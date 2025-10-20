# ==================== src/models/user.py ====================
"""User model definition"""

from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, Text, JSON, Float, Enum as SQLEnum
from datetime import datetime
import enum

from src.core.database import Base


class UserRole(enum.Enum):
    """User roles enumeration"""
    USER = "user"
    PREMIUM = "premium"
    ADMIN = "admin"
    BANNED = "banned"


class User(Base):
    """User model with enhanced features"""
    __tablename__ = "users"
    
    id = Column(BigInteger, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), index=True)
    first_name = Column(String(255))
    last_name = Column(String(255))
    language_code = Column(String(10), default="en")
    
    # Security
    role = Column(SQLEnum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    encrypted_data = Column(Text)
    
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
    
    def __repr__(self):
        return f"<User(id={self.telegram_id}, username={self.username})>"

