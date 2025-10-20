# ==================== src/models/media.py ====================
"""Media item model definition"""

from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, Text, JSON, Float, ForeignKey, Enum as SQLEnum
from datetime import datetime
import enum

from src.core.database import Base


class MediaType(enum.Enum):
    """Media type enumeration"""
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    DOCUMENT = "document"
    MANGA = "manga"


class MediaItem(Base):
    """Media item with metadata and caching"""
    __tablename__ = "media_items"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    
    # Media info
    url = Column(Text, nullable=False, index=True)
    url_hash = Column(String(64), index=True)
    media_type = Column(SQLEnum(MediaType), nullable=False)
    
    # File info
    file_path = Column(Text)
    s3_key = Column(String(512))
    file_size = Column(BigInteger)
    file_hash = Column(String(64))
    
    # Metadata
    title = Column(Text)
    description = Column(Text)
    duration = Column(Integer)
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
    
    def __repr__(self):
        return f"<MediaItem(id={self.id}, type={self.media_type}, title={self.title})>"
