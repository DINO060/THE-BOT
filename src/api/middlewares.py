# ==================== src/api/middlewares.py ====================
"""Bot middlewares for authentication, logging, and error handling"""

import time
import logging
from typing import Any, Dict, Optional
from datetime import datetime

from telegram import Update
from telegram.ext import BaseHandler, ContextTypes

from src.core.database import get_db, User, UserRole
from src.core.monitoring import monitoring, metrics
from src.core.cache import cache
from src.core.exceptions import BotException


class AuthenticationMiddleware(BaseHandler):
    """Authenticate and authorize users"""
    
    def __init__(self):
        super().__init__(self.callback)
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check user authentication and authorization"""
        if not update.effective_user:
            return
        
        user_id = update.effective_user.id
        
        # Check cache first
        cached_user = await cache.get('users', str(user_id))
        
        if cached_user:
            context.user_data['db_user'] = cached_user
            return
        
        # Get from database
        async with get_db() as db:
            user = await db.query(User).filter(
                User.telegram_id == user_id
            ).first()
            
            if user:
                # Check if banned
                if user.role == UserRole.BANNED:
                    if update.message:
                        await update.message.reply_text(
                            "❌ Your account has been banned. Contact support for assistance."
                        )
                    raise PermissionError("User is banned")
                
                # Update last active
                user.last_active_at = datetime.utcnow()
                await db.commit()
                
                # Cache user data
                user_data = {
                    'id': user.id,
                    'telegram_id': user.telegram_id,
                    'username': user.username,
                    'role': user.role.value,
                    'is_premium': user.is_premium,
                    'language_code': user.language_code,
                }
                
                await cache.set('users', str(user_id), user_data, ttl=300)
                context.user_data['db_user'] = user_data
    
    def check_handlers(self, update: Update) -> bool:
        """Check if update should be handled"""
        return update.effective_user is not None


class LoggingMiddleware(BaseHandler):
    """Log all interactions for analytics"""
    
    def __init__(self):
        super().__init__(self.callback)
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Log interaction details"""
        if not update.effective_user:
            return
        
        # Extract interaction data
        interaction = {
            'user_id': update.effective_user.id,
            'username': update.effective_user.username,
            'timestamp': datetime.utcnow().isoformat(),
            'update_type': update.to_dict().get('update_id'),
        }
        
        if update.message:
            interaction['message_type'] = 'text' if update.message.text else 'other'
            interaction['message_length'] = len(update.message.text or '')
            
            # Log command if present
            if update.message.text and update.message.text.startswith('/'):
                command = update.message.text.split()[0]
                interaction['command'] = command
                metrics.requests_total.labels(
                    handler=command,
                    status='received'
                ).inc()
        
        elif update.callback_query:
            interaction['callback_data'] = update.callback_query.data
            metrics.requests_total.labels(
                handler='callback',
                status='received'
            ).inc()
        
        # Log to monitoring
        await monitoring.log_event(
            'user_interaction',
            interaction,
            user_id=update.effective_user.id,
            level='info'
        )
        
        # Store in context for later use
        context.user_data['interaction_start'] = time.time()
    
    def check_handlers(self, update: Update) -> bool:
        """Always handle for logging"""
        return True


class ErrorHandlingMiddleware(BaseHandler):
    """Global error handling middleware"""
    
    def __init__(self):
        super().__init__(self.callback)
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors globally"""
        try:
            # This middleware doesn't do anything in the callback
            # It's used for the error handler
            pass
        except Exception as e:
            await self.handle_error(update, context, e)
    
    async def handle_error(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        error: Exception
    ):
        """Handle different error types"""
        self.logger.error(f"Error occurred: {error}", exc_info=True)
        
        # Track error
        monitoring.track_error(error, {
            'update': update.to_dict() if update else None,
            'user_id': update.effective_user.id if update and update.effective_user else None,
        })
        
        # Increment error metric
        metrics.errors_total.labels(
            error_type=type(error).__name__,
            handler=context.user_data.get('current_handler', 'unknown')
        ).inc()
        
        # Send user-friendly error message
        if update and update.effective_message:
            if isinstance(error, BotException):
                # Custom bot exceptions with user-friendly messages
                await update.effective_message.reply_text(
                    f"⚠️ {str(error)}"
                )
            elif isinstance(error, PermissionError):
                await update.effective_message.reply_text(
                    "❌ You don't have permission to perform this action."
                )
            elif isinstance(error, ValueError):
                await update.effective_message.reply_text(
                    "❌ Invalid input. Please check and try again."
                )
            elif isinstance(error, TimeoutError):
                await update.effective_message.reply_text(
                    "⏱ Operation timed out. Please try again."
                )
            else:
                # Generic error message
                await update.effective_message.reply_text(
                    "❌ An unexpected error occurred. Our team has been notified.\n"
                    f"Error ID: {context.error_id if hasattr(context, 'error_id') else 'N/A'}"
                )
        
        # Log interaction completion time
        if 'interaction_start' in context.user_data:
            duration = time.time() - context.user_data['interaction_start']
            metrics.request_duration.labels(
                handler=context.user_data.get('current_handler', 'unknown')
            ).observe(duration)
    
    def check_handlers(self, update: Update) -> bool:
        """Always handle for error catching"""
        return True


class RateLimitMiddleware(BaseHandler):
    """Rate limiting middleware using Redis"""
    
    def __init__(self, requests_per_minute: int = 30):
        super().__init__(self.callback)
        self.requests_per_minute = requests_per_minute
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check rate limits"""
        if not update.effective_user:
            return
        
        user_id = update.effective_user.id
        
        # Check rate limit
        key = f"rate_limit:{user_id}"
        current = await cache.redis.incr(key)
        
        if current == 1:
            # Set expiry on first request
            await cache.redis.expire(key, 60)
        
        if current > self.requests_per_minute:
            # Rate limit exceeded
            metrics.errors_total.labels(
                error_type='RateLimitExceeded',
                handler='middleware'
            ).inc()
            
            if update.message:
                await update.message.reply_text(
                    f"⚠️ Rate limit exceeded. Maximum {self.requests_per_minute} requests per minute.\n"
                    "Please wait before trying again."
                )
            
            raise PermissionError("Rate limit exceeded")
    
    def check_handlers(self, update: Update) -> bool:
        """Check all updates with effective user"""
        return update.effective_user is not None