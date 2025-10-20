# 🎯 TODO PRIORITAIRE - Actions Immédiates

## ⚡ PHASE 1: CORRECTIONS CRITIQUES (Semaine 1)

### 1. Créer le fichier `.env.example`
```bash
# Telegram
BOT_TOKEN=your_bot_token_from_botfather
API_ID=your_api_id
API_HASH=your_api_hash
WEBHOOK_URL=https://your-domain.com

# Database
DATABASE_URL=postgresql://bot_user:${DB_PASSWORD}@postgres:5432/bot_db
DB_PASSWORD=your_secure_password_here
DB_POOL_SIZE=50
DB_MAX_OVERFLOW=100

# Redis
REDIS_URL=redis://default:${REDIS_PASSWORD}@redis:6379/0
REDIS_PASSWORD=your_redis_password
REDIS_POOL_SIZE=50
CACHE_TTL_SECONDS=3600

# Celery
CELERY_BROKER_URL=amqp://admin:${RABBITMQ_PASSWORD}@rabbitmq:5672//
CELERY_RESULT_BACKEND=redis://default:${REDIS_PASSWORD}@redis:6379/1
CELERY_TASK_TIMEOUT=3600
RABBITMQ_PASSWORD=your_rabbitmq_password

# Storage (MinIO/S3)
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=your_minio_secret
MINIO_BUCKET=media-files
MINIO_SECURE=false
MAX_FILE_SIZE_MB=2048

# Security
ENCRYPTION_KEY=  # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
JWT_SECRET_KEY=  # Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
JWT_ALGORITHM=HS256

# Rate Limiting
RATE_LIMIT_PER_USER=10/minute
RATE_LIMIT_GLOBAL=1000/minute

# Monitoring
SENTRY_DSN=
ELASTIC_URL=http://elasticsearch:9200
PROMETHEUS_PORT=9090
ENABLE_MONITORING=true

# Payment
STRIPE_API_KEY=
STRIPE_WEBHOOK_SECRET=
ENABLE_PAYMENT=false

# Features
ENABLE_CACHE=true
ENABLE_PLUGINS=true

# Environment
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
```

### 2. Corriger les imports manquants dans `bot.py`

**Ajouter au début du fichier:**
```python
import hashlib
import os
from src.core.exceptions import SecurityError
```

### 3. Créer `src/core/exceptions.py` (complet)

```python
"""Custom exceptions for the bot"""

class BotException(Exception):
    """Base exception for all bot errors"""
    pass


class RateLimitError(BotException):
    """Raised when rate limit is exceeded"""
    pass


class SecurityError(BotException):
    """Raised on security violations"""
    pass


class DownloadError(BotException):
    """Raised when download fails"""
    pass


class QuotaExceededError(BotException):
    """Raised when user quota is exceeded"""
    pass


class DMCAError(BotException):
    """Raised when content is DMCA protected"""
    pass


class PluginError(BotException):
    """Raised when plugin operation fails"""
    pass


class StorageError(BotException):
    """Raised when storage operation fails"""
    pass


class PaymentError(BotException):
    """Raised when payment processing fails"""
    pass


class ValidationError(BotException):
    """Raised when input validation fails"""
    pass
```

### 4. Compléter `src/SERVICES/storage.py`

