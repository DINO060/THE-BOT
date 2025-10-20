# ==================== src/core/cache.py ====================
"""Advanced caching system with Redis"""

import json
import hashlib
import pickle
from typing import Optional, Any, Union, Dict, List
from datetime import datetime, timedelta
import asyncio

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from .config import settings
from .monitoring import metrics


class CacheManager:
    """Advanced cache manager with multiple strategies"""
    
    def __init__(self):
        self.redis = None
        self.connect_task = None
    
    async def connect(self):
        """Establish Redis connection"""
        if self.redis is None:
            self.redis = await aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=False,
                max_connections=settings.redis_pool_size
            )
    
    async def disconnect(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
    
    def _make_key(self, namespace: str, key: str) -> str:
        """Generate cache key with namespace"""
        return f"cache:{namespace}:{key}"
    
    def _hash_key(self, key: str) -> str:
        """Hash long keys to prevent Redis key size issues"""
        if len(key) > 200:
            return hashlib.sha256(key.encode()).hexdigest()
        return key
    
    async def get(
        self,
        namespace: str,
        key: str,
        default: Any = None
    ) -> Any:
        """Get value from cache"""
        if not settings.enable_cache:
            return default
        
        await self.connect()
        cache_key = self._make_key(namespace, self._hash_key(key))
        
        try:
            value = await self.redis.get(cache_key)
            if value is None:
                metrics.cache_misses.inc()
                return default
            
            metrics.cache_hits.inc()
            
            # Try JSON first, then pickle
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return pickle.loads(value)
                
        except RedisError as e:
            metrics.cache_errors.inc()
            return default
    
    async def set(
        self,
        namespace: str,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """Set value in cache"""
        if not settings.enable_cache:
            return False
        
        await self.connect()
        cache_key = self._make_key(namespace, self._hash_key(key))
        ttl = ttl or settings.cache_ttl
        
        try:
            # Try JSON first for better debugging
            try:
                serialized = json.dumps(value)
            except (TypeError, ValueError):
                serialized = pickle.dumps(value)
            
            await self.redis.setex(cache_key, ttl, serialized)
            metrics.cache_sets.inc()
            return True
            
        except RedisError as e:
            metrics.cache_errors.inc()
            return False
    
    async def delete(self, namespace: str, key: str) -> bool:
        """Delete value from cache"""
        await self.connect()
        cache_key = self._make_key(namespace, self._hash_key(key))
        
        try:
            result = await self.redis.delete(cache_key)
            return bool(result)
        except RedisError:
            return False
    
    async def exists(self, namespace: str, key: str) -> bool:
        """Check if key exists in cache"""
        await self.connect()
        cache_key = self._make_key(namespace, self._hash_key(key))
        
        try:
            return bool(await self.redis.exists(cache_key))
        except RedisError:
            return False
    
    async def get_or_set(
        self,
        namespace: str,
        key: str,
        factory_fn,
        ttl: Optional[int] = None
    ) -> Any:
        """Get from cache or compute and cache"""
        value = await self.get(namespace, key)
        if value is not None:
            return value
        
        # Compute value
        if asyncio.iscoroutinefunction(factory_fn):
            value = await factory_fn()
        else:
            value = factory_fn()
        
        # Cache it
        await self.set(namespace, key, value, ttl)
        return value
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching pattern"""
        await self.connect()
        
        try:
            cursor = b'0'
            deleted = 0
            
            while cursor:
                cursor, keys = await self.redis.scan(
                    cursor,
                    match=f"cache:{pattern}",
                    count=100
                )
                
                if keys:
                    deleted += await self.redis.delete(*keys)
                
                if cursor == b'0':
                    break
            
            return deleted
            
        except RedisError:
            return 0
    
    async def get_ttl(self, namespace: str, key: str) -> int:
        """Get TTL of cached key"""
        await self.connect()
        cache_key = self._make_key(namespace, self._hash_key(key))
        
        try:
            ttl = await self.redis.ttl(cache_key)
            return max(0, ttl)
        except RedisError:
            return 0
    
    async def extend_ttl(self, namespace: str, key: str, ttl: int) -> bool:
        """Extend TTL of cached key"""
        await self.connect()
        cache_key = self._make_key(namespace, self._hash_key(key))
        
        try:
            return bool(await self.redis.expire(cache_key, ttl))
        except RedisError:
            return False


# Global cache instance
cache = CacheManager()