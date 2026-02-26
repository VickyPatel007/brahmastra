#!/bin/bash
# Brahmastra Backend Startup Script
# This script ensures DATABASE_URL is set before starting the backend

# Kill any existing backend processes
pkill -9 -f uvicorn

# Navigate to project directory
cd /home/ubuntu/brahmastra

# Activate virtual environment
source venv/bin/activate

# Set DATABASE_URL environment variable
export DATABASE_URL="postgresql://brahmastra_admin:BrahmastraDB2024!@brahmastra-db.ctuc8ygwmfbb.ap-south-1.rds.amazonaws.com:5432/brahmastra"

# Start backend with DATABASE_URL set
nohup python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload > /tmp/brahmastra.log 2>&1 &

# Wait for backend to start
sleep 3

# Test health endpoint
echo "Testing backend health..."
curl -s http://localhost:8000/health

echo ""
echo "✅ Backend started with DATABASE_URL set!"
echo "Backend is running on http://0.0.0.0:8000"