```python
"""S3/MinIO storage service"""

import os
import logging
from typing import Optional
from pathlib import Path
import minio
from minio.error import S3Error

from src.core.config import settings
from src.core.exceptions import StorageError


class StorageService:
    """Handle file storage in S3/MinIO"""
    
    def __init__(self):
        self.client = minio.Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure
        )
        self.bucket = settings.minio_bucket
        self.logger = logging.getLogger(__name__)
        
        # Create bucket if not exists
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                self.logger.info(f"Created bucket: {self.bucket}")
        except S3Error as e:
            self.logger.error(f"Failed to create bucket: {e}")
    
    async def upload(self, file_path: str, s3_key: str) -> str:
        """Upload file to S3"""
        try:
            # Upload file
            self.client.fput_object(
                self.bucket,
                s3_key,
                file_path
            )
            
            # Generate presigned URL (valid for 7 days)
            url = self.client.presigned_get_object(
                self.bucket,
                s3_key,
                expires=timedelta(days=7)
            )
            
            self.logger.info(f"Uploaded {file_path} to {s3_key}")
            return url
            
        except S3Error as e:
            self.logger.error(f"Upload failed: {e}")
            raise StorageError(f"Failed to upload file: {e}")
    
    async def download(self, s3_key: str, output_path: str) -> bool:
        """Download file from S3"""
        try:
            self.client.fget_object(
                self.bucket,
                s3_key,
                output_path
            )
            return True
        except S3Error as e:
            self.logger.error(f"Download failed: {e}")
            return False
    
    async def delete(self, s3_key: str) -> bool:
        """Delete file from S3"""
        try:
            self.client.remove_object(self.bucket, s3_key)
            return True
        except S3Error as e:
            self.logger.error(f"Delete failed: {e}")
            return False
    
    async def exists(self, s3_key: str) -> bool:
        """Check if file exists"""
        try:
            self.client.stat_object(self.bucket, s3_key)
            return True
        except S3Error:
            return False
    
    async def get_url(self, s3_key: str, expires_days: int = 7) -> str:
        """Get presigned URL for file"""
        try:
            url = self.client.presigned_get_object(
                self.bucket,
                s3_key,
                expires=timedelta(days=expires_days)
            )
            return url
        except S3Error as e:
            raise StorageError(f"Failed to generate URL: {e}")


# Global storage service
storage_service = StorageService()
```

### 5. Ajouter la commande `/premium` dans `bot.py`

```python
@monitoring.track_performance("cmd_premium")
@rate_limit(requests=5, window=60)
async def cmd_premium(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Premium subscription command"""
    user_id = update.effective_user.id
    
    # Get user info
    async with get_db() as db:
        result = await db.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await update.message.reply_text("❌ User not found")
            return
    
    # Check if already premium
    if user.is_premium and user.premium_until and user.premium_until > datetime.utcnow():
        days_left = (user.premium_until - datetime.utcnow()).days
        await update.message.reply_text(
            f"⭐ Vous êtes déjà Premium!\n\n"
            f"Expire dans: {days_left} jours"
        )
        return
    
    # Show premium plans
    premium_text = """
⭐ <b>Passez à Premium!</b>

<b>🎁 Avantages Premium:</b>
• Quota illimité (vs 1GB/jour gratuit)
• Files jusqu'à 2GB (vs 100MB gratuit)
• Priorité de téléchargement
• Qualité maximale disponible
• Pas de publicité
• Cache étendu (7 jours vs 1 jour)
• Support prioritaire

<b>💰 Tarifs:</b>
• 4.99€/mois
• 49.99€/an (économisez 2 mois!)
• 9.99€ boost ponctuel (7 jours)

<b>💳 Paiement sécurisé par Stripe</b>
    """
    
    keyboard = [
        [
            InlineKeyboardButton(
                "💳 Mensuel (4.99€)", 
                callback_data="premium:buy:monthly"
            )
        ],
        [
            InlineKeyboardButton(
                "💳 Annuel (49.99€) 🔥", 
                callback_data="premium:buy:yearly"
            )
        ],
        [
            InlineKeyboardButton(
                "⚡ Boost 7j (9.99€)", 
                callback_data="premium:buy:boost"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Annuler", 
                callback_data="cancel"
            )
        ]
    ]
    
    await update.message.reply_text(
        premium_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
```

### 6. Ajouter la commande `/status` dans `bot.py`

