#!/bin/bash
# Auto-Start Setup Script for Brahmastra Backend

set -e

echo "🚀 Setting up Brahmastra auto-start service..."

# Create systemd service file
sudo tee /etc/systemd/system/brahmastra.service > /dev/null <<'EOF'
[Unit]
Description=Brahmastra Self-Healing Infrastructure API
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/brahmastra
Environment="PATH=/home/ubuntu/brahmastra/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/ubuntu/brahmastra/venv/bin/python3 /home/ubuntu/brahmastra/main.py
Restart=always
RestartSec=10
StandardOutput=append:/home/ubuntu/brahmastra/app.log
StandardError=append:/home/ubuntu/brahmastra/app.log

[Install]
WantedBy=multi-user.target
EOF

echo "✅ Service file created"

# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable brahmastra.service

# Start the service now
sudo systemctl start brahmastra.service

# Check status
sudo systemctl status brahmastra.service --no-pager

echo ""
echo "✅ Brahmastra is now set up to auto-start!"
echo ""
echo "📋 Useful commands:"
echo "  - Check status:  sudo systemctl status brahmastra"
echo "  - View logs:     sudo journalctl -u brahmastra -f"
echo "  - Restart:       sudo systemctl restart brahmastra"
echo "  - Stop:          sudo systemctl stop brahmastra"
echo ""
echo "🌐 Test your API:"
echo "  curl http://localhost:8000/health"
