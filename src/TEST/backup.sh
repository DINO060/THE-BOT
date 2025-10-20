# ==================== backup.sh ====================
#!/bin/bash
# Backup script for database and media files

set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/$TIMESTAMP"

echo "🔐 Starting backup at $TIMESTAMP"

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup PostgreSQL
echo "🗄️ Backing up database..."
docker-compose exec postgres pg_dump -U bot_user bot_db | gzip > "$BACKUP_DIR/database.sql.gz"

# Backup Redis
echo "💾 Backing up Redis..."
docker-compose exec redis redis-cli --rdb "$BACKUP_DIR/redis.rdb"

# Backup MinIO data
echo "📦 Backing up media files..."
docker-compose exec minio mc mirror minio/media-files "$BACKUP_DIR/media"

# Compress backup
echo "🗜️ Compressing backup..."
tar -czf "/backups/backup_$TIMESTAMP.tar.gz" -C /backups $TIMESTAMP

# Upload to remote storage (optional)
if [ ! -z "$BACKUP_S3_BUCKET" ]; then
    echo "☁️ Uploading to S3..."
    aws s3 cp "/backups/backup_$TIMESTAMP.tar.gz" "s3://$BACKUP_S3_BUCKET/backups/"
fi

# Clean old local backups (keep last 7 days)
echo "🧹 Cleaning old backups..."
find /backups -name "backup_*.tar.gz" -mtime +7 -delete

echo "✅ Backup completed successfully!"