```python
@monitoring.track_performance("cmd_status")
@rate_limit(requests=10, window=60)
async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check download status"""
    user_id = update.effective_user.id
    
    # Get task ID from arguments
    if context.args:
        task_id = context.args[0]
    else:
        # Show recent tasks
        async with get_db() as db:
            result = await db.execute(
                select(Task)
                .where(Task.user_id == user_id)
                .order_by(Task.created_at.desc())
                .limit(5)
            )
            tasks = result.scalars().all()
            
            if not tasks:
                await update.message.reply_text(
                    "📭 Aucun téléchargement en cours ou récent"
                )
                return
            
            # Format tasks list
            status_text = "📊 <b>Vos téléchargements récents:</b>\n\n"
            
            for task in tasks:
                status_emoji = {
                    TaskStatus.PENDING: "⏳",
                    TaskStatus.PROCESSING: "⚙️",
                    TaskStatus.COMPLETED: "✅",
                    TaskStatus.FAILED: "❌",
                    TaskStatus.CANCELLED: "🚫"
                }.get(task.status, "❓")
                
                status_text += (
                    f"{status_emoji} <code>{task.task_id[:8]}</code> - "
                    f"{task.status.value}\n"
                    f"Progress: {task.progress}%\n"
                )
                
                if task.status == TaskStatus.PROCESSING and task.eta:
                    eta_str = task.eta.strftime("%H:%M:%S")
                    status_text += f"ETA: {eta_str}\n"
                
                status_text += "\n"
            
            status_text += "\n💡 Utilisez `/status <task_id>` pour plus de détails"
            
            await update.message.reply_text(status_text, parse_mode="HTML")
            return
    
    # Get specific task status
    async with get_db() as db:
        result = await db.execute(
            select(Task).where(
                Task.task_id == task_id,
                Task.user_id == user_id
            )
        )
        task = result.scalar_one_or_none()
        
        if not task:
            await update.message.reply_text("❌ Task not found")
            return
    
    # Format detailed status
    status_emoji = {
        TaskStatus.PENDING: "⏳",
        TaskStatus.PROCESSING: "⚙️",
        TaskStatus.COMPLETED: "✅",
        TaskStatus.FAILED: "❌",
        TaskStatus.CANCELLED: "🚫"
    }.get(task.status, "❓")
    
    status_text = f"""
{status_emoji} <b>Status: {task.status.value.upper()}</b>

<b>📋 Details:</b>
• Task ID: <code>{task.task_id}</code>
• Type: {task.task_type}
• Progress: {task.progress}%
• Priority: {task.priority}

<b>⏱ Timing:</b>
• Created: {task.created_at.strftime("%Y-%m-%d %H:%M:%S")}
    """
    
    if task.started_at:
        status_text += f"• Started: {task.started_at.strftime('%H:%M:%S')}\n"
    
    if task.completed_at:
        duration = (task.completed_at - task.started_at).total_seconds()
        status_text += f"• Completed: {task.completed_at.strftime('%H:%M:%S')}\n"
        status_text += f"• Duration: {duration:.1f}s\n"
    
    if task.eta and task.status == TaskStatus.PROCESSING:
        status_text += f"• ETA: {task.eta.strftime('%H:%M:%S')}\n"
    
    if task.error_message:
        status_text += f"\n❌ <b>Error:</b> {task.error_message}\n"
    
    if task.output_data:
        status_text += f"\n✅ <b>Result available!</b>\n"
    
    keyboard = []
    if task.status == TaskStatus.COMPLETED and task.output_data:
        keyboard.append([
            InlineKeyboardButton(
                "📥 Télécharger", 
                url=task.output_data.get('url')
            )
        ])
    elif task.status == TaskStatus.PROCESSING:
        keyboard.append([
            InlineKeyboardButton(
                "❌ Annuler", 
                callback_data=f"task:cancel:{task.task_id}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("🔄 Refresh", callback_data=f"task:status:{task.task_id}")
    ])
    
    await update.message.reply_text(
        status_text,
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
        parse_mode="HTML"
    )
```

### 7. Créer les migrations Alembic

**Créer `migrations/env.py`:**
```python
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

from src.core.config import settings
from src.core.database import Base
from src.models.user import User
from src.models.media import MediaItem
from src.models.transaction import Transaction

# Alembic Config object
config = context.config

# Override sqlalchemy.url with our settings
config.set_main_option("sqlalchemy.url", settings.database_url)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**Créer la première migration:**
```bash
# Dans le terminal
cd migrations
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head
```

---

## ⚡ PHASE 2: FONCTIONNALITÉS ESSENTIELLES (Semaine 2)

### 8. Créer plugin Twitter/X

**Créer `src/plugins/twitter.py`:**
```python
"""Twitter/X plugin"""

import re
from typing import Dict, Any, Optional, Tuple
import httpx
from playwright.async_api import async_playwright

from src.plugins.base import BasePlugin, PluginInfo
from src.core.exceptions import DownloadError


