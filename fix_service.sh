#!/bin/bash
# Quick fix for the crashed service

echo "🔧 Fixing the backend service..."

cd /home/ubuntu/brahmastra

# Check service status
echo "📊 Current service status:"
sudo systemctl status brahmastra --no-pager | tail -20

# Check logs for errors
echo ""
echo "📋 Recent logs:"
sudo journalctl -u brahmastra -n 30 --no-pager

# Restore backup if it exists
if [ -f "main.py.backup" ]; then
    echo ""
    echo "🔄 Restoring backup..."
    cp main.py.backup main.py
    sudo systemctl restart brahmastra
    sleep 3
    curl http://localhost:8000/health
else
    echo "❌ No backup found"
fi
