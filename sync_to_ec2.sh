#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Brahmastra — Sync Local Code to EC2 & Restart
# Run from your LOCAL machine:  bash sync_to_ec2.sh
# ═══════════════════════════════════════════════════════════════

EC2_USER="ubuntu"
EC2_IP="3.6.36.97"   # ← UPDATE if IP changes
KEY_FILE="./brahmastra-key.pem"
REMOTE_DIR="/home/ubuntu/brahmastra"

echo "🚀 Syncing Brahmastra to EC2..."
echo "   Target: $EC2_USER@$EC2_IP"

# 1. Sync backend code
echo ""
echo "📁 Syncing backend..."
scp -i "$KEY_FILE" -o StrictHostKeyChecking=no \
    backend/main.py \
    backend/auth.py \
    backend/database.py \
    backend/models.py \
    backend/schemas.py \
    backend/threat_detection.py \
    backend/email_service.py \
    backend/self_healing.py \
    backend/logger.py \
    backend/requirements.txt \
    "$EC2_USER@$EC2_IP:$REMOTE_DIR/backend/"

# 2. Sync dashboard
echo "📁 Syncing dashboard..."
scp -i "$KEY_FILE" -o StrictHostKeyChecking=no \
    dashboard/index.html \
    dashboard/login.html \
    dashboard/forgot-password.html \
    dashboard/reset-password.html \
    dashboard/verify-email.html \
    "$EC2_USER@$EC2_IP:$REMOTE_DIR/dashboard/"

# 3. Sync setup script
echo "📁 Syncing setup script..."
scp -i "$KEY_FILE" -o StrictHostKeyChecking=no \
    setup_phase3_ec2.sh \
    "$EC2_USER@$EC2_IP:$REMOTE_DIR/"

# 4. Restart backend on EC2
echo ""
echo "🔄 Restarting backend on EC2..."
ssh -i "$KEY_FILE" -o StrictHostKeyChecking=no "$EC2_USER@$EC2_IP" << 'REMOTE'
    sudo systemctl restart brahmastra 2>/dev/null || echo "⚠️ brahmastra service not found"
    sudo systemctl restart brahmastra-healer 2>/dev/null || echo "⚠️ healer service not found"
    sudo systemctl reload nginx 2>/dev/null || echo "⚠️ nginx reload failed"
    sleep 3
    echo ""
    echo "🔍 Service status:"
    echo "  Backend: $(sudo systemctl is-active brahmastra 2>/dev/null || echo 'not configured')"
    echo "  Healer:  $(sudo systemctl is-active brahmastra-healer 2>/dev/null || echo 'not configured')"
    echo "  Nginx:   $(sudo systemctl is-active nginx 2>/dev/null || echo 'not configured')"
    echo ""
    curl -sf http://localhost:8000/health && echo "✅ API is healthy" || echo "❌ API not responding"
REMOTE

echo ""
echo "✅ Sync complete!"
echo "🌐 Dashboard: http://$EC2_IP:8080"
echo "🔌 API:       http://$EC2_IP:8000/docs"
