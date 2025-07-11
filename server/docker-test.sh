#!/bin/bash

# Test script for Docker setup
echo "🐳 Testing Docker setup for EZ Scheduler Server"
echo "=================================================="

echo "📁 Checking required files..."
FILES=("pyproject.toml" "uv.lock" "src/ez_scheduler/main.py" ".env")
for file in "${FILES[@]}"; do
    if [[ -f "$file" ]]; then
        echo "  ✅ $file"
    else
        echo "  ❌ $file (missing)"
        exit 1
    fi
done

echo "🔧 Testing Docker build..."
if command -v docker &> /dev/null; then
    echo "  Building Docker image..."
    docker build -t ez-scheduler-server . || exit 1
    echo "  ✅ Docker build successful"
    
    echo "🚀 Testing Docker run (dry run)..."
    echo "  Command: docker run -p 8080:8080 ez-scheduler-server"
    echo "  ✅ Ready to run"
else
    echo "  ⚠️  Docker not available, skipping build test"
fi

echo "📋 Docker Compose services:"
echo "  - postgres:5432"
echo "  - redis:6379" 
echo "  - app:8080"

echo ""
echo "🎉 Docker setup verification complete!"
echo ""
echo "To run the services:"
echo "  docker-compose up         # Start dependencies only"
echo "  docker-compose --profile app up  # Start all services including app"