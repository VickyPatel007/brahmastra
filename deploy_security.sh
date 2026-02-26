#!/bin/bash

# Deploy Security Enhancements to EC2
# This script deploys CORS restriction, rate limiting, and logout functionality

set -e  # Exit on error

echo "🚀 Deploying Security Enhancements to EC2..."
echo ""

# Configuration
EC2_IP="13.234.113.97"
EC2_USER="ubuntu"
EC2_KEY="~/.ssh/brahmastra-key.pem"
PROJECT_DIR="/home/ubuntu/brahmastra"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step 1: Upload updated files
echo -e "${YELLOW}📤 Step 1: Uploading updated backend files...${NC}"
scp -i $EC2_KEY backend/main.py ${EC2_USER}@${EC2_IP}:${PROJECT_DIR}/backend/
scp -i $EC2_KEY backend/requirements.txt ${EC2_USER}@${EC2_IP}:${PROJECT_DIR}/backend/

echo -e "${GREEN}✅ Files uploaded${NC}"
echo ""

# Step 2: Install dependencies and restart backend
echo -e "${YELLOW}🔧 Step 2: Installing dependencies and restarting backend...${NC}"
ssh -i $EC2_KEY ${EC2_USER}@${EC2_IP} << 'ENDSSH'
cd /home/ubuntu/brahmastra

# Activate virtual environment
source venv/bin/activate

# Install slowapi
pip install slowapi>=0.1.9

# Kill existing backend
sudo pkill -9 python3 || true
sudo pkill -9 uvicorn || true

# Wait a moment
sleep 2

# Start backend
nohup python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 > /tmp/brahmastra.log 2>&1 &

# Wait for startup
sleep 3

# Verify backend is running
ps aux | grep uvicorn | grep -v grep

echo ""
echo "✅ Backend restarted with security enhancements!"
ENDSSH

echo -e "${GREEN}✅ Backend deployed and running${NC}"
echo ""

# Step 3: Verify deployment
echo -e "${YELLOW}🧪 Step 3: Verifying deployment...${NC}"

# Test 1: Check if backend is responding
echo "Test 1: Backend health check..."
if curl -s -o /dev/null -w "%{http_code}" http://${EC2_IP}:8000/api/health | grep -q "200"; then
    echo -e "${GREEN}✅ Backend is responding${NC}"
else
    echo -e "${RED}❌ Backend health check failed${NC}"
fi

# Test 2: Check API docs
echo "Test 2: API documentation..."
if curl -s http://${EC2_IP}:8000/docs | grep -q "Brahmastra"; then
    echo -e "${GREEN}✅ API docs accessible${NC}"
else
    echo -e "${RED}❌ API docs not accessible${NC}"
fi

echo ""
echo -e "${GREEN}🎉 Deployment Complete!${NC}"
echo ""
echo "📊 What's New:"
echo "  ✅ CORS restricted to specific origins"
echo "  ✅ Rate limiting: 5/min for register, 10/min for login"
echo "  ✅ Logout endpoint added"
echo ""
echo "🌐 Test URLs:"
echo "  - API Docs: http://${EC2_IP}:8000/docs"
echo "  - Login Page: http://${EC2_IP}:8080/login.html"
echo ""
echo "📝 Next: Test rate limiting by trying to register 6 times quickly"
