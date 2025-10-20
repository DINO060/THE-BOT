 ==================== src/models/transaction.py ====================
"""Transaction model for payments"""

from sqlalchemy import Column, Integer, BigInteger, String, Float, DateTime, JSON, ForeignKey, Enum as SQLEnum
from datetime import datetime
import enum

from src.core.database import Base


class TransactionStatus(enum.Enum):
    """Transaction status enumeration"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class Transaction(Base):
    """Payment transaction model"""
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    
    # Transaction info
    transaction_id = Column(String(255), unique=True)
    payment_method = Column(String(50))
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="USD")
    
    # Status
    status = Column(SQLEnum(TransactionStatus), default=TransactionStatus.PENDING)
    stripe_payment_intent_id = Column(String(255))
    
    # Metadata
    metadata = Column(JSON)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Transaction(id={self.transaction_id}, amount={self.amount}, status={self.status})>"
