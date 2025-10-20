# ==================== src/core/__init__.py ====================
"""Core functionality package"""

from src.core.config import settings
from src.core.database import Base, get_db, engine, AsyncSessionLocal
from src.core.cache import cache, CacheManager
from src.core.security import SecurityManager, RateLimiter
from src.core.monitoring import monitoring, metrics
from src.core.exceptions import (
    BotException,
    ConfigurationError,
    DatabaseError,
    CacheError,
    RateLimitError,
    SecurityError,
    ValidationError,
    MediaError,
    DownloadError,
    ConversionError,
    StorageError,
    PaymentError,
    PluginError,
    DMCAError,
    QuotaExceededError,
    TaskError
)

__all__ = [
    # Config
    'settings',
    
    # Database
    'Base',
    'get_db',
    'engine',
    'AsyncSessionLocal',
    
    # Cache
    'cache',
    'CacheManager',
    
    # Security
    'SecurityManager',
    'RateLimiter',
    
    # Monitoring
    'monitoring',
    'metrics',
    
    # Exceptions
    'BotException',
    'ConfigurationError',
    'DatabaseError',
    'CacheError',
    'RateLimitError',
    'SecurityError',
    'ValidationError',
    'MediaError',
    'DownloadError',
    'ConversionError',
    'StorageError',
    'PaymentError',
    'PluginError',
    'DMCAError',
    'QuotaExceededError',
    'TaskError',
]