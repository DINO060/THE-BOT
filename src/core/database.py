# ==================== src/core/database.py ====================
"""Database models and connection management"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from datetime import datetime
import enum

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, Text, ForeignKey, Index, Enum, JSON, BigInteger
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship, selectinload
from sqlalchemy.pool import NullPool

from .config import settings

# Async engine for PostgreSQL
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
    poolclass=NullPool if settings.environment == "test" else None
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()


class UserRole(enum.Enum):
    """User roles enumeration"""
    USER = "user"
    PREMIUM = "premium"
    ADMIN = "admin"
    BANNED = "banned"


class MediaType(enum.Enum):
    """Media type enumeration"""
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    DOCUMENT = "document"
    MANGA = "manga"


class TaskStatus(enum.Enum):
    """Task status enumeration"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class User(Base):
    """User model with enhanced security and tracking"""
    __tablename__ = "users"
    
    id = Column(BigInteger, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), index=True)
    first_name = Column(String(255))
    last_name = Column(String(255))
    language_code = Column(String(10), default="en")
    
    # Security
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    encrypted_data = Column(Text)  # For sensitive data
    
    # Subscription
    is_premium = Column(Boolean, default=False)
    premium_until = Column(DateTime)
    stripe_customer_id = Column(String(255))
    
    # Usage tracking
    total_downloads = Column(Integer, default=0)
    total_bytes = Column(BigInteger, default=0)
    daily_quota_used = Column(Float, default=0)
    quota_reset_at = Column(DateTime)
    
    # Preferences
    preferences = Column(JSON, default=dict)
    settings = Column(JSON, default=dict)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_active_at = Column(DateTime)
    
    # Relationships
    media_items = relationship("MediaItem", back_populates="user", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index("ix_user_role_active", role, is_active),
        Index("ix_user_premium", is_premium, premium_until),
    )


class MediaItem(Base):
    """Media item with caching and metadata"""
    __tablename__ = "media_items"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    
    # Media info
    url = Column(Text, nullable=False, index=True)
    url_hash = Column(String(64), index=True)  # SHA256 of URL for fast lookup
    media_type = Column(Enum(MediaType), nullable=False)
    
    # File info
    file_path = Column(Text)
    s3_key = Column(String(512))
    file_size = Column(BigInteger)
    file_hash = Column(String(64))  # For deduplication
    
    # Metadata
    title = Column(Text)
    description = Column(Text)
    duration = Column(Integer)  # In seconds
    resolution = Column(String(20))
    metadata = Column(JSON)
    
    # Cache management
    cached_at = Column(DateTime)
    cache_expires_at = Column(DateTime)
    access_count = Column(Integer, default=0)
    last_accessed_at = Column(DateTime)
    
    # Status
    is_available = Column(Boolean, default=True)
    is_dmca_flagged = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="media_items")
    
    # Indexes
    __table_args__ = (
        Index("ix_media_url_hash", url_hash),
        Index("ix_media_file_hash", file_hash),
        Index("ix_media_cache", cached_at, cache_expires_at),
    )


class Task(Base):
    """Background task tracking"""
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True)
    task_id = Column(String(255), unique=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    
    # Task info
    task_type = Column(String(50), nullable=False)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, index=True)
    priority = Column(Integer, default=0)
    
    # Input/Output
    input_data = Column(JSON)
    output_data = Column(JSON)
    error_message = Column(Text)
    
    # Progress
    progress = Column(Float, default=0)
    eta = Column(DateTime)
    
    # Timing
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    # Relationships
    user = relationship("User", back_populates="tasks")
    
    # Indexes
    __table_args__ = (
        Index("ix_task_status_priority", status, priority),
    )


class Transaction(Base):
    """Payment transactions"""
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    
    # Transaction info
    transaction_id = Column(String(255), unique=True)
    payment_method = Column(String(50))
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="USD")
    
    # Status
    status = Column(String(50))
    stripe_payment_intent_id = Column(String(255))
    
    # Metadata
    metadata = Column(JSON)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="transactions")


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()