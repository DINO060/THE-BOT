# ==================== deploy.sh ====================
#!/bin/bash
# Production deployment script

set -e

echo "🚀 Starting production deployment..."

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check required variables
required_vars="BOT_TOKEN DB_PASSWORD REDIS_PASSWORD MINIO_ACCESS_KEY MINIO_SECRET_KEY"
for var in $required_vars; do
    if [ -z "${!var}" ]; then
        echo "❌ Error: $var is not set"
        exit 1
    fi
done

# Pull latest code
echo "📦 Pulling latest code..."
git pull origin main

# Build Docker images
echo "🔨 Building Docker images..."
docker-compose -f docker/docker-compose.yml build

# Run database migrations
echo "🗄️ Running database migrations..."
docker-compose -f docker/docker-compose.yml run --rm bot-api alembic upgrade head

# Start services
echo "🎯 Starting services..."
docker-compose -f docker/docker-compose.yml up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check service health
services="postgres redis rabbitmq minio bot-api worker"
for service in $services; do
    if docker-compose -f docker/docker-compose.yml ps | grep -q "$service.*Up"; then
        echo "✅ $service is running"
    else
        echo "❌ $service failed to start"
        docker-compose -f docker/docker-compose.yml logs $service
        exit 1
    fi
done

# Run tests
echo "🧪 Running tests..."
docker-compose -f docker/docker-compose.yml run --rm bot-api pytest tests/ -v

# Setup monitoring
echo "📊 Setting up monitoring..."
curl -X POST http://localhost:3000/api/dashboards/db \
    -H "Content-Type: application/json" \
    -H "Authorization: Basic $(echo -n admin:$GRAFANA_PASSWORD | base64)" \
    -d @monitoring/grafana/dashboard.json

echo "✅ Deployment complete!"
echo "📊 Grafana: http://localhost:3000"
echo "🌻 Flower: http://localhost:5555"
echo "📈 Prometheus: http://localhost:9090"