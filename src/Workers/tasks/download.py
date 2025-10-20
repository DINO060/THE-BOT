# ==================== src/workers/tasks/download.py ====================
"""Download tasks for Celery workers"""

import os
import hashlib
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from celery import current_task
from src.workers.celery_app import celery_app
from src.core.database import get_db, MediaItem, User, MediaType
from src.core.cache import cache
from src.core.monitoring import monitoring, metrics
from src.core.exceptions import DownloadError, QuotaExceededError
from src.plugins.base import plugin_manager
from src.services.storage import storage_service


@celery_app.task(bind=True, name='download.process_media')
def process_media_download(
    self,
    user_id: int,
    url: str,
    media_type: str,
    options: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Process media download with caching and quota management
    
    Args:
        user_id: User ID
        url: Media URL
        media_type: Type of media
        options: Download options
    
    Returns:
        Dict with download result
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(
            _process_download_async(self, user_id, url, media_type, options)
        )
        return result
    finally:
        loop.close()


async def _process_download_async(
    task,
    user_id: int,
    url: str,
    media_type: str,
    options: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Async download processing"""
    
    # Update task state
    task.update_state(state='PROCESSING', meta={'progress': 0})
    
    # Check cache first
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    cached_result = await cache.get('downloads', url_hash)
    
    if cached_result and not (options or {}).get('force_download'):
        # Verify file still exists
        if await storage_service.exists(cached_result['s3_key']):
            metrics.cache_hits.inc()
            return cached_result
    
    # Check user quota
    async with get_db() as db:
        user = await db.get(User, user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        # Check daily quota
        if user.quota_reset_at and user.quota_reset_at < datetime.utcnow():
            user.daily_quota_used = 0
            user.quota_reset_at = datetime.utcnow() + timedelta(days=1)
        
        quota_limit = 10000 if user.is_premium else 1000  # MB
        if user.daily_quota_used >= quota_limit:
            raise QuotaExceededError("Daily quota exceeded")
    
    # Find appropriate plugin
    plugin = await plugin_manager.find_handler(url)
    if not plugin:
        raise DownloadError(f"No plugin available for URL: {url}")
    
    # Extract info first
    task.update_state(state='PROCESSING', meta={'progress': 10})
    info = await plugin.extract_info(url)
    
    if not info:
        raise DownloadError("Failed to extract media information")
    
    # Download media
    task.update_state(state='PROCESSING', meta={'progress': 30})
    temp_path = f"/tmp/{task.request.id}"
    
    success, file_path, metadata = await plugin.download(
        url, temp_path, options
    )
    
    if not success:
        raise DownloadError(f"Download failed: {metadata.get('error')}")
    
    # Get file info
    file_size = os.path.getsize(file_path)
    file_hash = hashlib.sha256(open(file_path, 'rb').read()).hexdigest()
    
    # Upload to S3
    task.update_state(state='PROCESSING', meta={'progress': 70})
    s3_key = f"{media_type}/{datetime.utcnow().strftime('%Y/%m/%d')}/{file_hash}"
    s3_url = await storage_service.upload(file_path, s3_key)
    
    # Update database
    task.update_state(state='PROCESSING', meta={'progress': 90})
    async with get_db() as db:
        # Create media item
        media_item = MediaItem(
            user_id=user_id,
            url=url,
            url_hash=url_hash,
            media_type=MediaType[media_type.upper()],
            s3_key=s3_key,
            file_size=file_size,
            file_hash=file_hash,
            title=metadata.get('title'),
            description=metadata.get('description'),
            duration=metadata.get('duration'),
            resolution=metadata.get('resolution'),
            metadata=metadata,
            cached_at=datetime.utcnow(),
            cache_expires_at=datetime.utcnow() + timedelta(days=7 if user.is_premium else 1)
        )
        db.add(media_item)
        
        # Update user quota
        user.daily_quota_used += file_size / (1024 * 1024)  # Convert to MB
        user.total_downloads += 1
        user.total_bytes += file_size
        
        await db.commit()
    
    # Clean up temp file
    os.remove(file_path)
    
    # Cache result
    result = {
        'success': True,
        'url': s3_url,
        's3_key': s3_key,
        'file_size': file_size,
        'metadata': metadata
    }
    
    await cache.set('downloads', url_hash, result, ttl=3600)
    
    # Update metrics
    metrics.downloads_total.labels(
        media_type=media_type,
        status='success'
    ).inc()
    metrics.file_size.labels(media_type=media_type).observe(file_size)
    
    task.update_state(state='SUCCESS', meta={'progress': 100})
    
    return result


@celery_app.task(name='download.batch_download')
def batch_download(urls: List[str], user_id: int, options: Dict[str, Any] = None):
    """Process multiple downloads in batch"""
    results = []
    
    for url in urls:
        try:
            result = process_media_download.delay(
                user_id, url, 'video', options
            )
            results.append(result.id)
        except Exception as e:
            results.append({'error': str(e), 'url': url})
    
    return results