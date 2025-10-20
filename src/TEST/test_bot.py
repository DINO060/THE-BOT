# ==================== tests/test_bot.py ====================
"""Bot functionality tests"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from telegram import Update, User, Message, Chat

from src.api.bot import ProductionBot


class TestProductionBot:
    """Test main bot functionality"""
    
    @pytest.fixture
    def bot(self):
        with patch('src.api.bot.settings') as mock_settings:
            mock_settings.bot_token = 'test_token'
            mock_settings.enable_monitoring = False
            return ProductionBot()
    
    @pytest.fixture
    def update(self):
        """Create mock update"""
        update = Mock(spec=Update)
        update.effective_user = Mock(spec=User)
        update.effective_user.id = 12345
        update.effective_user.username = "testuser"
        update.effective_user.first_name = "Test"
        update.effective_user.language_code = "en"
        
        update.message = Mock(spec=Message)
        update.message.text = "/start"
        update.message.reply_text = AsyncMock()
        
        update.effective_message = update.message
        
        return update
    
    @pytest.mark.asyncio
    async def test_start_command_new_user(self, bot, update):
        """Test /start command for new user"""
        context = Mock()
        context.user_data = {}
        
        with patch('src.api.bot.get_db') as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session
            mock_session.query.return_value.filter.return_value.first.return_value = None
            
            await bot.cmd_start(update, context)
            
            # Check that user was created
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()
            
            # Check welcome message was sent
            update.message.reply_text.assert_called_once()
            call_args = update.message.reply_text.call_args
            assert "Media Bot" in call_args[0][0]
    
    @pytest.mark.asyncio
    async def test_handle_youtube_url(self, bot, update):
        """Test handling YouTube URL"""
        update.message.text = "https://youtube.com/watch?v=test"
        context = Mock()
        context.user_data = {}
        
        with patch('src.api.bot.plugin_manager') as mock_pm:
            mock_plugin = Mock()
            mock_plugin.extract_info = AsyncMock(return_value={
                'title': 'Test Video',
                'duration': 120,
                'resolution': '1080p'
            })
            mock_pm.find_handler = AsyncMock(return_value=mock_plugin)
            
            await bot.handle_message(update, context)
            
            # Check that plugin was used
            mock_pm.find_handler.assert_called_with("https://youtube.com/watch?v=test")
            mock_plugin.extract_info.assert_called_once()
            
            # Check info was displayed
            update.message.reply_text.assert_called()