# ==================== src/services/storage.py ====================
"""Object storage service using MinIO/S3"""

import os
import hashlib
from typing import Optional, Dict, Any, BinaryIO, List
from pathlib import Path
import asyncio
from datetime import datetime, timedelta

from minio import Minio
from minio.error import S3Error
import boto3
from botocore.exceptions import ClientError

from src.core.config import settings
from src.core.monitoring import monitoring, metrics
from src.core.exceptions import StorageError


class StorageService:
    """Unified storage service for S3-compatible object storage"""
    
    def __init__(self):
        self.client = None
        self.cdn_url = settings.cdn_url if hasattr(settings, 'cdn_url') else None
        self._setup_client()
    
    def _setup_client(self):
        """Initialize MinIO/S3 client"""
        try:
            self.client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure
            )
            
            # Ensure bucket exists
            if not self.client.bucket_exists(settings.minio_bucket):
                self.client.make_bucket(settings.minio_bucket)
                
                # Set bucket policy for public read (if using CDN)
                if self.cdn_url:
                    policy = {
                        "Version": "2012-10-17",
                        "Statement": [{
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": ["s3:GetObject"],
                            "Resource": f"arn:aws:s3:::{settings.minio_bucket}/*"
                        }]
                    }
                    self.client.set_bucket_policy(
                        settings.minio_bucket,
                        json.dumps(policy)
                    )
                    
        except Exception as e:
            raise StorageError(f"Failed to initialize storage: {e}")
    
    async def upload(
        self,
        file_path: str,
        object_name: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Upload file to object storage
        
        Args:
            file_path: Local file path
            object_name: Object name in storage (default: generated)
            metadata: Additional metadata
            
        Returns:
            Public URL or S3 key
        """
        if not os.path.exists(file_path):
            raise StorageError(f"File not found: {file_path}")
        
        # Generate object name if not provided
        if not object_name:
            file_hash = self._calculate_file_hash(file_path)
            ext = Path(file_path).suffix
            date_path = datetime.utcnow().strftime("%Y/%m/%d")
            object_name = f"{date_path}/{file_hash}{ext}"
        
        # Prepare metadata
        metadata = metadata or {}
        metadata['upload_timestamp'] = datetime.utcnow().isoformat()
        metadata['original_filename'] = os.path.basename(file_path)
        
        # Upload file
        loop = asyncio.get_event_loop()
        
        try:
            # Run blocking operation in thread pool
            await loop.run_in_executor(
                None,
                self._upload_file_sync,
                file_path,
                object_name,
                metadata
            )
            
            # Track metrics
            file_size = os.path.getsize(file_path)
            metrics.file_size.labels(media_type="upload").observe(file_size)
            
            # Return URL
            if self.cdn_url:
                return f"{self.cdn_url}/{object_name}"
            else:
                return self._get_presigned_url(object_name)
                
        except Exception as e:
            monitoring.track_error(e, {
                'file_path': file_path,
                'object_name': object_name
            })
            raise StorageError(f"Upload failed: {e}")
    
    def _upload_file_sync(
        self,
        file_path: str,
        object_name: str,
        metadata: Dict[str, str]
    ):
        """Synchronous file upload"""
        file_size = os.path.getsize(file_path)
        
        with open(file_path, 'rb') as file_data:
            self.client.put_object(
                settings.minio_bucket,
                object_name,
                file_data,
                file_size,
                metadata=metadata
            )
    
    async def upload_stream(
        self,
        data: BinaryIO,
        object_name: str,
        size: int,
        content_type: str = 'application/octet-stream',
        metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """Upload data stream to storage"""
        metadata = metadata or {}
        metadata['upload_timestamp'] = datetime.utcnow().isoformat()
        
        loop = asyncio.get_event_loop()
        
        try:
            await loop.run_in_executor(
                None,
                self.client.put_object,
                settings.minio_bucket,
                object_name,
                data,
                size,
                content_type,
                metadata
            )
            
            if self.cdn_url:
                return f"{self.cdn_url}/{object_name}"
            else:
                return self._get_presigned_url(object_name)
                
        except Exception as e:
            raise StorageError(f"Stream upload failed: {e}")
    
    async def download(
        self,
        object_name: str,
        file_path: str
    ) -> bool:
        """Download object from storage"""
        loop = asyncio.get_event_loop()
        
        try:
            await loop.run_in_executor(
                None,
                self.client.fget_object,
                settings.minio_bucket,
                object_name,
                file_path
            )
            return True
            
        except S3Error as e:
            if e.code == 'NoSuchKey':
                return False
            raise StorageError(f"Download failed: {e}")
    
    async def get_stream(self, object_name: str) -> Optional[bytes]:
        """Get object as bytes stream"""
        loop = asyncio.get_event_loop()
        
        try:
            response = await loop.run_in_executor(
                None,
                self.client.get_object,
                settings.minio_bucket,
                object_name
            )
            
            data = response.read()
            response.close()
            response.release_conn()
            
            return data
            
        except S3Error as e:
            if e.code == 'NoSuchKey':
                return None
            raise StorageError(f"Stream get failed: {e}")
    
    async def delete(self, object_name: str) -> bool:
        """Delete object from storage"""
        loop = asyncio.get_event_loop()
        
        try:
            await loop.run_in_executor(
                None,
                self.client.remove_object,
                settings.minio_bucket,
                object_name
            )
            return True
            
        except S3Error:
            return False
    
    async def exists(self, object_name: str) -> bool:
        """Check if object exists"""
        loop = asyncio.get_event_loop()
        
        try:
            await loop.run_in_executor(
                None,
                self.client.stat_object,
                settings.minio_bucket,
                object_name
            )
            return True
            
        except S3Error as e:
            if e.code == 'NoSuchKey':
                return False
            raise StorageError(f"Existence check failed: {e}")
    
    async def list_objects(
        self,
        prefix: str = "",
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """List objects with prefix"""
        loop = asyncio.get_event_loop()
        
        try:
            objects = await loop.run_in_executor(
                None,
                lambda: list(self.client.list_objects(
                    settings.minio_bucket,
                    prefix=prefix,
                    recursive=True
                ))
            )
            
            return [
                {
                    'name': obj.object_name,
                    'size': obj.size,
                    'last_modified': obj.last_modified,
                    'etag': obj.etag
                }
                for obj in objects[:limit]
            ]
            
        except Exception as e:
            raise StorageError(f"List objects failed: {e}")
    
    async def get_object_info(self, object_name: str) -> Optional[Dict[str, Any]]:
        """Get object metadata"""
        loop = asyncio.get_event_loop()
        
        try:
            stat = await loop.run_in_executor(
                None,
                self.client.stat_object,
                settings.minio_bucket,
                object_name
            )
            
            return {
                'size': stat.size,
                'last_modified': stat.last_modified,
                'etag': stat.etag,
                'content_type': stat.content_type,
                'metadata': stat.metadata
            }
            
        except S3Error as e:
            if e.code == 'NoSuchKey':
                return None
            raise StorageError(f"Get info failed: {e}")
    
    def _get_presigned_url(
        self,
        object_name: str,
        expiry: int = 3600
    ) -> str:
        """Generate presigned URL for temporary access"""
        try:
            return self.client.presigned_get_object(
                settings.minio_bucket,
                object_name,
                expires=timedelta(seconds=expiry)
            )
        except Exception as e:
            raise StorageError(f"Presigned URL generation failed: {e}")
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of file"""
        sha256_hash = hashlib.sha256()
        
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        
        return sha256_hash.hexdigest()
    
    async def cleanup_expired(self, days: int = 7) -> int:
        """Clean up old objects"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        deleted_count = 0
        
        objects = await self.list_objects()
        
        for obj in objects:
            if obj['last_modified'] < cutoff_date:
                await self.delete(obj['name'])
                deleted_count += 1
        
        return deleted_count


# Global storage service instance
storage_service = StorageService()

