#!/bin/bash
# ============================================================
# BRAHMASTRA - Deploy Self-Healing Engine as systemd service
# Run this in your EC2 terminal after setup_nginx_dashboard.sh
# ============================================================

echo "🤖 Setting up Self-Healing Engine..."

# Copy self_healing.py to EC2 path
# (If running from the repo, it should already be at the right path)
HEAL_PATH="/home/ubuntu/brahmastra/backend/self_healing.py"

if [ ! -f "$HEAL_PATH" ]; then
    echo "❌ self_healing.py not found at $HEAL_PATH"
    echo "   Please make sure you've cloned/copied the latest backend files."
    exit 1
fi

# Install requests if not present
echo "📦 Installing dependencies..."
cd /home/ubuntu/brahmastra/backend
source venv/bin/activate
pip install requests psutil --quiet
deactivate

# Create systemd service
echo "⚙️  Creating systemd service..."
sudo tee /etc/systemd/system/brahmastra-healer.service > /dev/null << 'SVCEOF'
[Unit]
Description=Brahmastra Self-Healing Engine
After=network.target brahmastra.service
Requires=brahmastra.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/brahmastra/backend
ExecStart=/home/ubuntu/brahmastra/backend/venv/bin/python3 self_healing.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable brahmastra-healer.service
sudo systemctl start brahmastra-healer.service

sleep 3
sudo systemctl status brahmastra-healer.service --no-pager

echo ""
echo "✅ Self-Healing Engine is now running!"
echo ""
echo "📋 Useful commands:"
echo "   View logs   : sudo journalctl -u brahmastra-healer -f"
echo "   Check status: sudo systemctl status brahmastra-healer"
echo "   Stop engine : sudo systemctl stop brahmastra-healer"
