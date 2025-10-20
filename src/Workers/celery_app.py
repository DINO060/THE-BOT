# ==================== src/workers/celery_app.py ====================
"""Celery configuration for distributed task processing"""

from celery import Celery, Task
from celery.signals import worker_ready, worker_shutdown, task_failure, task_success
from kombu import Queue, Exchange
import logging

from src.core.config import settings
from src.core.monitoring import monitoring, metrics


# Create Celery app
celery_app = Celery(
    'bot_workers',
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        'src.workers.tasks.download',
        'src.workers.tasks.convert',
        'src.workers.tasks.upload',
        'src.workers.tasks.cleanup',
    ]
)

# Configure Celery
celery_app.conf.update(
    # Task settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Task execution
    task_track_started=True,
    task_time_limit=settings.celery_task_timeout,
    task_soft_time_limit=settings.celery_task_timeout - 60,
    task_acks_late=True,
    worker_prefetch_multiplier=2,
    
    # Queue configuration
    task_default_queue='default',
    task_queues=(
        Queue('default', Exchange('default'), routing_key='default'),
        Queue('downloads', Exchange('downloads'), routing_key='downloads'),
        Queue('priority', Exchange('priority'), routing_key='priority'),
        Queue('conversion', Exchange('conversion'), routing_key='conversion'),
        Queue('maintenance', Exchange('maintenance'), routing_key='maintenance'),
    ),
    task_routes={
        'src.workers.tasks.download.*': {'queue': 'downloads'},
        'src.workers.tasks.convert.*': {'queue': 'conversion'},
        'src.workers.tasks.cleanup.*': {'queue': 'maintenance'},
    },
    
    # Result backend
    result_expires=3600,
    
    # Worker settings
    worker_max_tasks_per_child=100,
    worker_disable_rate_limits=False,
    
    # Beat scheduler
    beat_schedule={
        'cleanup-expired-cache': {
            'task': 'src.workers.tasks.cleanup.cleanup_expired_cache',
            'schedule': 3600.0,  # Every hour
        },
        'cleanup-temp-files': {
            'task': 'src.workers.tasks.cleanup.cleanup_temp_files',
            'schedule': 1800.0,  # Every 30 minutes
        },
        'update-metrics': {
            'task': 'src.workers.tasks.monitoring.update_metrics',
            'schedule': 60.0,  # Every minute
        },
    },
)


class MonitoredTask(Task):
    """Base task with monitoring"""
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure"""
        monitoring.track_error(exc, {
            'task_id': task_id,
            'task_name': self.name,
            'args': args,
            'kwargs': kwargs,
        })
        metrics.errors_total.labels(
            error_type=type(exc).__name__,
            handler=self.name
        ).inc()
    
    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success"""
        pass
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Handle task retry"""
        logging.warning(f"Task {self.name} retrying: {exc}")


# Set base task
celery_app.Task = MonitoredTask


@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Handle worker startup"""
    logging.info(f"Worker ready: {sender}")
    metrics.queue_size.labels(queue_name='workers').inc()


@worker_shutdown.connect
def worker_shutdown_handler(sender=None, **kwargs):
    """Handle worker shutdown"""
    logging.info(f"Worker shutting down: {sender}")
    metrics.queue_size.labels(queue_name='workers').dec()


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, **kwargs):
    """Handle task failure"""
    metrics.errors_total.labels(
        error_type=type(exception).__name__,
        handler=sender.name if sender else 'unknown'
    ).inc()


@task_success.connect
def task_success_handler(sender=None, result=None, **kwargs):
    """Handle task success"""
    pass