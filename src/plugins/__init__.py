# ==================== src/plugins/__init__.py ====================
"""Plugin system for extensible media processing"""

from src.plugins.base import (
    BasePlugin,
    PluginInfo,
    PluginManager,
    plugin_manager
)

# Import and register all plugins
def register_all_plugins():
    """Register all available plugins"""
    try:
        from src.plugins.youtube import YouTubePlugin
        from src.plugins.instagram import InstagramPlugin
        from src.plugins.tiktok import TikTokPlugin
        
        plugin_manager.register(YouTubePlugin())
        plugin_manager.register(InstagramPlugin())
        plugin_manager.register(TikTokPlugin())
        
        return plugin_manager
    except ImportError as e:
        print(f"Failed to import plugins: {e}")
        return plugin_manager

__all__ = [
    'BasePlugin',
    'PluginInfo',
    'PluginManager',
    'plugin_manager',
    'register_all_plugins',
]
