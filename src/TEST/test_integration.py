# ==================== tests/test_integration.py ====================
"""Integration tests for complete workflow"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta
import tempfile
import os

from src.api.bot import ProductionBot
from src.core.database import get_db, User, MediaItem, UserRole
from src.plugins.youtube import YouTubePlugin
from src.workers.tasks.download import process_media_download
from src.services.storage import storage_service


class TestEndToEndWorkflow:
    """Test complete download workflow"""
    
    @pytest.fixture
    async def setup_test_user(self):
        """Create test user in database"""
        async with get_db() as db:
            user = User(
                telegram_id=12345,
                username="testuser",
                first_name="Test",
                last_name="User",
                role=UserRole.USER,
                quota_reset_at=datetime.utcnow() + timedelta(days=1)
            )
            db.add(user)
            await db.commit()
            yield user
            # Cleanup
            await db.delete(user)
            await db.commit()
    
    @pytest.mark.asyncio
    async def test_complete_download_workflow(self, setup_test_user):
        """Test complete workflow from URL to download"""
        user = setup_test_user
        test_url = "https://youtube.com/watch?v=test"
        
        # Mock plugin
        with patch('src.plugins.base.plugin_manager') as mock_pm:
            mock_plugin = Mock(spec=YouTubePlugin)
            mock_plugin.extract_info = AsyncMock(return_value={
                'title': 'Test Video',
                'duration': 120,
                'filesize': 10485760  # 10MB
            })
            mock_plugin.download = AsyncMock(return_value=(
                True,
                '/tmp/test.mp4',
                {'title': 'Test Video', 'duration': 120}
            ))
            mock_pm.find_handler = AsyncMock(return_value=mock_plugin)
            
            # Mock storage
            with patch.object(storage_service, 'upload') as mock_upload:
                mock_upload.return_value = 'https://cdn.example.com/test.mp4'
                
                # Process download
                with patch('src.workers.tasks.download.get_db', return_value=AsyncMock()):
                    result = await process_media_download(
                        user.id,
                        test_url,
                        'video',
                        {}
                    )
                
                # Verify result
                assert result['success'] is True
                assert 'url' in result
                assert result['metadata']['title'] == 'Test Video'
    
    @pytest.mark.asyncio
    async def test_quota_enforcement(self, setup_test_user):
        """Test user quota is enforced"""
        user = setup_test_user
        
        async with get_db() as db:
            # Set user quota to exceeded
            db_user = await db.get(User, user.id)
            db_user.daily_quota_used = 1001  # Exceeds 1000 MB limit
            await db.commit()
        
        # Try to download
        with pytest.raises(QuotaExceededError):
            await process_media_download(
                user.id,
                "https://youtube.com/watch?v=test",
                'video',
                {}
            )
    
    @pytest.mark.asyncio
    async def test_cache_hit_workflow(self):
        """Test that cached downloads are returned immediately"""
        test_url = "https://youtube.com/watch?v=cached"
        url_hash = hashlib.sha256(test_url.encode()).hexdigest()
        
        # Pre-populate cache
        cached_result = {
            'success': True,
            'url': 'https://cdn.example.com/cached.mp4',
            's3_key': 'videos/2024/01/01/cached.mp4',
            'file_size': 5242880,
            'metadata': {'title': 'Cached Video'}
        }
        
        from src.core.cache import cache
        await cache.set('downloads', url_hash, cached_result)
        
        # Mock storage exists check
        with patch.object(storage_service, 'exists') as mock_exists:
            mock_exists.return_value = True
            
            # Process download
            result = await process_media_download(
                12345,
                test_url,
                'video',
                {}
            )
            
            # Should return cached result
            assert result == cached_result
            
            # Storage existence should be checked
            mock_exists.assert_called_once_with('videos/2024/01/01/cached.mp4')


class TestPaymentIntegration:
    """Test payment processing"""
    
    @pytest.mark.asyncio
    async def test_stripe_webhook_processing(self):
        """Test Stripe webhook handling"""
        from src.services.payment import PaymentService
        
        payment_service = PaymentService()
        
        # Mock webhook payload
        webhook_payload = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "metadata": {
                        "user_id": "12345",
                        "plan": "premium_monthly"
                    },
                    "amount_total": 499,
                    "currency": "usd",
                    "payment_intent": "pi_test_123"
                }
            }
        }
        
        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_construct.return_value = webhook_payload
            
            with patch('src.services.payment.get_db') as mock_db:
                mock_session = AsyncMock()
                mock_db.return_value.__aenter__.return_value = mock_session
                
                mock_user = Mock()
                mock_user.id = 1
                mock_user.telegram_id = 12345
                mock_session.query.return_value.filter.return_value.first.return_value = mock_user
                
                # Process webhook
                result = await payment_service.handle_webhook(
                    b'payload',
                    'sig_header'
                )
                
                assert result is True
                
                # Check user was upgraded
                assert mock_user.is_premium is True
                assert mock_user.premium_until is not None


class TestAdminFunctions:
    """Test admin panel functionality"""
    
    @pytest.fixture
    def admin_panel(self):
        from src.api.admin import AdminPanel
        return AdminPanel()
    
    @pytest.mark.asyncio
    async def test_admin_statistics(self, admin_panel):
        """Test statistics gathering"""
        with patch('src.api.admin.get_db') as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session
            
            # Mock query results
            mock_session.scalar = AsyncMock()
            mock_session.scalar.side_effect = [
                100,  # total_users
                50,   # active_users
                10,   # premium_users
                2,    # banned_users
                25,   # downloads_today
                150,  # downloads_week
                1000, # total_downloads
                100,  # total_tasks
                5,    # failed_tasks
                1073741824,  # storage_used (1GB)
                500,  # total_files
                99.99,  # revenue_today
                2999.70,  # revenue_month
            ]
            
            # Mock cache stats
            with patch('src.core.cache.cache.redis.info') as mock_info:
                mock_info.return_value = {
                    'keyspace_hits': '8000',
                    'keyspace_misses': '2000'
                }
                
                with patch('src.core.cache.cache.redis.llen') as mock_llen:
                    mock_llen.return_value = 15
                    
                    stats = await admin_panel.get_statistics()
                    
                    assert stats['total_users'] == 100
                    assert stats['active_users'] == 50
                    assert stats['premium_users'] == 10
                    assert stats['success_rate'] == 95.0
                    assert stats['storage_used_gb'] == 1.0
                    assert stats['cache_hit_rate'] == 80.0
    
    @pytest.mark.asyncio
    async def test_broadcast_message(self, admin_panel):
        """Test message broadcasting"""
        with patch('src.api.admin.get_db') as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session
            
            # Mock users query
            mock_session.execute = AsyncMock()
            mock_session.execute.return_value = [(123,), (456,), (789,)]
            
            with patch('telegram.Bot') as mock_bot_class:
                mock_bot = Mock()
                mock_bot_class.return_value = mock_bot
                mock_bot.send_message = AsyncMock()
                
                result = await admin_panel.broadcast_message(
                    "Test broadcast",
                    target="all",
                    test_mode=True
                )
                
                assert result['total'] == 3
                assert mock_bot.send_message.call_count == 3

