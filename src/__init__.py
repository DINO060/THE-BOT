# ==================== src/__init__.py ====================
"""
Telegram Media Bot - Production Ready
A scalable, secure bot for downloading media from various platforms
"""

__version__ = "1.0.0"
__author__ = "BotTeam"
__license__ = "MIT"

from src.core.config import settings
from src.core.database import Base, get_db
from src.core.cache import cache
from src.core.monitoring import monitoring

__all__ = [
    'settings',
    'Base',
    'get_db',
    'cache',
    'monitoring',
]