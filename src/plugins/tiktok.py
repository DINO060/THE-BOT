# ==================== src/plugins/tiktok.py ====================
"""TikTok plugin with anti-detection and watermark removal"""

import re
import json
import asyncio
from typing import Dict, Any, Optional, Tuple
import httpx

from src.plugins.base import BasePlugin, PluginInfo
from src.core.exceptions import DownloadError


class TikTokPlugin(BasePlugin):
    """TikTok video downloader with watermark removal option"""
    
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="tiktok",
            version="1.0.0",
            author="BotTeam",
            description="TikTok video downloader with no watermark option",
            supported_domains=["tiktok.com", "vm.tiktok.com"],
            supported_types=["video"],
            priority=85
        )
    
    def can_handle(self, url: str) -> bool:
        """Check if URL is a TikTok link"""
        patterns = [
            r'tiktok\.com/@[\w.-]+/video/\d+',
            r'tiktok\.com/t/[\w]+',
            r'vm\.tiktok\.com/[\w]+',
            r'vt\.tiktok\.com/[\w]+',
        ]
        
        for pattern in patterns:
            if re.search(pattern, url):
                return True
        return False
    
    async def extract_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract TikTok video information"""
        # Resolve short URLs
        final_url = await self._resolve_redirect(url)
        
        # Extract video ID
        video_id = self._extract_video_id(final_url)
        if not video_id:
            return None
        
        # Try multiple extraction methods
        info = await self._extract_via_api(video_id)
        if not info:
            info = await self._extract_via_web(final_url)
        
        return info
    
    async def _resolve_redirect(self, url: str) -> str:
        """Resolve TikTok short URLs"""
        if 'vm.tiktok.com' in url or '/t/' in url:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, headers={
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X)'
                })
                return str(response.url)
        return url
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from URL"""
        match = re.search(r'/video/(\d+)', url)
        if match:
            return match.group(1)
        return None
    
    async def _extract_via_api(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Extract using TikTok API endpoints"""
        api_url = f"https://api2.musical.ly/aweme/v1/aweme/detail/"
        
        params = {
            'aweme_id': video_id,
            'version_code': '26.1.3',
            'app_name': 'musical_ly',
            'channel': 'App Store',
            'device_platform': 'iphone',
            'device_type': 'iPhone9,2',
            'os_version': '14.6',
        }
        
        headers = {
            'User-Agent': 'TikTok 26.1.3 rv:261303 (iPhone; iOS 14.6; en_US)',
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(api_url, params=params, headers=headers)
                data = response.json()
                
                if data.get('aweme_detail'):
                    return self._parse_api_response(data['aweme_detail'])
                    
            except Exception as e:
                self.logger.debug(f"API extraction failed: {e}")
        
        return None
    
    async def _extract_via_web(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract from web page"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers)
                
                # Extract JSON data from page
                match = re.search(
                    r'<script[^>]*>self\.__UNIVERSAL_DATA_FOR_REHYDRATION__\s*=\s*({.+?})</script>',
                    response.text
                )
                
                if match:
                    data = json.loads(match.group(1))
                    return self._parse_web_data(data)
                
                # Alternative pattern
                match = re.search(
                    r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>({.+?})</script>',
                    response.text
                )
                
                if match:
                    data = json.loads(match.group(1))
                    return self._parse_web_data(data)
                    
            except Exception as e:
                self.logger.error(f"Web extraction failed: {e}")
        
        return None
    
    def _parse_api_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse TikTok API response"""
        video = data.get('video', {})
        stats = data.get('statistics', {})
        author = data.get('author', {})
        
        # Get video URLs
        download_addr = video.get('download_addr', {}).get('url_list', [])
        play_addr = video.get('play_addr', {}).get('url_list', [])
        
        # No watermark URL (if available)
        no_watermark_url = None
        for url in play_addr:
            if 'watermark=0' in url or 'vod-' in url:
                no_watermark_url = url
                break
        
        return {
            'type': 'tiktok_video',
            'video_id': data.get('aweme_id'),
            'description': data.get('desc', '')[:200],
            'author': author.get('unique_id'),
            'author_name': author.get('nickname'),
            'create_time': data.get('create_time'),
            'duration': video.get('duration'),
            'width': video.get('width'),
            'height': video.get('height'),
            'cover': video.get('cover', {}).get('url_list', [None])[0],
            'play_count': stats.get('play_count'),
            'like_count': stats.get('digg_count'),
            'comment_count': stats.get('comment_count'),
            'share_count': stats.get('share_count'),
            'download_url': download_addr[0] if download_addr else None,
            'play_url': play_addr[0] if play_addr else None,
            'no_watermark_url': no_watermark_url,
        }
    
    def _parse_web_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse web page data"""
        # Navigate through nested structure
        try:
            default_scope = data.get('__DEFAULT_SCOPE__', {})
            video_detail = default_scope.get('webapp.video-detail', {})
            item_info = video_detail.get('itemInfo', {}).get('itemStruct', {})
            
            video = item_info.get('video', {})
            stats = item_info.get('stats', {})
            author = item_info.get('author', {})
            
            # Get highest quality download URL
            download_url = video.get('downloadAddr')
            bitrate_info = video.get('bitrateInfo', [])
            
            best_quality_url = download_url
            if bitrate_info:
                # Sort by quality and get best
                sorted_bitrates = sorted(bitrate_info, key=lambda x: x.get('Bitrate', 0), reverse=True)
                if sorted_bitrates:
                    best_quality_url = sorted_bitrates[0].get('PlayAddr', {}).get('UrlList', [download_url])[0]
            
            return {
                'type': 'tiktok_video',
                'video_id': item_info.get('id'),
                'description': item_info.get('desc', '')[:200],
                'author': author.get('uniqueId'),
                'author_name': author.get('nickname'),
                'create_time': item_info.get('createTime'),
                'duration': video.get('duration'),
                'width': video.get('width'),
                'height': video.get('height'),
                'cover': video.get('cover'),
                'play_count': stats.get('playCount'),
                'like_count': stats.get('diggCount'),
                'comment_count': stats.get('commentCount'),
                'share_count': stats.get('shareCount'),
                'download_url': best_quality_url,
                'music': item_info.get('music', {}).get('title'),
            }
        except Exception as e:
            self.logger.error(f"Failed to parse web data: {e}")
            return None
    
    async def download(
        self,
        url: str,
        output_path: str,
        options: Dict[str, Any] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Download TikTok video"""
        options = options or {}
        
        # Extract video info
        info = await self.extract_info(url)
        if not info:
            return False, None, {"error": "Failed to extract video info"}
        
        # Choose download URL
        download_url = info.get('no_watermark_url')  # Prefer no watermark
        if not download_url:
            download_url = info.get('download_url') or info.get('play_url')
        
        if not download_url:
            return False, None, {"error": "No download URL found"}
        
        # Download video
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X)',
            'Referer': 'https://www.tiktok.com/',
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    download_url,
                    headers=headers,
                    follow_redirects=True,
                    timeout=60
                )
                response.raise_for_status()
                
                # Save video
                video_path = f"{output_path}.mp4"
                with open(video_path, 'wb') as f:
                    f.write(response.content)
                
                # If watermark removal requested and we have watermark version
                if options.get('remove_watermark') and 'watermark' in download_url:
                    # Use FFmpeg to crop watermark (usually at bottom)
                    import subprocess
                    
                    output_no_wm = f"{output_path}_no_watermark.mp4"
                    cmd = [
                        'ffmpeg', '-i', video_path,
                        '-vf', 'crop=in_w:in_h-20:0:0',  # Crop 20px from bottom
                        '-c:a', 'copy',
                        output_no_wm
                    ]
                    
                    result = subprocess.run(cmd, capture_output=True)
                    if result.returncode == 0:
                        os.remove(video_path)
                        video_path = output_no_wm
                
                return True, video_path, info
                
            except Exception as e:
                self.logger.error(f"Download failed: {e}")
                return False, None, {"error": str(e)}