class TwitterPlugin(BasePlugin):
    """Twitter/X media downloader"""
    
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="twitter",
            version="1.0.0",
            author="BotTeam",
            description="Twitter/X video and image downloader",
            supported_domains=["twitter.com", "x.com", "t.co"],
            supported_types=["video", "image", "gif"],
            priority=85
        )
    
    def can_handle(self, url: str) -> bool:
        """Check if URL is a Twitter link"""
        patterns = [
            r'(twitter\.com|x\.com)/\w+/status/\d+',
            r't\.co/\w+'
        ]
        
        for pattern in patterns:
            if re.search(pattern, url):
                return True
        return False
    
    async def extract_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract tweet information"""
        # Implementation using Twitter API or web scraping
        # This is a simplified version
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            try:
                await page.goto(url, wait_until='networkidle', timeout=30000)
                
                # Extract media URLs
                media_urls = await page.evaluate("""
                    () => {
                        const videos = Array.from(document.querySelectorAll('video')).map(v => v.src);
                        const images = Array.from(document.querySelectorAll('img[src*="media"]')).map(img => img.src);
                        return { videos, images };
                    }
                """)
                
                # Get tweet text
                tweet_text = await page.text_content('div[data-testid="tweetText"]')
                
                return {
                    'type': 'tweet',
                    'text': tweet_text,
                    'video_urls': media_urls['videos'],
                    'image_urls': media_urls['images'],
                    'has_media': bool(media_urls['videos'] or media_urls['images'])
                }
                
            finally:
                await browser.close()
    
    async def download(
        self,
        url: str,
        output_path: str,
        options: Dict[str, Any] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Download Twitter media"""
        info = await self.extract_info(url)
        
        if not info or not info['has_media']:
            return False, None, {"error": "No media found"}
        
        # Download first video or image
        media_url = info['video_urls'][0] if info['video_urls'] else info['image_urls'][0]
        
        async with httpx.AsyncClient() as client:
            response = await client.get(media_url)
            response.raise_for_status()
            
            ext = '.mp4' if 'video' in media_url else '.jpg'
            file_path = f"{output_path}{ext}"
            
            with open(file_path, 'wb') as f:
                f.write(response.content)
        
        return True, file_path, info
```

### 9. Créer task scheduler pour nettoyage cache

**Créer `src/Workers/schedulers/cleanup.py`:**
```python
"""Scheduled tasks for cleanup and maintenance"""

from datetime import datetime, timedelta
from sqlalchemy import select, and_
from celery import shared_task

from src.Workers.celery_app import celery_app
from src.core.database import get_db, MediaItem, User
from src.SERVICES.storage import storage_service
from src.core.cache import cache


@celery_app.task(name='cleanup.expired_cache')
def cleanup_expired_cache():
    """Delete expired cached files"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(_cleanup_expired_cache_async())
        return result
    finally:
        loop.close()


async def _cleanup_expired_cache_async():
    """Async cleanup of expired cache"""
    deleted_count = 0
    freed_bytes = 0
    
    async with get_db() as db:
        # Find expired media items
        result = await db.execute(
            select(MediaItem).where(
                MediaItem.cache_expires_at < datetime.utcnow(),
                MediaItem.is_available == True
            )
        )
        expired_items = result.scalars().all()
        
        for item in expired_items:
            try:
                # Delete from S3
                if item.s3_key:
                    await storage_service.delete(item.s3_key)
                    freed_bytes += item.file_size or 0
                
                # Mark as unavailable
                item.is_available = False
                deleted_count += 1
                
            except Exception as e:
                logging.error(f"Failed to delete {item.id}: {e}")
        
        await db.commit()
    
    # Clear Redis cache
    await cache.invalidate_pattern("downloads:*")
    
    freed_gb = freed_bytes / (1024 ** 3)
    return {
        "deleted": deleted_count,
        "freed_gb": round(freed_gb, 2)
    }


@celery_app.task(name='cleanup.reset_quotas')
def reset_daily_quotas():
    """Reset daily quotas for all users"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(_reset_quotas_async())
        return result
    finally:
        loop.close()


async def _reset_quotas_async():
    """Async quota reset"""
    async with get_db() as db:
        # Find users with expired quota period
        result = await db.execute(
            select(User).where(
                User.quota_reset_at < datetime.utcnow()
            )
        )
        users = result.scalars().all()
        
        reset_count = 0
        for user in users:
            user.daily_quota_used = 0
            user.quota_reset_at = datetime.utcnow() + timedelta(days=1)
            reset_count += 1
        
        await db.commit()
        
        return {"reset_users": reset_count}


