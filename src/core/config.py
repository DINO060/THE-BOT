# ==================== src/core/config.py ====================
"""Configuration centralisée avec validation Pydantic"""

from typing import Optional, Dict, Any, List
from pydantic_settings import BaseSettings
from pydantic import Field, validator
import os
from pathlib import Path
from functools import lru_cache


class Settings(BaseSettings):
    """Configuration avec validation et type hints"""
    
    # Environment
    environment: str = Field(default="production", env="ENVIRONMENT")
    debug: bool = Field(default=False, env="DEBUG")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    # Telegram
    bot_token: str = Field(..., env="BOT_TOKEN")
    api_id: int = Field(..., env="API_ID")
    api_hash: str = Field(..., env="API_HASH")
    webhook_url: Optional[str] = Field(None, env="WEBHOOK_URL")
    
    # Database
    database_url: str = Field(..., env="DATABASE_URL")
    db_pool_size: int = Field(default=20, env="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=40, env="DB_MAX_OVERFLOW")
    
    # Redis
    redis_url: str = Field(..., env="REDIS_URL")
    redis_pool_size: int = Field(default=50, env="REDIS_POOL_SIZE")
    cache_ttl: int = Field(default=3600, env="CACHE_TTL_SECONDS")
    
    # Celery
    celery_broker_url: str = Field(..., env="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="redis://", env="CELERY_RESULT_BACKEND")
    celery_task_timeout: int = Field(default=3600, env="CELERY_TASK_TIMEOUT")
    
    # Storage
    minio_endpoint: str = Field(..., env="MINIO_ENDPOINT")
    minio_access_key: str = Field(..., env="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(..., env="MINIO_SECRET_KEY")
    minio_bucket: str = Field(default="media-files", env="MINIO_BUCKET")
    minio_secure: bool = Field(default=False, env="MINIO_SECURE")
    max_file_size_mb: int = Field(default=2048, env="MAX_FILE_SIZE_MB")
    
    # Security
    encryption_key: str = Field(..., env="ENCRYPTION_KEY")
    jwt_secret_key: str = Field(..., env="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    
    # Rate Limiting
    rate_limit_per_user: str = Field(default="10/minute", env="RATE_LIMIT_PER_USER")
    rate_limit_global: str = Field(default="1000/minute", env="RATE_LIMIT_GLOBAL")
    
    # Monitoring
    sentry_dsn: Optional[str] = Field(None, env="SENTRY_DSN")
    elastic_url: Optional[str] = Field(None, env="ELASTIC_URL")
    prometheus_port: int = Field(default=9090, env="PROMETHEUS_PORT")
    
    # Payment
    stripe_api_key: Optional[str] = Field(None, env="STRIPE_API_KEY")
    stripe_webhook_secret: Optional[str] = Field(None, env="STRIPE_WEBHOOK_SECRET")
    
    # Legal/DMCA
    dmca_email: str = Field(default="dmca@example.com", env="DMCA_EMAIL")
    content_blacklist_file: str = Field(default="blacklist.txt", env="CONTENT_BLACKLIST")
    
    # Features
    enable_cache: bool = Field(default=True, env="ENABLE_CACHE")
    enable_monitoring: bool = Field(default=True, env="ENABLE_MONITORING")
    enable_payment: bool = Field(default=False, env="ENABLE_PAYMENT")
    enable_plugins: bool = Field(default=True, env="ENABLE_PLUGINS")
    
    # Paths
    data_dir: Path = Field(default=Path("data"), env="DATA_DIR")
    temp_dir: Path = Field(default=Path("/tmp/bot"), env="TEMP_DIR")
    
    @validator("data_dir", "temp_dir", pre=True)
    def create_directories(cls, v):
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @validator("rate_limit_per_user", "rate_limit_global")
    def validate_rate_limit(cls, v):
        """Validate rate limit format: number/interval"""
        parts = v.split("/")
        if len(parts) != 2:
            raise ValueError(f"Invalid rate limit format: {v}")
        try:
            int(parts[0])
        except ValueError:
            raise ValueError(f"Invalid rate limit number: {parts[0]}")
        if parts[1] not in ["second", "minute", "hour", "day"]:
            raise ValueError(f"Invalid rate limit interval: {parts[1]}")
        return v
    
    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024
    
    @property
    def is_production(self) -> bool:
        return self.environment == "production"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


settings = get_settings()
