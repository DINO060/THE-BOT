# ==================== src/api/bot.py ====================
"""Main bot implementation with all security and features"""

import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.error import TelegramError

from src.core.config import settings
from src.core.database import get_db, User, UserRole
from src.core.cache import cache
from src.core.security import SecurityManager, RateLimiter, rate_limit
from src.core.monitoring import monitoring, metrics
from src.core.exceptions import BotException, RateLimitError
from src.plugins.base import plugin_manager
from src.workers.tasks.download import process_media_download
from src.utils.i18n import I18n
from src.services.payment import PaymentService
from src.api.middlewares import (
    AuthenticationMiddleware,
    LoggingMiddleware,
    ErrorHandlingMiddleware
)


class ProductionBot:
    """Production-ready Telegram bot with all features"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.app = None
        self.security = SecurityManager()
        self.rate_limiter = RateLimiter(cache.redis)
        self.i18n = I18n()
        self.payment_service = PaymentService()
        
    async def setup(self):
        """Initialize bot with all components"""
        # Create application
        self.app = Application.builder().token(settings.bot_token).build()
        
        # Add middlewares
        self.app.add_handler(AuthenticationMiddleware())
        self.app.add_handler(LoggingMiddleware())
        self.app.add_handler(ErrorHandlingMiddleware())
        
        # Register handlers
        self._register_handlers()
        
        # Initialize plugins
        await self._load_plugins()
        
        # Start monitoring
        if settings.enable_monitoring:
            asyncio.create_task(self._export_metrics())
        
        self.logger.info("Bot setup completed")
    
    def _register_handlers(self):
        """Register all command and message handlers"""
        # Commands
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("download", self.cmd_download))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("settings", self.cmd_settings))
        self.app.add_handler(CommandHandler("premium", self.cmd_premium))
        self.app.add_handler(CommandHandler("cancel", self.cmd_cancel))
        
        # Admin commands
        self.app.add_handler(CommandHandler("admin", self.cmd_admin))
        self.app.add_handler(CommandHandler("broadcast", self.cmd_broadcast))
        self.app.add_handler(CommandHandler("stats", self.cmd_stats))
        self.app.add_handler(CommandHandler("ban", self.cmd_ban))
        self.app.add_handler(CommandHandler("unban", self.cmd_unban))
        
        # Message handlers
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_message
        ))
        self.app.add_handler(MessageHandler(
            filters.Document.ALL,
            self.handle_document
        ))
        
        # Callback queries
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Error handler
        self.app.add_error_handler(self.handle_error)
    
    async def _load_plugins(self):
        """Load and register all plugins"""
        from src.plugins.youtube import YouTubePlugin
        from src.plugins.instagram import InstagramPlugin
        from src.plugins.tiktok import TikTokPlugin
        
        # Register plugins
        plugin_manager.register(YouTubePlugin())
        plugin_manager.register(InstagramPlugin())
        plugin_manager.register(TikTokPlugin())
        
        self.logger.info(f"Loaded {len(plugin_manager.plugins)} plugins")
    
    @monitoring.track_performance("cmd_start")
    @rate_limit(requests=5, window=60)
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        user = update.effective_user
        
        # Get or create user in database
        async with get_db() as db:
            db_user = await db.query(User).filter(
                User.telegram_id == user.id
            ).first()
            
            if not db_user:
                db_user = User(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    language_code=user.language_code or "en",
                    quota_reset_at=datetime.utcnow() + timedelta(days=1)
                )
                db.add(db_user)
                await db.commit()
                metrics.active_users.inc()
            else:
                db_user.last_active_at = datetime.utcnow()
                await db.commit()
        
        # Get localized welcome message
        lang = db_user.language_code
        welcome_text = self.i18n.get(lang, "welcome_message").format(
            name=user.first_name,
            bot_name="Media Bot"
        )
        
        # Create inline keyboard
        keyboard = [
            [
                InlineKeyboardButton(
                    self.i18n.get(lang, "btn_download"),
                    callback_data="menu:download"
                ),
                InlineKeyboardButton(
                    self.i18n.get(lang, "btn_help"),
                    callback_data="menu:help"
                ),
            ],
            [
                InlineKeyboardButton(
                    self.i18n.get(lang, "btn_settings"),
                    callback_data="menu:settings"
                ),
                InlineKeyboardButton(
                    self.i18n.get(lang, "btn_premium"),
                    callback_data="menu:premium"
                ),
            ],
        ]
        
        if db_user.role == UserRole.ADMIN:
            keyboard.append([
                InlineKeyboardButton(
                    "🔧 Admin Panel",
                    callback_data="menu:admin"
                )
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        
        # Track metrics
        metrics.requests_total.labels(handler="start", status="success").inc()
    
    @monitoring.track_performance("handle_message")
    @rate_limit(requests=10, window=60)
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages (URLs)"""
        message = update.message.text
        user_id = update.effective_user.id
        
        # Sanitize input
        try:
            message = self.security.sanitize_input(message)
        except SecurityError as e:
            await update.message.reply_text(
                "⚠️ Security violation detected. This incident has been logged."
            )
            monitoring.track_error(e, {"user_id": user_id, "message": message})
            return
        
        # Check if it's a URL
        if not message.startswith(("http://", "https://")):
            await update.message.reply_text(
                self.i18n.get(
                    await self._get_user_language(user_id),
                    "invalid_input"
                )
            )
            return
        
        # Find plugin that can handle this URL
        plugin = await plugin_manager.find_handler(message)
        
        if not plugin:
            supported_domains = ", ".join(plugin_manager.get_supported_domains())
            await update.message.reply_text(
                f"❌ URL not supported.\n\n"
                f"Supported domains: {supported_domains}"
            )
            return
        
        # Extract media info
        status_msg = await update.message.reply_text("🔍 Analyzing URL...")
        
        try:
            info = await plugin.extract_info(message)
            
            if not info:
                await status_msg.edit_text("❌ Failed to extract media information")
                return
            
            # Create download options
            keyboard = [
                [
                    InlineKeyboardButton(
                        f"📥 Download ({info.get('format', 'Best')})",
                        callback_data=f"dl:{user_id}:{hashlib.md5(message.encode()).hexdigest()[:8]}"
                    )
                ]
            ]
            
            if info.get('duration'):
                keyboard.append([
                    InlineKeyboardButton(
                        "🎵 Extract Audio",
                        callback_data=f"audio:{user_id}:{hashlib.md5(message.encode()).hexdigest()[:8]}"
                    )
                ])
            
            keyboard.append([
                InlineKeyboardButton(
                    "❌ Cancel",
                    callback_data="cancel"
                )
            ])
            
            # Store URL in cache for callback
            await cache.set(
                "pending_downloads",
                f"{user_id}:{hashlib.md5(message.encode()).hexdigest()[:8]}",
                {
                    "url": message,
                    "info": info,
                    "plugin": plugin.info.name
                },
                ttl=300
            )
            
            # Format info message
            info_text = f"<b>{info.get('title', 'Unknown')}</b>\n\n"
            
            if info.get('duration'):
                info_text += f"⏱ Duration: {info['duration']}s\n"
            if info.get('resolution'):
                info_text += f"📺 Resolution: {info['resolution']}\n"
            if info.get('filesize'):
                info_text += f"📦 Size: {info['filesize'] / 1024 / 1024:.1f} MB\n"
            
            await status_msg.edit_text(
                info_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
            
        except Exception as e:
            await status_msg.edit_text(f"❌ Error: {str(e)}")
            monitoring.track_error(e, {"url": message, "user_id": user_id})
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = query.from_user.id
        
        if data == "cancel":
            await query.message.delete()
            return
        
        if data.startswith("dl:"):
            # Process download
            _, original_user_id, url_hash = data.split(":")
            
            if int(original_user_id) != user_id:
                await query.answer("This is not your download!", show_alert=True)
                return
            
            # Get URL from cache
            cache_key = f"{user_id}:{url_hash}"
            download_data = await cache.get("pending_downloads", cache_key)
            
            if not download_data:
                await query.answer("Download expired. Please try again.", show_alert=True)
                await query.message.delete()
                return
            
            # Check user quota
            async with get_db() as db:
                user = await db.query(User).filter(
                    User.telegram_id == user_id
                ).first()
                
                quota_limit = 10000 if user.is_premium else 1000  # MB
                if user.daily_quota_used >= quota_limit:
                    await query.message.edit_text(
                        "⚠️ Daily quota exceeded!\n\n"
                        "Upgrade to Premium for unlimited downloads."
                    )
                    return
            
            # Start download task
            task = process_media_download.delay(
                user_id,
                download_data['url'],
                'video',
                {}
            )
            
            await query.message.edit_text(
                f"⏳ Download started!\n\n"
                f"Task ID: <code>{task.id}</code>\n"
                f"You will be notified when complete.",
                parse_mode="HTML"
            )
            
            # Store task ID for tracking
            await cache.set(
                "user_tasks",
                f"{user_id}:{task.id}",
                {
                    "task_id": task.id,
                    "url": download_data['url'],
                    "started_at": datetime.utcnow().isoformat()
                },
                ttl=3600
            )
    
    async def _get_user_language(self, user_id: int) -> str:
        """Get user's preferred language"""
        async with get_db() as db:
            user = await db.query(User).filter(
                User.telegram_id == user_id
            ).first()
            return user.language_code if user else "en"
    
    async def _export_metrics(self):
        """Export Prometheus metrics periodically"""
        while True:
            try:
                # Update gauge metrics
                async with get_db() as db:
                    active_users = await db.query(User).filter(
                        User.last_active_at > datetime.utcnow() - timedelta(days=1)
                    ).count()
                    metrics.active_users.set(active_users)
                
                # Export to file or push gateway
                metrics_data = metrics.export()
                
                # You can send this to Prometheus push gateway
                # or save to file for scraping
                
            except Exception as e:
                self.logger.error(f"Metrics export failed: {e}")
            
            await asyncio.sleep(60)  # Every minute
    
    async def handle_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Global error handler"""
        error = context.error
        
        # Log to monitoring
        monitoring.track_error(error, {
            "update": update.to_dict() if update else None,
            "context": str(context)
        })
        
        # Send user-friendly error message
        if update and update.effective_message:
            if isinstance(error, RateLimitError):
                await update.effective_message.reply_text(
                    "⚠️ You're sending too many requests. Please wait a moment."
                )
            elif isinstance(error, TelegramError):
                await update.effective_message.reply_text(
                    "❌ Telegram error occurred. Please try again."
                )
            else:
                await update.effective_message.reply_text(
                    "❌ An unexpected error occurred. Our team has been notified."
                )
    
    async def run(self):
        """Run the bot"""
        await self.setup()
        
        # Use webhooks in production
        if settings.is_production and settings.webhook_url:
            await self.app.run_webhook(
                listen="0.0.0.0",
                port=8000,
                url_path=settings.bot_token,
                webhook_url=f"{settings.webhook_url}/{settings.bot_token}"
            )
        else:
            # Use polling for development
            await self.app.run_polling(allowed_updates=Update.ALL_TYPES)


