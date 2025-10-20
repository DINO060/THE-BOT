# ==================== src/services/downloader.py ====================
"""Media downloader service"""

import asyncio
import hashlib
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import aiohttp
import aiofiles

from src.core.cache import cache
from src.core.monitoring import monitoring, metrics
from src.core.exceptions import DownloadError
from src.plugins.base import plugin_manager


class DownloaderService:
    """Service for downloading media files"""
    
    def __init__(self):
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=300),
            connector=aiohttp.TCPConnector(limit=10)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def download_media(
        self,
        url: str,
        output_path: str,
        media_type: str = "auto",
        options: Dict[str, Any] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Download media from URL
        
        Returns:
            Tuple of (success, file_path, metadata)
        """
        # Check cache first
        cache_key = hashlib.sha256(url.encode()).hexdigest()
        cached = await cache.get('downloads', cache_key)
        
        if cached and not (options or {}).get('force_download'):
            return True, cached['file_path'], cached['metadata']
        
        # Find appropriate plugin
        plugin = await plugin_manager.find_handler(url)
        
        if not plugin:
            # Fallback to direct download
            return await self._direct_download(url, output_path, options)
        
        # Use plugin to download
        try:
            success, file_path, metadata = await plugin.download(
                url, output_path, options
            )
            
            if success:
                # Cache result
                await cache.set(
                    'downloads',
                    cache_key,
                    {
                        'file_path': file_path,
                        'metadata': metadata
                    },
                    ttl=3600
                )
                
                # Update metrics
                metrics.downloads_total.labels(
                    media_type=media_type,
                    status='success'
                ).inc()
            else:
                metrics.downloads_total.labels(
                    media_type=media_type,
                    status='failed'
                ).inc()
            
            return success, file_path, metadata
            
        except Exception as e:
            monitoring.track_error(e, {'url': url, 'media_type': media_type})
            raise DownloadError(f"Download failed: {e}")
    
    async def _direct_download(
        self,
        url: str,
        output_path: str,
        options: Dict[str, Any] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Direct HTTP download without plugin"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get(url) as response:
                response.raise_for_status()
                
                # Get filename from headers or URL
                filename = self._get_filename(response, url)
                file_path = str(Path(output_path) / filename)
                
                # Download file
                async with aiofiles.open(file_path, 'wb') as file:
                    async for chunk in response.content.iter_chunked(8192):
                        await file.write(chunk)
                
                # Get metadata
                metadata = {
                    'filename': filename,
                    'size': response.headers.get('content-length'),
                    'content_type': response.headers.get('content-type'),
                    'url': str(response.url)
                }
                
                return True, file_path, metadata
                
        except Exception as e:
            return False, None, {'error': str(e)}
    
    def _get_filename(self, response, url: str) -> str:
        """Extract filename from response or URL"""
        # Try Content-Disposition header
        if 'content-disposition' in response.headers:
            import re
            match = re.findall(
                'filename="?([^"]+)"?',
                response.headers['content-disposition']
            )
            if match:
                return match[0]
        
        # Fallback to URL
        from urllib.parse import urlparse
        path = urlparse(url).path
        return path.split('/')[-1] or 'download'