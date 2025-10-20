# ==================== tests/test_security.py ====================
"""Security tests"""

import pytest
from unittest.mock import Mock, patch
import subprocess

from src.core.security import SecurityManager, RateLimiter
from src.core.exceptions import SecurityError


class TestSecurityManager:
    """Test security functionality"""
    
    @pytest.fixture
    def security_manager(self):
        with patch('src.core.security.settings') as mock_settings:
            mock_settings.encryption_key = 'test_key_padded_to_32_bytes_____'
            mock_settings.jwt_secret_key = 'test_secret'
            mock_settings.jwt_algorithm = 'HS256'
            mock_settings.redis_url = 'redis://localhost'
            return SecurityManager()
    
    def test_sql_injection_detection(self, security_manager):
        """Test SQL injection detection"""
        malicious_inputs = [
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "admin' --",
            "' UNION SELECT * FROM passwords",
        ]
        
        for malicious_input in malicious_inputs:
            with pytest.raises(SecurityError):
                security_manager.sanitize_input(malicious_input)
    
    def test_xss_detection(self, security_manager):
        """Test XSS detection"""
        xss_inputs = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "javascript:alert('XSS')",
            "<iframe src='evil.com'></iframe>",
        ]
        
        for xss_input in xss_inputs:
            with pytest.raises(SecurityError):
                security_manager.sanitize_input(xss_input)
    
    def test_path_traversal_detection(self, security_manager):
        """Test path traversal detection"""
        traversal_inputs = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "file://../../secret.txt",
        ]
        
        for traversal_input in traversal_inputs:
            with pytest.raises(SecurityError):
                security_manager.sanitize_input(traversal_input)
    
    def test_safe_input_sanitization(self, security_manager):
        """Test that safe inputs pass through"""
        safe_inputs = [
            "Hello World",
            "user@example.com",
            "https://youtube.com/watch?v=123",
            "This is a normal message",
        ]
        
        for safe_input in safe_inputs:
            result = security_manager.sanitize_input(safe_input)
            assert result == safe_input
    
    def test_filename_sanitization(self, security_manager):
        """Test filename sanitization"""
        test_cases = [
            ("../../../etc/passwd", "etc_passwd"),
            ("file<>name.txt", "file__name.txt"),
            ("very" * 100 + ".txt", "very" * 25 + ".txt"),  # Length limit
            ("normal_file.mp4", "normal_file.mp4"),
        ]
        
        for input_name, expected in test_cases:
            result = security_manager.sanitize_filename(input_name)
            assert len(result.split('.')[0]) <= 100
    
    def test_safe_shell_command(self, security_manager):
        """Test safe command execution"""
        # This should not allow injection
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout='', stderr=''
            )
            
            security_manager.safe_shell_command(
                'ffmpeg',
                ['-i', 'file; rm -rf /', 'output.mp4']
            )
            
            # Check that dangerous characters were escaped
            called_args = mock_run.call_args[0][0]
            assert 'rm' not in ' '.join(called_args)


class TestRateLimiter:
    """Test rate limiting"""
    
    @pytest.fixture
    def rate_limiter(self):
        mock_redis = Mock()
        return RateLimiter(mock_redis)
    
    @pytest.mark.asyncio
    async def test_rate_limit_allows_under_limit(self, rate_limiter):
        """Test that requests under limit are allowed"""
        rate_limiter.redis.pipeline.return_value.execute.return_value = [None, 5, None, None]
        
        result = rate_limiter.check_rate_limit("user:123", 10, 60)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_rate_limit_blocks_over_limit(self, rate_limiter):
        """Test that requests over limit are blocked"""
        rate_limiter.redis.pipeline.return_value.execute.return_value = [None, 11, None, None]
        
        result = rate_limiter.check_rate_limit("user:123", 10, 60)
        assert result is False



