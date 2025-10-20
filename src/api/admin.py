# ==================== src/api/admin.py ====================
"""Admin panel functionality for bot management"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.core.database import get_db, User, UserRole, MediaItem, Task, Transaction
from src.core.cache import cache
from src.core.monitoring import monitoring, metrics
from src.core.security import SecurityManager
from sqlalchemy import select, func, and_, or_


class AdminPanel:
    """Administrative functions for bot management"""
    
    def __init__(self):
        self.security = SecurityManager()
        
    async def check_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        async with get_db() as db:
            user = await db.query(User).filter(
                User.telegram_id == user_id,
                User.role == UserRole.ADMIN
            ).first()
            return user is not None
    
    async def show_dashboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show admin dashboard"""
        if not await self.check_admin(update.effective_user.id):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        # Get statistics
        stats = await self.get_statistics()
        
        dashboard_text = f"""
📊 <b>Admin Dashboard</b>

<b>👥 Users:</b>
• Total: {stats['total_users']:,}
• Active (24h): {stats['active_users']:,}
• Premium: {stats['premium_users']:,}
• Banned: {stats['banned_users']:,}

<b>📥 Downloads:</b>
• Today: {stats['downloads_today']:,}
• This Week: {stats['downloads_week']:,}
• Total: {stats['total_downloads']:,}
• Success Rate: {stats['success_rate']:.1f}%

<b>💾 Storage:</b>
• Used: {stats['storage_used_gb']:.1f} GB
• Files: {stats['total_files']:,}
• Cache Hit Rate: {stats['cache_hit_rate']:.1f}%

<b>💰 Revenue:</b>
• Today: ${stats['revenue_today']:.2f}
• This Month: ${stats['revenue_month']:.2f}
• MRR: ${stats['mrr']:.2f}

<b>🔧 System:</b>
• Uptime: {stats['uptime']}
• Queue Size: {stats['queue_size']}
• Error Rate: {stats['error_rate']:.2f}%
        """
        
        keyboard = [
            [
                InlineKeyboardButton("👥 Users", callback_data="admin:users"),
                InlineKeyboardButton("📊 Analytics", callback_data="admin:analytics"),
            ],
            [
                InlineKeyboardButton("📣 Broadcast", callback_data="admin:broadcast"),
                InlineKeyboardButton("🔧 Settings", callback_data="admin:settings"),
            ],
            [
                InlineKeyboardButton("🚫 Bans", callback_data="admin:bans"),
                InlineKeyboardButton("💾 Backup", callback_data="admin:backup"),
            ],
            [
                InlineKeyboardButton("📝 Logs", callback_data="admin:logs"),
                InlineKeyboardButton("🔄 Refresh", callback_data="admin:refresh"),
            ],
        ]
        
        await update.message.reply_text(
            dashboard_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        async with get_db() as db:
            # User statistics
            total_users = await db.scalar(
                select(func.count(User.id))
            )
            
            active_users = await db.scalar(
                select(func.count(User.id)).where(
                    User.last_active_at > datetime.utcnow() - timedelta(days=1)
                )
            )
            
            premium_users = await db.scalar(
                select(func.count(User.id)).where(
                    User.is_premium == True
                )
            )
            
            banned_users = await db.scalar(
                select(func.count(User.id)).where(
                    User.role == UserRole.BANNED
                )
            )
            
            # Download statistics
            downloads_today = await db.scalar(
                select(func.count(MediaItem.id)).where(
                    MediaItem.created_at > datetime.utcnow() - timedelta(days=1)
                )
            )
            
            downloads_week = await db.scalar(
                select(func.count(MediaItem.id)).where(
                    MediaItem.created_at > datetime.utcnow() - timedelta(days=7)
                )
            )
            
            total_downloads = await db.scalar(
                select(func.count(MediaItem.id))
            )
            
            # Success rate
            total_tasks = await db.scalar(
                select(func.count(Task.id)).where(
                    Task.created_at > datetime.utcnow() - timedelta(days=1)
                )
            ) or 1
            
            failed_tasks = await db.scalar(
                select(func.count(Task.id)).where(
                    Task.status == 'failed',
                    Task.created_at > datetime.utcnow() - timedelta(days=1)
                )
            ) or 0
            
            success_rate = ((total_tasks - failed_tasks) / total_tasks) * 100
            
            # Storage statistics
            storage_used = await db.scalar(
                select(func.sum(MediaItem.file_size))
            ) or 0
            
            storage_used_gb = storage_used / (1024 ** 3)
            
            total_files = await db.scalar(
                select(func.count(MediaItem.id))
            )
            
            # Revenue statistics
            revenue_today = await db.scalar(
                select(func.sum(Transaction.amount)).where(
                    Transaction.created_at > datetime.utcnow() - timedelta(days=1),
                    Transaction.status == 'completed'
                )
            ) or 0
            
            revenue_month = await db.scalar(
                select(func.sum(Transaction.amount)).where(
                    Transaction.created_at > datetime.utcnow() - timedelta(days=30),
                    Transaction.status == 'completed'
                )
            ) or 0
            
            # MRR calculation
            mrr = premium_users * 4.99  # Assuming $4.99/month
            
            # Cache statistics
            cache_stats = await cache.redis.info('stats')
            cache_hits = int(cache_stats.get('keyspace_hits', 0))
            cache_misses = int(cache_stats.get('keyspace_misses', 0))
            cache_total = cache_hits + cache_misses
            cache_hit_rate = (cache_hits / cache_total * 100) if cache_total > 0 else 0
            
            # Queue size
            queue_info = await cache.redis.llen('celery')
            
            # Uptime
            uptime_seconds = (datetime.utcnow() - datetime(2024, 1, 1)).total_seconds()
            uptime = self._format_uptime(uptime_seconds)
            
            # Error rate (from metrics)
            # This is simplified - in production you'd query Prometheus
            error_rate = 0.5  # Placeholder
            
            return {
                'total_users': total_users,
                'active_users': active_users,
                'premium_users': premium_users,
                'banned_users': banned_users,
                'downloads_today': downloads_today,
                'downloads_week': downloads_week,
                'total_downloads': total_downloads,
                'success_rate': success_rate,
                'storage_used_gb': storage_used_gb,
                'total_files': total_files,
                'cache_hit_rate': cache_hit_rate,
                'revenue_today': revenue_today,
                'revenue_month': revenue_month,
                'mrr': mrr,
                'uptime': uptime,
                'queue_size': queue_info,
                'error_rate': error_rate,
            }
    
    def _format_uptime(self, seconds: float) -> str:
        """Format uptime in human-readable format"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    
    async def manage_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """User management interface"""
        if not await self.check_admin(update.effective_user.id):
            return
        
        page = context.user_data.get('admin_users_page', 0)
        per_page = 10
        
        async with get_db() as db:
            # Get users with pagination
            users = await db.execute(
                select(User)
                .order_by(User.created_at.desc())
                .limit(per_page)
                .offset(page * per_page)
            )
            users = users.scalars().all()
            
            total_users = await db.scalar(select(func.count(User.id)))
            total_pages = (total_users + per_page - 1) // per_page
        
        # Format user list
        user_list = "👥 <b>User Management</b>\n\n"
        for user in users:
            role_emoji = {
                UserRole.ADMIN: "👑",
                UserRole.PREMIUM: "⭐",
                UserRole.USER: "👤",
                UserRole.BANNED: "🚫"
            }.get(user.role, "👤")
            
            user_list += (
                f"{role_emoji} <b>{user.first_name or 'Unknown'}</b> "
                f"(@{user.username or 'N/A'})\n"
                f"ID: <code>{user.telegram_id}</code>\n"
                f"Downloads: {user.total_downloads} | "
                f"Joined: {user.created_at.strftime('%Y-%m-%d')}\n\n"
            )
        
        user_list += f"Page {page + 1}/{total_pages}"
        
        # Navigation buttons
        keyboard = []
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"admin:users:page:{page-1}"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin:users:page:{page+1}"))
        
        if nav_row:
            keyboard.append(nav_row)
        
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin:dashboard")])
        
        await update.callback_query.edit_message_text(
            user_list,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    
    async def broadcast_message(
        self,
        message: str,
        target: str = "all",
        test_mode: bool = True
    ) -> Dict[str, int]:
        """Broadcast message to users"""
        async with get_db() as db:
            # Build query based on target
            query = select(User.telegram_id)
            
            if target == "premium":
                query = query.where(User.is_premium == True)
            elif target == "active":
                query = query.where(
                    User.last_active_at > datetime.utcnow() - timedelta(days=7)
                )
            elif target == "inactive":
                query = query.where(
                    User.last_active_at < datetime.utcnow() - timedelta(days=30)
                )
            
            # Exclude banned users
            query = query.where(User.role != UserRole.BANNED)
            
            if test_mode:
                query = query.limit(10)  # Send to only 10 users in test mode
            
            users = await db.execute(query)
            user_ids = [user_id for user_id, in users]
        
        # Send messages
        sent = 0
        failed = 0
        
        from telegram import Bot
        from src.core.config import settings
        bot = Bot(settings.bot_token)
        
        for user_id in user_ids:
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode="HTML"
                )
                sent += 1
                
                # Rate limiting
                if sent % 30 == 0:
                    await asyncio.sleep(1)
                    
            except Exception as e:
                failed += 1
                monitoring.track_error(e, {"user_id": user_id, "broadcast": True})
        
        return {"sent": sent, "failed": failed, "total": len(user_ids)}
    
    async def ban_user(self, user_id: int, reason: str = None) -> bool:
        """Ban a user"""
        async with get_db() as db:
            user = await db.query(User).filter(
                User.telegram_id == user_id
            ).first()
            
            if user:
                user.role = UserRole.BANNED
                user.settings = user.settings or {}
                user.settings['ban_reason'] = reason
                user.settings['banned_at'] = datetime.utcnow().isoformat()
                await db.commit()
                
                # Clear user cache
                await cache.delete('users', str(user_id))
                
                # Log action
                await monitoring.log_event(
                    'user_banned',
                    {'user_id': user_id, 'reason': reason},
                    level='warning'
                )
                
                return True
        return False
    
    async def unban_user(self, user_id: int) -> bool:
        """Unban a user"""
        async with get_db() as db:
            user = await db.query(User).filter(
                User.telegram_id == user_id
            ).first()
            
            if user and user.role == UserRole.BANNED:
                user.role = UserRole.USER
                user.settings = user.settings or {}
                user.settings.pop('ban_reason', None)
                user.settings.pop('banned_at', None)
                await db.commit()
                
                # Clear user cache
                await cache.delete('users', str(user_id))
                
                return True
        return False
    
    async def export_data(self, data_type: str = "users") -> str:
        """Export data as CSV"""
        import csv
        import io
        
        async with get_db() as db:
            if data_type == "users":
                users = await db.execute(select(User))
                users = users.scalars().all()
                
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(['ID', 'Username', 'Name', 'Role', 'Premium', 'Downloads', 'Created'])
                
                for user in users:
                    writer.writerow([
                        user.telegram_id,
                        user.username or 'N/A',
                        f"{user.first_name or ''} {user.last_name or ''}".strip(),
                        user.role.value,
                        user.is_premium,
                        user.total_downloads,
                        user.created_at.isoformat()
                    ])
                
                return output.getvalue()
            
            elif data_type == "transactions":
                transactions = await db.execute(select(Transaction))
                transactions = transactions.scalars().all()
                
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(['ID', 'User', 'Amount', 'Currency', 'Status', 'Created'])
                
                for trans in transactions:
                    writer.writerow([
                        trans.transaction_id,
                        trans.user_id,
                        trans.amount,
                        trans.currency,
                        trans.status,
                        trans.created_at.isoformat()
                    ])
                
                return output.getvalue()
