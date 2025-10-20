# ==================== src/plugins/instagram.py ====================
"""Instagram plugin with enhanced security and anti-detection"""

import re
import json
import asyncio
from typing import Dict, Any, Optional, Tuple
from playwright.async_api import async_playwright, Page
import httpx

from src.plugins.base import BasePlugin, PluginInfo
from src.core.exceptions import DownloadError


class InstagramPlugin(BasePlugin):
    """Instagram media downloader with anti-detection measures"""
    
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="instagram",
            version="1.0.0",
            author="BotTeam",
            description="Instagram photo, video, and story downloader",
            supported_domains=["instagram.com", "instagr.am"],
            supported_types=["photo", "video", "carousel", "story", "reel"],
            priority=90
        )
    
    def can_handle(self, url: str) -> bool:
        """Check if URL is an Instagram link"""
        patterns = [
            r'instagram\.com/p/[\w-]+',
            r'instagram\.com/reel/[\w-]+',
            r'instagram\.com/tv/[\w-]+',
            r'instagram\.com/stories/[\w-]+',
            r'instagr\.am/[\w-]+',
        ]
        
        for pattern in patterns:
            if re.search(pattern, url):
                return True
        return False
    
    async def extract_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract Instagram post information"""
        # Try API-based extraction first (faster)
        info = await self._extract_via_api(url)
        if info:
            return info
        
        # Fallback to browser-based extraction
        return await self._extract_via_browser(url)
    
    async def _extract_via_api(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract using Instagram's internal API"""
        # Extract shortcode from URL
        match = re.search(r'/(?:p|reel|tv)/([\w-]+)', url)
        if not match:
            return None
        
        shortcode = match.group(1)
        
        # Use Instagram's GraphQL API
        api_url = f"https://www.instagram.com/graphql/query/"
        
        query_hash = "9f8827793ef34641b2fb195d4d41151c"  # This may change
        variables = {
            "shortcode": shortcode,
            "child_comment_count": 0,
            "fetch_comment_count": 0,
            "parent_comment_count": 0,
            "has_threaded_comments": False
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': url,
        }
        
        params = {
            'query_hash': query_hash,
            'variables': json.dumps(variables)
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(api_url, params=params, headers=headers)
                data = response.json()
                
                media = data.get('data', {}).get('shortcode_media', {})
                if not media:
                    return None
                
                return self._parse_media_data(media)
                
            except Exception as e:
                self.logger.debug(f"API extraction failed: {e}")
                return None
    
    async def _extract_via_browser(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract using browser automation"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-web-security',
                ]
            )
            
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                locale='en-US',
            )
            
            # Add anti-detection scripts
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'permissions', {
                    get: () => ({ query: () => Promise.resolve({ state: 'granted' }) })
                });
            """)
            
            page = await context.new_page()
            
            try:
                # Navigate with timeout
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                
                # Wait for content to load
                await page.wait_for_selector('article', timeout=10000)
                
                # Extract media URLs
                media_info = await self._extract_media_from_page(page)
                
                return media_info
                
            except Exception as e:
                self.logger.error(f"Browser extraction failed: {e}")
                return None
            finally:
                await browser.close()
    
    async def _extract_media_from_page(self, page: Page) -> Dict[str, Any]:
        """Extract media information from loaded page"""
        # Get post data from page
        data = await page.evaluate("""
            () => {
                const getMediaFromArticle = () => {
                    const article = document.querySelector('article');
                    if (!article) return null;
                    
                    const media = [];
                    
                    // Find images
                    const images = article.querySelectorAll('img[srcset]');
                    images.forEach(img => {
                        const srcset = img.getAttribute('srcset');
                        const urls = srcset.split(',').map(s => s.trim().split(' ')[0]);
                        media.push({
                            type: 'image',
                            url: urls[urls.length - 1],  // Highest quality
                            thumbnail: img.src
                        });
                    });
                    
                    // Find videos
                    const videos = article.querySelectorAll('video');
                    videos.forEach(video => {
                        media.push({
                            type: 'video',
                            url: video.src,
                            thumbnail: video.poster
                        });
                    });
                    
                    // Get caption
                    const caption = article.querySelector('h1, [role="button"] span')?.innerText;
                    
                    // Get username
                    const username = document.querySelector('header a')?.innerText;
                    
                    return {
                        media: media,
                        caption: caption,
                        username: username
                    };
                };
                
                return getMediaFromArticle();
            }
        """)
        
        if not data or not data.get('media'):
            raise DownloadError("Could not extract media from page")
        
        return {
            'type': 'instagram_post',
            'username': data.get('username'),
            'caption': data.get('caption', '')[:200],
            'media_count': len(data['media']),
            'media_urls': [m['url'] for m in data['media']],
            'media_types': [m['type'] for m in data['media']],
            'thumbnails': [m.get('thumbnail') for m in data['media']],
        }
    
    def _parse_media_data(self, media: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Instagram API media data"""
        info = {
            'type': media.get('__typename', 'GraphImage').replace('Graph', '').lower(),
            'shortcode': media.get('shortcode'),
            'caption': (media.get('edge_media_to_caption', {})
                       .get('edges', [{}])[0]
                       .get('node', {})
                       .get('text', ''))[:200],
            'username': media.get('owner', {}).get('username'),
            'timestamp': media.get('taken_at_timestamp'),
            'likes': media.get('edge_media_preview_like', {}).get('count'),
            'comments': media.get('edge_media_to_comment', {}).get('count'),
        }
        
        # Handle different media types
        if info['type'] == 'video':
            info['video_url'] = media.get('video_url')
            info['thumbnail'] = media.get('thumbnail_src')
            info['duration'] = media.get('video_duration')
            info['view_count'] = media.get('video_view_count')
        elif info['type'] == 'sidecar':
            # Carousel post
            edges = media.get('edge_sidecar_to_children', {}).get('edges', [])
            info['media_count'] = len(edges)
            info['media_urls'] = []
            for edge in edges:
                node = edge.get('node', {})
                if node.get('is_video'):
                    info['media_urls'].append(node.get('video_url'))
                else:
                    info['media_urls'].append(node.get('display_url'))
        else:
            # Single image
            info['image_url'] = media.get('display_url')
            info['thumbnail'] = media.get('thumbnail_src')
        
        return info
    
    async def download(
        self,
        url: str,
        output_path: str,
        options: Dict[str, Any] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Download Instagram media"""
        # Extract media info
        info = await self.extract_info(url)
        if not info:
            return False, None, {"error": "Failed to extract media info"}
        
        # Determine media URLs
        media_urls = []
        if 'video_url' in info:
            media_urls.append(info['video_url'])
        elif 'image_url' in info:
            media_urls.append(info['image_url'])
        elif 'media_urls' in info:
            media_urls.extend(info['media_urls'])
        
        if not media_urls:
            return False, None, {"error": "No media URLs found"}
        
        # Download media files
        downloaded_files = []
        async with httpx.AsyncClient() as client:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.instagram.com/',
            }
            
            for i, media_url in enumerate(media_urls):
                try:
                    response = await client.get(media_url, headers=headers, timeout=60)
                    response.raise_for_status()
                    
                    # Determine file extension
                    content_type = response.headers.get('content-type', '')
                    ext = '.mp4' if 'video' in content_type else '.jpg'
                    
                    # Save file
                    filename = f"{output_path}_{i}{ext}" if len(media_urls) > 1 else f"{output_path}{ext}"
                    
                    with open(filename, 'wb') as f:
                        f.write(response.content)
                    
                    downloaded_files.append(filename)
                    
                except Exception as e:
                    self.logger.error(f"Failed to download media {i}: {e}")
        
        if not downloaded_files:
            return False, None, {"error": "Failed to download any media"}
        
        # Return first file if single, or create archive if multiple
        if len(downloaded_files) == 1:
            return True, downloaded_files[0], info
        else:
            # Create ZIP archive for multiple files
            import zipfile
            zip_path = f"{output_path}.zip"
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for file in downloaded_files:
                    zipf.write(file, os.path.basename(file))
                    os.remove(file)  # Clean up individual files
            
            info['media_count'] = len(downloaded_files)
            return True, zip_path, info