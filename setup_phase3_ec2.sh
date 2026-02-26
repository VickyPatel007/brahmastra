#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Brahmastra Phase 3 — EC2 Setup Script
# Run this ONCE on your EC2 instance to set up:
#   1. Proper .env file with strong JWT secret
#   2. Self-Healing Engine as a systemd service
#   3. Nginx proxy so dashboard talks to backend via same port
# ═══════════════════════════════════════════════════════════════

set -e  # Exit on error
echo "================================================"
echo "🛡️  Brahmastra Phase 3 EC2 Setup"
echo "================================================"

BRAHMASTRA_DIR="/home/ubuntu/brahmastra"
cd "$BRAHMASTRA_DIR"

# ─── STEP 1: Generate Strong JWT Secret ──────────────────────
echo ""
echo "🔐 Step 1: Generating strong JWT secret..."

JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
echo "   Generated: ${JWT_SECRET:0:16}... (hidden for security)"

# ─── STEP 2: Create Production .env File ──────────────────────
echo ""
echo "📄 Step 2: Creating .env file..."

# Get the public IP of this instance
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "localhost")
echo "   Server IP: $PUBLIC_IP"

cat > "$BRAHMASTRA_DIR/.env" << EOF
# ════════════════════════════════════════════════
# Brahmastra Production Environment Variables
# Generated: $(date)
# ════════════════════════════════════════════════

# Server
SERVER_HOST=http://${PUBLIC_IP}
CORS_ORIGINS=http://${PUBLIC_IP},http://${PUBLIC_IP}:8080,http://${PUBLIC_IP}:8000,http://localhost:8080

# JWT Auth — STRONG generated secret, never share this!
JWT_SECRET_KEY=${JWT_SECRET}

# Database — local PostgreSQL
DATABASE_URL=postgresql://brahmastra_admin:BrahmastraDB2024!@localhost:5432/brahmastra_db

# AWS SES Email (fill in once you verify your email in SES)
# SES_FROM_EMAIL=noreply@yourdomain.com
# AWS_REGION=ap-south-1
# AWS_ACCESS_KEY_ID=
# AWS_SECRET_ACCESS_KEY=
EOF

echo "   ✅ .env file created at $BRAHMASTRA_DIR/.env"

# ─── STEP 3: Update Systemd Service to Load .env ─────────────
echo ""
echo "⚙️  Step 3: Updating brahmastra.service to load .env..."

sudo tee /etc/systemd/system/brahmastra.service > /dev/null << 'EOF'
[Unit]
Description=Brahmastra API Backend
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/brahmastra
EnvironmentFile=/home/ubuntu/brahmastra/.env
ExecStart=/home/ubuntu/brahmastra/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=append:/home/ubuntu/brahmastra/app.log
StandardError=append:/home/ubuntu/brahmastra/app.log

[Install]
WantedBy=multi-user.target
EOF

echo "   ✅ brahmastra.service updated"

# ─── STEP 4: Create Self-Healing Engine Systemd Service ───────
echo ""
echo "🔄 Step 4: Setting up Self-Healing Engine as systemd service..."

sudo tee /etc/systemd/system/brahmastra-healer.service > /dev/null << 'EOF'
[Unit]
Description=Brahmastra Self-Healing Engine
After=network.target brahmastra.service
Wants=brahmastra.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/brahmastra
ExecStart=/home/ubuntu/brahmastra/venv/bin/python3 backend/self_healing.py
Restart=always
RestartSec=10
StandardOutput=append:/home/ubuntu/brahmastra/self_healing.log
StandardError=append:/home/ubuntu/brahmastra/self_healing.log

[Install]
WantedBy=multi-user.target
EOF

echo "   ✅ brahmastra-healer.service created"

# ─── STEP 5: Update Nginx to Proxy API Calls ─────────────────
echo ""
echo "🌐 Step 5: Updating Nginx config to proxy API calls..."

sudo tee /etc/nginx/sites-available/brahmastra > /dev/null << 'EOF'
server {
    listen 8080;
    server_name _;

    # Serve static dashboard files
    root /home/ubuntu/brahmastra/dashboard;
    index index.html login.html;

    # Proxy /api/* and /ws to FastAPI backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 30s;
    }

    # WebSocket proxy
    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Static files
    location / {
        try_files $uri $uri/ /index.html;
        expires 1h;
        add_header Cache-Control "public, no-transform";
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
}
EOF

# Symlink if not already done
sudo ln -sf /etc/nginx/sites-available/brahmastra /etc/nginx/sites-enabled/brahmastra 2>/dev/null || true
sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

# Test nginx config
if sudo nginx -t 2>/dev/null; then
    echo "   ✅ Nginx config is valid"
else
    echo "   ⚠️  Nginx config has errors, check manually"
fi

# ─── STEP 6: Install missing Python packages ──────────────────
echo ""
echo "📦 Step 6: Installing missing Python packages..."
source venv/bin/activate
pip install -q requests  # needed by self_healing.py
pip install -q python-dotenv
deactivate
echo "   ✅ Packages installed"

# ─── STEP 7: Reload and Restart All Services ─────────────────
echo ""
echo "🚀 Step 7: Reloading and restarting all services..."

sudo systemctl daemon-reload

sudo systemctl enable brahmastra.service
sudo systemctl restart brahmastra.service
echo "   ✅ brahmastra backend restarted"

sudo systemctl enable brahmastra-healer.service
sudo systemctl start brahmastra-healer.service
echo "   ✅ self-healer started"

sudo systemctl reload nginx || sudo systemctl restart nginx
echo "   ✅ nginx reloaded"

# ─── STEP 8: Wait and verify ─────────────────────────────────
echo ""
echo "⏳ Waiting 5 seconds for services to start..."
sleep 5

echo ""
echo "🔍 Checking service status..."
echo ""

echo "--- brahmastra backend ---"
sudo systemctl is-active brahmastra.service && echo "✅ RUNNING" || echo "❌ NOT RUNNING"

echo ""
echo "--- self-healer ---"
sudo systemctl is-active brahmastra-healer.service && echo "✅ RUNNING" || echo "❌ NOT RUNNING"

echo ""
echo "--- nginx ---"
sudo systemctl is-active nginx && echo "✅ RUNNING" || echo "❌ NOT RUNNING"

echo ""
echo "🧪 Testing API health..."
if curl -sf http://localhost:8000/health > /dev/null; then
    echo "✅ API responding at http://localhost:8000/health"
else
    echo "❌ API not responding yet. Check: sudo journalctl -u brahmastra -n 50"
fi

echo ""
echo "================================================"
echo "✅ Phase 3 Setup Complete!"
echo "================================================"
echo ""
echo "📊 Dashboard:    http://${PUBLIC_IP}:8080"
echo "🔌 API:          http://${PUBLIC_IP}:8000"
echo "📚 API Docs:     http://${PUBLIC_IP}:8000/docs"
echo ""
echo "📋 Useful commands:"
echo "   sudo systemctl status brahmastra         # Backend status"
echo "   sudo systemctl status brahmastra-healer  # Self-healer status"
echo "   tail -f /home/ubuntu/brahmastra/app.log           # Backend logs"
echo "   tail -f /home/ubuntu/brahmastra/self_healing.log  # Healer logs"
echo ""
echo "⚡ NEXT: To enable real emails, edit .env and set SES_FROM_EMAIL"
echo "   Then: sudo systemctl restart brahmastra"
