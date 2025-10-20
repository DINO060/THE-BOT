# ==================== src/core/security.py ====================
"""Security utilities: encryption, sanitization, rate limiting"""

import hashlib
import secrets
import re
import subprocess
import shlex
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from functools import wraps
import asyncio

from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext
import bleach
from redis import Redis
from telegram import Update
from telegram.ext import ContextTypes

from .config import settings
from .exceptions import RateLimitError, SecurityError


class SecurityManager:
    """Centralized security management"""
    
    def __init__(self):
        self.fernet = Fernet(settings.encryption_key.encode())
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True)
        
        # Compile regex patterns for efficiency
        self._sql_injection_pattern = re.compile(
            r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|CREATE|ALTER|EXEC|EXECUTE|SCRIPT|JAVASCRIPT)\b)",
            re.IGNORECASE
        )
        self._xss_pattern = re.compile(
            r"(<script|javascript:|onerror=|onclick=|<iframe|<embed|<object)",
            re.IGNORECASE
        )
        self._path_traversal_pattern = re.compile(r"\.\./|\.\\/")
        
    def encrypt(self, data: str) -> str:
        """Encrypt sensitive data"""
        return self.fernet.encrypt(data.encode()).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt sensitive data"""
        return self.fernet.decrypt(encrypted_data.encode()).decode()
    
    def hash_password(self, password: str) -> str:
        """Hash password with bcrypt"""
        return self.pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        return self.pwd_context.verify(plain_password, hashed_password)
    
    def create_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + (expires_delta or timedelta(hours=24))
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
            return payload
        except JWTError:
            return None
    
    def sanitize_input(self, input_str: str) -> str:
        """Sanitize user input against injection attacks"""
        if not input_str:
            return ""
        
        # Remove potential SQL injection
        if self._sql_injection_pattern.search(input_str):
            raise SecurityError("Potential SQL injection detected")
        
        # Remove potential XSS
        if self._xss_pattern.search(input_str):
            raise SecurityError("Potential XSS attack detected")
        
        # Remove path traversal
        if self._path_traversal_pattern.search(input_str):
            raise SecurityError("Path traversal attempt detected")
        
        # Clean HTML
        cleaned = bleach.clean(input_str, tags=[], strip=True)
        
        return cleaned[:1000]  # Limit length
    
    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe storage"""
        # Remove path components
        filename = os.path.basename(filename)
        
        # Keep only safe characters
        filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
        
        # Limit length
        name, ext = os.path.splitext(filename)
        if len(name) > 100:
            name = name[:100]
        
        return f"{name}{ext}"
    
    def safe_shell_command(self, cmd: str, args: List[str]) -> subprocess.CompletedProcess:
        """Execute shell command safely without injection"""
        # Never use shell=True
        # Always use argument list
        safe_cmd = [cmd] + [shlex.quote(arg) for arg in args]
        
        return subprocess.run(
            safe_cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False
        )
    
    def generate_secure_token(self, length: int = 32) -> str:
        """Generate cryptographically secure random token"""
        return secrets.token_urlsafe(length)
    
    def hash_file(self, file_path: str) -> str:
        """Generate SHA256 hash of file for integrity check"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()


class RateLimiter:
    """Redis-based rate limiter with sliding window"""
    
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
    
    def check_rate_limit(
        self,
        key: str,
        limit: int,
        window: int,
        identifier: str = ""
    ) -> bool:
        """
        Check if rate limit is exceeded
        
        Args:
            key: Rate limit key (e.g., "user:123")
            limit: Maximum number of requests
            window: Time window in seconds
            identifier: Optional request identifier for deduplication
        
        Returns:
            True if within limit, False if exceeded
        """
        now = datetime.utcnow().timestamp()
        pipeline = self.redis.pipeline()
        
        # Sliding window using sorted sets
        window_start = now - window
        redis_key = f"rate_limit:{key}"
        
        # Remove old entries
        pipeline.zremrangebyscore(redis_key, 0, window_start)
        
        # Count current entries
        pipeline.zcard(redis_key)
        
        # Add new entry if within limit
        if identifier:
            member = f"{now}:{identifier}"
        else:
            member = f"{now}:{secrets.token_hex(8)}"
        
        pipeline.zadd(redis_key, {member: now})
        
        # Set expiry
        pipeline.expire(redis_key, window + 60)
        
        results = pipeline.execute()
        current_count = results[1]
        
        return current_count < limit
    
    def reset_limit(self, key: str):
        """Reset rate limit for a key"""
        self.redis.delete(f"rate_limit:{key}")


def rate_limit(requests: int = 10, window: int = 60):
    """Decorator for rate limiting handlers"""
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.effective_user:
                return await func(update, context)
            
            user_id = update.effective_user.id
            redis_client = Redis.from_url(settings.redis_url)
            limiter = RateLimiter(redis_client)
            
            if not limiter.check_rate_limit(
                f"user:{user_id}",
                requests,
                window
            ):
                await update.message.reply_text(
                    f"⚠️ Rate limit exceeded. Please wait {window} seconds."
                )
                raise RateLimitError(f"User {user_id} exceeded rate limit")
            
            return await func(update, context)
        return wrapper
    return decorator