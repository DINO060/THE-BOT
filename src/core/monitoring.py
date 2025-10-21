# ==================== src/core/monitoring.py ====================
"""Comprehensive monitoring with Prometheus, Sentry, and Elasticsearch"""

import time
import logging
import json
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from functools import wraps
import traceback

from prometheus_client import Counter, Histogram, Gauge, Info, CollectorRegistry, generate_latest
import sentry_sdk
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from elasticsearch import AsyncElasticsearch
from opentelemetry import trace
from opentelemetry.exporter.jaeger import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .config import settings


class Metrics:
    """Prometheus metrics collection"""
    
    def __init__(self):
        self.registry = CollectorRegistry()
        
        # Counters
        self.downloads_total = Counter(
            'bot_downloads_total',
            'Total downloads',
            ['media_type', 'status'],
            registry=self.registry
        )
        
        self.requests_total = Counter(
            'bot_requests_total',
            'Total requests',
            ['handler', 'status'],
            registry=self.registry
        )
        
        self.errors_total = Counter(
            'bot_errors_total',
            'Total errors',
            ['error_type', 'handler'],
            registry=self.registry
        )
        
        self.cache_hits = Counter(
            'bot_cache_hits_total',
            'Cache hits',
            registry=self.registry
        )
        
        self.cache_misses = Counter(
            'bot_cache_misses_total',
            'Cache misses',
            registry=self.registry
        )
        
        self.cache_sets = Counter(
            'bot_cache_sets_total',
            'Cache sets',
            registry=self.registry
        )
        
        self.cache_errors = Counter(
            'bot_cache_errors_total',
            'Cache errors',
            registry=self.registry
        )
        
        # Histograms
        self.download_duration = Histogram(
            'bot_download_duration_seconds',
            'Download duration',
            ['media_type'],
            buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600),
            registry=self.registry
        )
        
        self.request_duration = Histogram(
            'bot_request_duration_seconds',
            'Request duration',
            ['handler'],
            buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5),
            registry=self.registry
        )
        
        self.file_size = Histogram(
            'bot_file_size_bytes',
            'Downloaded file size',
            ['media_type'],
            buckets=(
                1024 * 100,      # 100KB
                1024 * 500,      # 500KB
                1024 * 1024,     # 1MB
                1024 * 1024 * 5, # 5MB
                1024 * 1024 * 10,    # 10MB
                1024 * 1024 * 50,    # 50MB
                1024 * 1024 * 100,   # 100MB
                1024 * 1024 * 500,   # 500MB
                1024 * 1024 * 1024,  # 1GB
                1024 * 1024 * 1024 * 2,  # 2GB
            ),
            registry=self.registry
        )
        
        # Gauges
        self.active_users = Gauge(
            'bot_active_users',
            'Active users',
            registry=self.registry
        )
        
        self.queue_size = Gauge(
            'bot_queue_size',
            'Queue size',
            ['queue_name'],
            registry=self.registry
        )
        
        self.cache_memory = Gauge(
            'bot_cache_memory_bytes',
            'Cache memory usage',
            registry=self.registry
        )
        
        # Info
        self.build_info = Info(
            'bot_build',
            'Build information',
            registry=self.registry
        )
        
        self.build_info.info({
            'version': '1.0.0',
            'environment': settings.environment,
            'debug': str(settings.debug)
        })
    
    def export(self) -> bytes:
        """Export metrics in Prometheus format"""
        return generate_latest(self.registry)


# Global metrics instance
metrics = Metrics()


class MonitoringManager:
    """Centralized monitoring management"""
    
    def __init__(self):
        self.elasticsearch = None
        self.tracer = None
        self._setup_sentry()
        self._setup_tracing()
        self._setup_elasticsearch()
    
    def _setup_sentry(self):
        """Initialize Sentry error tracking"""
        if settings.sentry_dsn and settings.enable_monitoring:
            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                environment=settings.environment,
                integrations=[
                    SqlalchemyIntegration(),
                    RedisIntegration(),
                ],
                traces_sample_rate=0.1 if settings.is_production else 1.0,
                profiles_sample_rate=0.1 if settings.is_production else 1.0,
                attach_stacktrace=True,
                send_default_pii=False,  # GDPR compliance
                before_send=self._before_send_sentry,
            )
    
    def _before_send_sentry(self, event: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Filter sensitive data before sending to Sentry"""
        # Remove sensitive data
        if 'extra' in event:
            sensitive_keys = ['password', 'token', 'api_key', 'secret', 'card']
            for key in list(event['extra'].keys()):
                if any(sensitive in key.lower() for sensitive in sensitive_keys):
                    event['extra'][key] = '[REDACTED]'
        
        return event
    
    def _setup_tracing(self):
        """Initialize OpenTelemetry tracing"""
        if settings.enable_monitoring:
            trace.set_tracer_provider(TracerProvider())
            self.tracer = trace.get_tracer(__name__)
            
            # Add Jaeger exporter for production
            if settings.is_production:
                jaeger_exporter = JaegerExporter(
                    agent_host_name="jaeger",
                    agent_port=6831,
                )
                span_processor = BatchSpanProcessor(jaeger_exporter)
                trace.get_tracer_provider().add_span_processor(span_processor)
    
    async def _setup_elasticsearch(self):
        """Initialize Elasticsearch for log aggregation"""
        if settings.elastic_url and settings.enable_monitoring:
            self.elasticsearch = AsyncElasticsearch([settings.elastic_url])
    
    async def log_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        user_id: Optional[int] = None,
        level: str = "info"
    ):
        """Log event to Elasticsearch"""
        if not self.elasticsearch:
            return
        
        document = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "level": level,
            "user_id": user_id,
            "data": data,
            "environment": settings.environment,
        }
        
        try:
            await self.elasticsearch.index(
                index=f"bot-logs-{datetime.utcnow().strftime('%Y.%m')}",
                body=document
            )
        except Exception as e:
            logging.error(f"Elasticsearch logging failed: {e}")
    
    def track_error(self, error: Exception, context: Dict[str, Any] = None):
        """Track error in Sentry"""
        sentry_sdk.capture_exception(error, extra=context)
    
    def track_performance(self, name: str):
        """Decorator to track function performance"""
        def decorator(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()
                
                # Start tracing span
                if self.tracer:
                    with self.tracer.start_as_current_span(name) as span:
                        try:
                            result = await func(*args, **kwargs)
                            span.set_status(trace.Status(trace.StatusCode.OK))
                            return result
                        except Exception as e:
                            span.set_status(
                                trace.Status(trace.StatusCode.ERROR, str(e))
                            )
                            raise
                        finally:
                            duration = time.time() - start_time
                            metrics.request_duration.labels(handler=name).observe(duration)
                else:
                    try:
                        return await func(*args, **kwargs)
                    finally:
                        duration = time.time() - start_time
                        metrics.request_duration.labels(handler=name).observe(duration)
            
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = time.time()
                
                if self.tracer:
                    with self.tracer.start_as_current_span(name) as span:
                        try:
                            result = func(*args, **kwargs)
                            span.set_status(trace.Status(trace.StatusCode.OK))
                            return result
                        except Exception as e:
                            span.set_status(
                                trace.Status(trace.StatusCode.ERROR, str(e))
                            )
                            raise
                        finally:
                            duration = time.time() - start_time
                            metrics.request_duration.labels(handler=name).observe(duration)
                else:
                    try:
                        return func(*args, **kwargs)
                    finally:
                        duration = time.time() - start_time
                        metrics.request_duration.labels(handler=name).observe(duration)
            
            return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
        return decorator


# Global monitoring instance
monitoring = MonitoringManager()







