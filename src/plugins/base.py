# ==================== src/plugins/base.py ====================
"""Plugin system for extensible media processing"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
import re
import logging

from src.core.cache import cache
from src.core.monitoring import monitoring


@dataclass
class PluginInfo:
    """Plugin metadata"""
    name: str
    version: str
    author: str
    description: str
    supported_domains: List[str]
    supported_types: List[str]
    priority: int = 0  # Higher priority plugins are tried first


class BasePlugin(ABC):
    """Base class for all plugins"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cache = cache
        self.monitoring = monitoring
    
    @property
    @abstractmethod
    def info(self) -> PluginInfo:
        """Plugin information"""
        pass
    
    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if plugin can handle this URL"""
        pass
    
    @abstractmethod
    async def extract_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract media information without downloading"""
        pass
    
    @abstractmethod
    async def download(
        self,
        url: str,
        output_path: str,
        options: Dict[str, Any] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Download media
        
        Returns:
            Tuple of (success, file_path, metadata)
        """
        pass
    
    async def validate_url(self, url: str) -> bool:
        """Validate URL format"""
        try:
            # Basic URL validation
            pattern = r'^https?://[^\s/$.?#].[^\s]*$'
            if not re.match(pattern, url):
                return False
            
            # Check against supported domains
            for domain in self.info.supported_domains:
                if domain in url:
                    return True
            
            return False
        except Exception:
            return False
    
    async def get_cached_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Get cached media info"""
        cache_key = f"plugin:{self.info.name}:info:{url}"
        return await self.cache.get("plugin_info", cache_key)
    
    async def cache_info(self, url: str, info: Dict[str, Any], ttl: int = 3600):
        """Cache media info"""
        cache_key = f"plugin:{self.info.name}:info:{url}"
        await self.cache.set("plugin_info", cache_key, info, ttl)
    
    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe storage"""
        # Remove invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        
        # Limit length
        name, ext = os.path.splitext(filename)
        if len(name) > 200:
            name = name[:200]
        
        return f"{name}{ext}"
    
    async def before_download(self, url: str, options: Dict[str, Any] = None):
        """Hook called before download starts"""
        pass
    
    async def after_download(
        self,
        url: str,
        file_path: str,
        metadata: Dict[str, Any]
    ):
        """Hook called after successful download"""
        pass
    
    async def on_error(self, url: str, error: Exception):
        """Hook called on download error"""
        self.logger.error(f"Download error for {url}: {error}")
        self.monitoring.track_error(error, {
            'plugin': self.info.name,
            'url': url
        })


class PluginManager:
    """Manage and orchestrate plugins"""
    
    def __init__(self):
        self.plugins: List[BasePlugin] = []
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def register(self, plugin: BasePlugin):
        """Register a plugin"""
        self.plugins.append(plugin)
        self.plugins.sort(key=lambda p: p.info.priority, reverse=True)
        self.logger.info(f"Registered plugin: {plugin.info.name}")
    
    def unregister(self, plugin_name: str):
        """Unregister a plugin"""
        self.plugins = [p for p in self.plugins if p.info.name != plugin_name]
    
    async def find_handler(self, url: str) -> Optional[BasePlugin]:
        """Find appropriate plugin for URL"""
        for plugin in self.plugins:
            if plugin.can_handle(url):
                return plugin
        return None
    
    async def extract_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract info using appropriate plugin"""
        plugin = await self.find_handler(url)
        if plugin:
            return await plugin.extract_info(url)
        return None
    
    async def download(
        self,
        url: str,
        output_path: str,
        options: Dict[str, Any] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Download using appropriate plugin"""
        plugin = await self.find_handler(url)
        if plugin:
            return await plugin.download(url, output_path, options)
        return False, None, None
    
    def get_supported_domains(self) -> List[str]:
        """Get all supported domains"""
        domains = set()
        for plugin in self.plugins:
            domains.update(plugin.info.supported_domains)
        return list(domains)
    
    def get_plugin_info(self) -> List[PluginInfo]:
        """Get info for all plugins"""
        return [plugin.info for plugin in self.plugins]


# Global plugin manager
plugin_manager = PluginManager()