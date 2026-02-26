#!/bin/bash
# ============================================================
# deploy_backend.sh — Deploy updated Brahmastra backend to EC2
# Usage: ./deploy_backend.sh
# ============================================================

set -e

EC2_IP="15.206.82.159"
EC2_USER="ubuntu"
PEM_KEY="./brahmastra-key.pem"
REMOTE_DIR="/home/ubuntu/brahmastra"

echo "🚀 Deploying Brahmastra backend to $EC2_IP..."

# ── Step 1: Copy backend files ────────────────────────────────────────────────
echo "📦 Uploading backend files..."
rsync -avz --progress \
    -e "ssh -i $PEM_KEY -o StrictHostKeyChecking=no" \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.env' \
    backend/ \
    $EC2_USER@$EC2_IP:$REMOTE_DIR/backend/

# ── Step 2: Copy dashboard files ──────────────────────────────────────────────
echo "🎨 Uploading dashboard files..."
rsync -avz --progress \
    -e "ssh -i $PEM_KEY -o StrictHostKeyChecking=no" \
    dashboard/ \
    $EC2_USER@$EC2_IP:/var/www/brahmastra/

# ── Step 3: Install dependencies & restart service ───────────────────────────
echo "📡 Installing dependencies and restarting service..."
ssh -i $PEM_KEY -o StrictHostKeyChecking=no $EC2_USER@$EC2_IP << 'REMOTE'
    set -e
    cd /home/ubuntu/brahmastra

    # Activate venv and install deps
    source venv/bin/activate
    pip install -r backend/requirements.txt --quiet

    # Reload and restart backend
    sudo systemctl daemon-reload
    sudo systemctl restart brahmastra.service

    echo "⏳ Waiting for service to start..."
    sleep 5

    # Check status
    if sudo systemctl is-active --quiet brahmastra.service; then
        echo "✅ brahmastra.service is RUNNING"
        curl -s http://localhost:8000/health | python3 -m json.tool
    else
        echo "❌ Service failed to start. Logs:"
        sudo journalctl -u brahmastra.service --no-pager -n 30
        exit 1
    fi
REMOTE

echo ""
echo "✅ Deploy complete!"
echo "   Dashboard : http://$EC2_IP"
echo "   API Health: http://$EC2_IP:8000/health"
echo "   API Docs  : http://$EC2_IP:8000/docs"
