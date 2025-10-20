# ==================== tests/test_storage.py ====================
"""Storage service tests"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os

from src.services.storage import StorageService
from src.core.exceptions import StorageError


class TestStorageService:
    """Test storage service"""
    
    @pytest.fixture
    def storage_service(self):
        with patch('src.services.storage.settings') as mock_settings:
            mock_settings.minio_endpoint = 'localhost:9000'
            mock_settings.minio_access_key = 'test_access'
            mock_settings.minio_secret_key = 'test_secret'
            mock_settings.minio_secure = False
            mock_settings.minio_bucket = 'test-bucket'
            mock_settings.cdn_url = None
            
            with patch('src.services.storage.Minio') as mock_minio:
                mock_client = MagicMock()
                mock_minio.return_value = mock_client
                mock_client.bucket_exists.return_value = True
                
                service = StorageService()
                service.client = mock_client
                return service
    
    @pytest.mark.asyncio
    async def test_upload_file(self, storage_service):
        """Test file upload"""
        # Create temp file
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"test content")
            tmp_path = tmp.name
        
        try:
            result = await storage_service.upload(tmp_path, "test/file.txt")
            
            # Check that upload was called
            storage_service.client.put_object.assert_called()
            
            # Check return value format
            assert isinstance(result, str)
            
        finally:
            os.unlink(tmp_path)
    
    @pytest.mark.asyncio
    async def test_upload_nonexistent_file(self, storage_service):
        """Test uploading non-existent file raises error"""
        with pytest.raises(StorageError):
            await storage_service.upload("/nonexistent/file.txt")
    
    @pytest.mark.asyncio
    async def test_exists_check(self, storage_service):
        """Test checking if object exists"""
        storage_service.client.stat_object.return_value = Mock()
        
        exists = await storage_service.exists("test/file.txt")
        assert exists is True
        
        from minio.error import S3Error
        storage_service.client.stat_object.side_effect = S3Error(
            code='NoSuchKey',
            message='',
            resource='',
            request_id='',
            host_id='',
            response=Mock(status=404)
        )
        
        exists = await storage_service.exists("nonexistent.txt")
        assert exists is False
    
    def test_file_hash_calculation(self, storage_service):
        """Test file hash calculation"""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"test content")
            tmp_path = tmp.name
        
        try:
            hash1 = storage_service._calculate_file_hash(tmp_path)
            hash2 = storage_service._calculate_file_hash(tmp_path)
            
            # Hash should be consistent
            assert hash1 == hash2
            assert len(hash1) == 64  # SHA256 hex length
            
        finally:
            os.unlink(tmp_path)