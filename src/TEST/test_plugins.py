# ==================== tests/test_plugins.py ====================
"""Plugin system tests"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import tempfile
import os

from src.plugins.base import PluginManager
from src.plugins.youtube import YouTubePlugin


class TestYouTubePlugin:
    """Test YouTube plugin"""
    
    @pytest.fixture
    def youtube_plugin(self):
        return YouTubePlugin()
    
    def test_can_handle_youtube_urls(self, youtube_plugin):
        """Test YouTube URL detection"""
        valid_urls = [
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=test&list=playlist",
            "https://m.youtube.com/watch?v=test",
        ]
        
        for url in valid_urls:
            assert youtube_plugin.can_handle(url) is True
    
    def test_rejects_non_youtube_urls(self, youtube_plugin):
        """Test rejection of non-YouTube URLs"""
        invalid_urls = [
            "https://example.com",
            "https://vimeo.com/123",
            "not a url",
            "",
        ]
        
        for url in invalid_urls:
            assert youtube_plugin.can_handle(url) is False
    
    @pytest.mark.asyncio
    async def test_extract_info_caching(self, youtube_plugin):
        """Test that extracted info is cached"""
        url = "https://youtube.com/watch?v=test"
        
        with patch.object(youtube_plugin, 'get_cached_info') as mock_cache:
            mock_cache.return_value = {"cached": True}
            
            result = await youtube_plugin.extract_info(url)
            assert result == {"cached": True}
            mock_cache.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_dmca_check(self, youtube_plugin):
        """Test DMCA content detection"""
        dmca_info = {
            'title': 'Official Music Video - VEVO',
            'uploader': 'Sony Music Entertainment'
        }
        
        is_dmca = await youtube_plugin._check_dmca(dmca_info)
        assert is_dmca is True
        
        safe_info = {
            'title': 'Tutorial Video',
            'uploader': 'Tech Channel'
        }
        
        is_dmca = await youtube_plugin._check_dmca(safe_info)
        assert is_dmca is False


class TestPluginManager:
    """Test plugin manager"""
    
    @pytest.fixture
    def plugin_manager(self):
        return PluginManager()
    
    def test_plugin_registration(self, plugin_manager):
        """Test plugin registration and priority"""
        mock_plugin1 = Mock()
        mock_plugin1.info.name = "plugin1"
        mock_plugin1.info.priority = 50
        
        mock_plugin2 = Mock()
        mock_plugin2.info.name = "plugin2"
        mock_plugin2.info.priority = 100
        
        plugin_manager.register(mock_plugin1)
        plugin_manager.register(mock_plugin2)
        
        # Higher priority should be first
        assert plugin_manager.plugins[0] == mock_plugin2
        assert plugin_manager.plugins[1] == mock_plugin1
    
    @pytest.mark.asyncio
    async def test_find_handler(self, plugin_manager):
        """Test finding appropriate handler for URL"""
        mock_plugin = Mock()
        mock_plugin.can_handle.return_value = True
        
        plugin_manager.register(mock_plugin)
        
        handler = await plugin_manager.find_handler("https://example.com")
        assert handler == mock_plugin
        mock_plugin.can_handle.assert_called_with("https://example.com")