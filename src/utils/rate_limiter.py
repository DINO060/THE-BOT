# ==================== src/utils/rate_limiter.py ====================
"""Rate limiting utilities"""

from functools import wraps
import asyncio
from typing import Callable

from src.core.security import RateLimiter
from src.core.cache import cache
from src.core.exceptions import RateLimitError


def rate_limit_decorator(requests: int = 10, window: int = 60):
    """Decorator for rate limiting functions"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get user ID from context
            user_id = kwargs.get('user_id') or (args[0] if args else None)
            
            if user_id:
                limiter = RateLimiter(cache.redis)
                
                if not limiter.check_rate_limit(
                    f"func:{func.__name__}:{user_id}",
                    requests,
                    window
                ):
                    raise RateLimitError(
                        f"Rate limit exceeded for {func.__name__}"
                    )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator