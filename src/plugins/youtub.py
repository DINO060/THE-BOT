# ==================== src/plugins/youtube.py ====================
"""YouTube plugin using yt-dlp with enhanced security"""

import os
import re
import asyncio
import hashlib
from typing import Dict, Any, Optional, Tuple, List
from pathlib import Path
import yt_dlp

from src.plugins.base import BasePlugin, PluginInfo
from src.core.exceptions import DownloadError, DMCAError
from src.core.security import SecurityManager


class YouTubePlugin(BasePlugin):
    """YouTube/yt-dlp plugin for video downloads"""
    
    def __init__(self):
        super().__init__()
        self.security = SecurityManager()
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'no_color': True,
            'noprogress': True,
            'age_limit': 18,
            'prefer_free_formats': True,
            'keepvideo': False,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'referer': 'https://www.google.com/',
            'cookiefile': None,  # Don't use cookies by default (security)
            'socket_timeout': 30,
            'retries': 3,
            'fragment_retries': 3,
            'skip_unavailable_fragments': True,
            'concurrent_fragment_downloads': 4,
        }
    
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="youtube",
            version="2.0.0",
            author="BotTeam",
            description="YouTube and 1000+ sites video downloader",
            supported_domains=[
                "youtube.com", "youtu.be", "youtube-nocookie.com",
                "vimeo.com", "dailymotion.com", "facebook.com",
                "instagram.com", "twitter.com", "tiktok.com",
                "reddit.com", "twitch.tv", "soundcloud.com"
            ],
            supported_types=["video", "audio", "playlist"],
            priority=100
        )
    
    def can_handle(self, url: str) -> bool:
        """Check if URL can be handled by yt-dlp"""
        # First check common patterns for speed
        common_patterns = [
            r'(youtube\.com/watch\?v=|youtu\.be/)',
            r'(vimeo\.com/\d+)',
            r'(dailymotion\.com/video/)',
            r'(facebook\.com/.*/videos/)',
            r'(instagram\.com/(p|reel|tv)/)',
            r'(twitter\.com/.*/status/)',
            r'(reddit\.com/r/.*/comments/)',
            r'(tiktok\.com/@.*/video/)',
            r'(soundcloud\.com/)',
        ]
        
        for pattern in common_patterns:
            if re.search(pattern, url):
                return True
        
        # Use yt-dlp's extractor for other sites
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            try:
                extractors = ydl._ies
                for ie in extractors:
                    if ie.suitable(url):
                        return True
            except Exception:
                pass
        
        return False
    
    async def extract_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract video information without downloading"""
        # Check cache first
        cached_info = await self.get_cached_info(url)
        if cached_info:
            return cached_info
        
        opts = self.ydl_opts.copy()
        opts['skip_download'] = True
        opts['extract_flat'] = 'in_playlist'  # Only extract playlist info, not videos
        
        loop = asyncio.get_event_loop()
        
        try:
            # Run in thread pool to avoid blocking
            info = await loop.run_in_executor(
                None,
                self._extract_info_sync,
                url,
                opts
            )
            
            if not info:
                return None
            
            # Check for DMCA/copyright
            if await self._check_dmca(info):
                raise DMCAError("Content is DMCA protected")
            
            # Process and clean info
            processed_info = self._process_info(info)
            
            # Cache the info
            await self.cache_info(url, processed_info, ttl=3600)
            
            return processed_info
            
        except Exception as e:
            self.logger.error(f"Failed to extract info: {e}")
            await self.on_error(url, e)
            return None
    
    def _extract_info_sync(self, url: str, opts: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous info extraction"""
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    
    async def download(
        self,
        url: str,
        output_path: str,
        options: Dict[str, Any] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Download video with progress tracking"""
        options = options or {}
        
        # Prepare download options
        opts = self.ydl_opts.copy()
        
        # Set quality
        quality = options.get('quality', 'best')
        if quality == 'best':
            opts['format'] = 'best[ext=mp4]/best'
        elif quality == 'audio':
            opts['format'] = 'bestaudio/best'
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        else:
            opts['format'] = f'best[height<={quality}]/best'
        
        # Set output template
        safe_filename = self.security.generate_secure_token(16)
        opts['outtmpl'] = str(Path(output_path) / f'{safe_filename}.%(ext)s')
        
        # Add progress hook
        progress_data = {'percent': 0, 'speed': 0, 'eta': 0}
        
        def progress_hook(d):
            if d['status'] == 'downloading':
                progress_data['percent'] = d.get('_percent_str', '0%')
                progress_data['speed'] = d.get('_speed_str', 'N/A')
                progress_data['eta'] = d.get('_eta_str', 'N/A')
        
        opts['progress_hooks'] = [progress_hook]
        
        # Download
        loop = asyncio.get_event_loop()
        
        try:
            await self.before_download(url, options)
            
            # Run download in thread pool
            result = await loop.run_in_executor(
                None,
                self._download_sync,
                url,
                opts
            )
            
            if not result:
                return False, None, {"error": "Download failed"}
            
            # Get the downloaded file
            downloaded_files = list(Path(output_path).glob(f'{safe_filename}.*'))
            if not downloaded_files:
                return False, None, {"error": "No file downloaded"}
            
            file_path = str(downloaded_files[0])
            
            # Get file metadata
            metadata = {
                'title': result.get('title'),
                'description': result.get('description'),
                'duration': result.get('duration'),
                'uploader': result.get('uploader'),
                'upload_date': result.get('upload_date'),
                'view_count': result.get('view_count'),
                'like_count': result.get('like_count'),
                'resolution': f"{result.get('width')}x{result.get('height')}",
                'fps': result.get('fps'),
                'format': result.get('format'),
                'filesize': os.path.getsize(file_path),
            }
            
            await self.after_download(url, file_path, metadata)
            
            return True, file_path, metadata
            
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            await self.on_error(url, e)
            return False, None, {"error": str(e)}
    
    def _download_sync(self, url: str, opts: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous download"""
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=True)
    
    def _process_info(self, info: Dict[str, Any]) -> Dict[str, Any]:
        """Process and clean extracted info"""
        # Handle playlists
        if info.get('_type') == 'playlist':
            return {
                'type': 'playlist',
                'title': info.get('title', 'Playlist'),
                'uploader': info.get('uploader'),
                'playlist_count': len(info.get('entries', [])),
                'entries': [
                    {
                        'title': e.get('title'),
                        'url': e.get('url'),
                        'duration': e.get('duration'),
                    }
                    for e in info.get('entries', [])[:10]  # Limit to first 10
                ]
            }
        
        # Get best format
        formats = info.get('formats', [])
        best_video = None
        best_audio = None
        
        for f in formats:
            if f.get('vcodec') != 'none':
                if not best_video or (f.get('height', 0) > best_video.get('height', 0)):
                    best_video = f
            if f.get('acodec') != 'none':
                if not best_audio or (f.get('abr', 0) > best_audio.get('abr', 0)):
                    best_audio = f
        
        return {
            'type': 'video',
            'title': info.get('title', 'Unknown'),
            'description': (info.get('description') or '')[:500],  # Limit description length
            'thumbnail': info.get('thumbnail'),
            'duration': info.get('duration'),
            'uploader': info.get('uploader'),
            'upload_date': info.get('upload_date'),
            'view_count': info.get('view_count'),
            'like_count': info.get('like_count'),
            'width': info.get('width'),
            'height': info.get('height'),
            'fps': info.get('fps'),
            'format': best_video.get('format_note') if best_video else None,
            'resolution': f"{info.get('width')}x{info.get('height')}" if info.get('width') else None,
            'filesize': best_video.get('filesize') if best_video else None,
            'has_audio': bool(best_audio),
            'webpage_url': info.get('webpage_url'),
        }
    
    async def _check_dmca(self, info: Dict[str, Any]) -> bool:
        """Check if content is DMCA protected"""
        # Check against blacklist
        title = info.get('title', '').lower()
        uploader = info.get('uploader', '').lower()
        
        # Load DMCA blacklist from database or file
        blacklisted_terms = [
            # Add known copyrighted content patterns
            'vevo', 'official music video', 'warner', 'sony music',
            'universal music', 'copyright', 'umg'
        ]
        
        for term in blacklisted_terms:
            if term in title or term in uploader:
                return True
        
        # Check if marked as copyrighted by platform
        if info.get('age_limit', 0) >= 99:  # yt-dlp uses 99 for copyright blocked
            return True
        
        return False
