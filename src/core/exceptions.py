# ==================== src/core/exceptions.py ====================
"""Custom exceptions for better error handling"""


class BotException(Exception):
    """Base exception for all bot errors"""
    pass


class ConfigurationError(BotException):
    """Configuration related errors"""
    pass


class DatabaseError(BotException):
    """Database operation errors"""
    pass


class CacheError(BotException):
    """Cache operation errors"""
    pass


class RateLimitError(BotException):
    """Rate limit exceeded error"""
    pass


class SecurityError(BotException):
    """Security violation error"""
    pass


class ValidationError(BotException):
    """Input validation error"""
    pass


class MediaError(BotException):
    """Media processing error"""
    pass


class DownloadError(MediaError):
    """Download failure"""
    pass


class ConversionError(MediaError):
    """Media conversion error"""
    pass


class StorageError(BotException):
    """Storage operation error"""
    pass


class PaymentError(BotException):
    """Payment processing error"""
    pass


class PluginError(BotException):
    """Plugin operation error"""
    pass


class DMCAError(BotException):
    """DMCA/Legal compliance error"""
    pass


class QuotaExceededError(BotException):
    """User quota exceeded"""
    pass


class TaskError(BotException):
    """Background task error"""
    pass