@celery_app.task(name='cleanup.check_premium_expiry')
def check_premium_expiry():
    """Check and expire premium subscriptions"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(_check_premium_expiry_async())
        return result
    finally:
        loop.close()


async def _check_premium_expiry_async():
    """Async premium expiry check"""
    async with get_db() as db:
        # Find expired premium users
        result = await db.execute(
            select(User).where(
                User.is_premium == True,
                User.premium_until < datetime.utcnow()
            )
        )
        users = result.scalars().all()
        
        expired_count = 0
        for user in users:
            user.is_premium = False
            expired_count += 1
            
            # TODO: Send notification to user
            # await send_notification(user.telegram_id, "premium_expired")
        
        await db.commit()
        
        return {"expired_users": expired_count}
```

**Configurer les tâches périodiques dans `src/Workers/celery_app.py`:**
```python
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    'cleanup-expired-cache': {
        'task': 'cleanup.expired_cache',
        'schedule': crontab(hour='*/6'),  # Every 6 hours
    },
    'reset-daily-quotas': {
        'task': 'cleanup.reset_quotas',
        'schedule': crontab(hour=0, minute=0),  # Daily at midnight
    },
    'check-premium-expiry': {
        'task': 'cleanup.check_premium_expiry',
        'schedule': crontab(hour='*/1'),  # Every hour
    },
}
```

### 10. Créer tests unitaires de base

**Créer `src/TEST/unit/test_security.py`:**
```python
"""Tests for security module"""

import pytest
from src.core.security import SecurityManager, RateLimiter
from src.core.exceptions import SecurityError


@pytest.fixture
def security():
    return SecurityManager()


def test_sanitize_sql_injection(security):
    """Test SQL injection detection"""
    malicious_input = "'; DROP TABLE users; --"
    
    with pytest.raises(SecurityError):
        security.sanitize_input(malicious_input)


def test_sanitize_xss(security):
    """Test XSS detection"""
    malicious_input = "<script>alert('xss')</script>"
    
    with pytest.raises(SecurityError):
        security.sanitize_input(malicious_input)


def test_sanitize_path_traversal(security):
    """Test path traversal detection"""
    malicious_input = "../../etc/passwd"
    
    with pytest.raises(SecurityError):
        security.sanitize_input(malicious_input)


def test_sanitize_valid_input(security):
    """Test valid input passes through"""
    valid_input = "https://youtube.com/watch?v=abc123"
    result = security.sanitize_input(valid_input)
    
    assert result == valid_input


def test_encrypt_decrypt(security):
    """Test encryption/decryption"""
    data = "sensitive_data"
    
    encrypted = security.encrypt(data)
    assert encrypted != data
    
    decrypted = security.decrypt(encrypted)
    assert decrypted == data


def test_password_hashing(security):
    """Test password hashing and verification"""
    password = "MySecurePassword123!"
    
    hashed = security.hash_password(password)
    assert hashed != password
    
    assert security.verify_password(password, hashed)
    assert not security.verify_password("wrong_password", hashed)
```

**Créer `pytest.ini` à la racine:**
```ini
[pytest]
testpaths = src/TEST
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --tb=short
    --strict-markers
    --disable-warnings
markers =
    unit: Unit tests
    integration: Integration tests
    performance: Performance tests
```

---

## 🎯 CHECKLIST RAPIDE

### Fichiers à Créer
- [  ] `.env.example`
- [ ] `.env` (avec vos vraies clés)
- [ ] `src/core/exceptions.py` (complet)
- [ ] `src/SERVICES/storage.py` (complet)
- [ ] `migrations/env.py`
- [ ] `src/plugins/twitter.py`
- [ ] `src/Workers/schedulers/cleanup.py`
- [ ] `src/TEST/unit/test_security.py`
- [ ] `pytest.ini`

### Modifications à Faire
- [ ] Ajouter imports manquants dans `bot.py`
- [ ] Ajouter commande `/premium`
- [ ] Ajouter commande `/status`
- [ ] Ajouter commande `/settings`
- [ ] Configurer beat_schedule dans `celery_app.py`

### À Tester
- [ ] Connexion au bot Telegram
- [ ] Téléchargement simple YouTube
- [ ] Vérification quotas
- [ ] Flow premium (sans paiement réel)
- [ ] Storage S3/MinIO
- [ ] Rate limiting

### Commandes à Exécuter
```bash
# Installer dépendances
pip install -r requirements.txt

# Créer clés de sécurité
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Initialiser DB
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head

# Lancer services
docker-compose -f Dorkers/docker-compose.yml up -d

# Lancer bot
python main.py
```

---

**🎯 Une fois ces éléments complétés, votre bot sera fonctionnel à 90%!**

