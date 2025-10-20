# ==================== migrations/versions/001_initial.py ====================
# ==================== migrations/versions/001_initial.py ====================
"""Initial migration

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial tables"""
    
    # Create enum types
    op.execute("CREATE TYPE userrole AS ENUM ('user', 'premium', 'admin', 'banned')")
    op.execute("CREATE TYPE mediatype AS ENUM ('video', 'audio', 'image', 'document', 'manga')")
    op.execute("CREATE TYPE taskstatus AS ENUM ('pending', 'processing', 'completed', 'failed', 'cancelled')")
    
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(255)),
        sa.Column('first_name', sa.String(255)),
        sa.Column('last_name', sa.String(255)),
        sa.Column('language_code', sa.String(10), default='en'),
        sa.Column('role', postgresql.ENUM('user', 'premium', 'admin', 'banned', name='userrole'), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('encrypted_data', sa.Text()),
        sa.Column('is_premium', sa.Boolean(), default=False),
        sa.Column('premium_until', sa.DateTime()),
        sa.Column('stripe_customer_id', sa.String(255)),
        sa.Column('total_downloads', sa.Integer(), default=0),
        sa.Column('total_bytes', sa.BigInteger(), default=0),
        sa.Column('daily_quota_used', sa.Float(), default=0),
        sa.Column('quota_reset_at', sa.DateTime()),
        sa.Column('preferences', sa.JSON(), default=dict),
        sa.Column('settings', sa.JSON(), default=dict),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('last_active_at', sa.DateTime()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('telegram_id')
    )
    
    # Create indexes
    op.create_index('ix_users_telegram_id', 'users', ['telegram_id'])
    op.create_index('ix_users_username', 'users', ['username'])
    op.create_index('ix_user_role_active', 'users', ['role', 'is_active'])
    op.create_index('ix_user_premium', 'users', ['is_premium', 'premium_until'])
    
    # Create media_items table
    op.create_table(
        'media_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger()),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('url_hash', sa.String(64)),
        sa.Column('media_type', postgresql.ENUM('video', 'audio', 'image', 'document', 'manga', name='mediatype'), nullable=False),
        sa.Column('file_path', sa.Text()),
        sa.Column('s3_key', sa.String(512)),
        sa.Column('file_size', sa.BigInteger()),
        sa.Column('file_hash', sa.String(64)),
        sa.Column('title', sa.Text()),
        sa.Column('description', sa.Text()),
        sa.Column('duration', sa.Integer()),
        sa.Column('resolution', sa.String(20)),
        sa.Column('metadata', sa.JSON()),
        sa.Column('cached_at', sa.DateTime()),
        sa.Column('cache_expires_at', sa.DateTime()),
        sa.Column('access_count', sa.Integer(), default=0),
        sa.Column('last_accessed_at', sa.DateTime()),
        sa.Column('is_available', sa.Boolean(), default=True),
        sa.Column('is_dmca_flagged', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_media_url_hash', 'media_items', ['url_hash'])
    op.create_index('ix_media_file_hash', 'media_items', ['file_hash'])
    op.create_index('ix_media_cache', 'media_items', ['cached_at', 'cache_expires_at'])
    op.create_index('ix_media_user', 'media_items', ['user_id'])
    
    # Create tasks table
    op.create_table(
        'tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.String(255), nullable=False),
        sa.Column('user_id', sa.BigInteger()),
        sa.Column('task_type', sa.String(50), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'processing', 'completed', 'failed', 'cancelled', name='taskstatus'), default='pending'),
        sa.Column('priority', sa.Integer(), default=0),
        sa.Column('input_data', sa.JSON()),
        sa.Column('output_data', sa.JSON()),
        sa.Column('error_message', sa.Text()),
        sa.Column('progress', sa.Float(), default=0),
        sa.Column('eta', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('started_at', sa.DateTime()),
        sa.Column('completed_at', sa.DateTime()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('task_id')
    )
    
    # Create indexes
    op.create_index('ix_task_status_priority', 'tasks', ['status', 'priority'])
    op.create_index('ix_task_user', 'tasks', ['user_id'])
    op.create_index('ix_task_created', 'tasks', ['created_at'])
    
    # Create transactions table
    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger()),
        sa.Column('transaction_id', sa.String(255), nullable=False),
        sa.Column('payment_method', sa.String(50)),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(3), default='USD'),
        sa.Column('status', sa.String(50)),
        sa.Column('stripe_payment_intent_id', sa.String(255)),
        sa.Column('metadata', sa.JSON()),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('transaction_id')
    )
    
    # Create indexes
    op.create_index('ix_transaction_user', 'transactions', ['user_id'])
    op.create_index('ix_transaction_status', 'transactions', ['status'])
    op.create_index('ix_transaction_created', 'transactions', ['created_at'])


def downgrade() -> None:
    """Drop all tables"""
    op.drop_table('transactions')
    op.drop_table('tasks')
    op.drop_table('media_items')
    op.drop_table('users')
    
    # Drop enum types
    op.execute('DROP TYPE IF EXISTS userrole')
    op.execute('DROP TYPE IF EXISTS mediatype')
    op.execute('DROP TYPE IF EXISTS taskstatus')
