#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# BRAHMASTRA PHASE 3 — PASTE THIS ENTIRE SCRIPT INTO EC2
# ═══════════════════════════════════════════════════════════════
set -e
echo "🛡️  Brahmastra Phase 3 — Starting..."

BRAHMASTRA_DIR="/home/ubuntu/brahmastra"
cd "$BRAHMASTRA_DIR"

# ─────────────────────────────────────────────────────
# PART 1: Fix dashboard/index.html — remove hardcoded IP
# ─────────────────────────────────────────────────────
echo "📝 Patching dashboard/index.html..."

# Replace hardcoded API_URL with relative path
sed -i "s|const API_URL = 'http://[0-9.]*:8000';|// API via Nginx proxy (relative paths)\n        const API_URL = '';|g" dashboard/index.html

# Add WS_URL if not present
if ! grep -q "WS_URL" dashboard/index.html; then
    sed -i "/const API_URL = '';/a\\        const WS_URL = 'ws://' + window.location.hostname + ':8080/ws';" dashboard/index.html
fi

echo "   ✅ index.html patched"

# ─────────────────────────────────────────────────────
# PART 2: Fix dashboard/login.html — remove hardcoded IP
# ─────────────────────────────────────────────────────
echo "📝 Patching dashboard/login.html..."

sed -i "s|const API_URL = 'http://[0-9.]*:8000';|// API via Nginx proxy\n        const API_URL = '';|g" dashboard/login.html

echo "   ✅ login.html patched"

# ─────────────────────────────────────────────────────
# PART 3: Generate Strong JWT Secret + Create .env
# ─────────────────────────────────────────────────────
echo ""
echo "🔐 Generating JWT secret..."

JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "localhost")

echo "   IP: $PUBLIC_IP"
echo "   JWT: ${JWT_SECRET:0:12}..."

cat > "$BRAHMASTRA_DIR/.env" << EOF
# Brahmastra Production Config — Generated $(date)
SERVER_HOST=http://${PUBLIC_IP}
CORS_ORIGINS=http://${PUBLIC_IP},http://${PUBLIC_IP}:8080,http://${PUBLIC_IP}:8000,http://localhost:8080,http://localhost:8000
JWT_SECRET_KEY=${JWT_SECRET}
DATABASE_URL=postgresql://brahmastra_admin:BrahmastraDB2024!@localhost:5432/brahmastra_db
# SES_FROM_EMAIL=noreply@yourdomain.com
# AWS_REGION=ap-south-1
EOF

echo "   ✅ .env created"

# ─────────────────────────────────────────────────────
# PART 4: Update backend main.py — add security alert
# ─────────────────────────────────────────────────────
echo ""
echo "📝 Patching backend/main.py..."

# Fix the threat_detection import to include MAX_FAILED_LOGINS
sed -i 's/from backend.threat_detection import threat_engine$/from backend.threat_detection import threat_engine, MAX_FAILED_LOGINS/' backend/main.py

echo "   ✅ main.py patched"

# ─────────────────────────────────────────────────────
# PART 5: Update brahmastra.service to load .env
# ─────────────────────────────────────────────────────
echo ""
echo "⚙️  Updating brahmastra.service..."

sudo tee /etc/systemd/system/brahmastra.service > /dev/null << 'SVCEOF'
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
SVCEOF

echo "   ✅ brahmastra.service updated"

# ─────────────────────────────────────────────────────
# PART 6: Create Self-Healing systemd service
# ─────────────────────────────────────────────────────
echo ""
echo "🔄 Creating brahmastra-healer.service..."

sudo tee /etc/systemd/system/brahmastra-healer.service > /dev/null << 'HEALEOF'
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
HEALEOF

echo "   ✅ brahmastra-healer.service created"

# ─────────────────────────────────────────────────────
# PART 7: Update Nginx to proxy /api/* to backend
# ─────────────────────────────────────────────────────
echo ""
echo "🌐 Updating Nginx config..."

sudo tee /etc/nginx/sites-available/brahmastra > /dev/null << 'NGXEOF'
server {
    listen 8080;
    server_name _;

    root /home/ubuntu/brahmastra/dashboard;
    index index.html login.html;

    # Proxy API calls to FastAPI backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 30s;
    }

    # Proxy /health endpoint
    location /health {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
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
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
}
NGXEOF

sudo ln -sf /etc/nginx/sites-available/brahmastra /etc/nginx/sites-enabled/brahmastra 2>/dev/null || true
sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

if sudo nginx -t 2>/dev/null; then
    echo "   ✅ Nginx config valid"
else
    echo "   ⚠️  Nginx config error"
fi

# ─────────────────────────────────────────────────────
# PART 8: Install missing packages
# ─────────────────────────────────────────────────────
echo ""
echo "📦 Installing packages..."
source venv/bin/activate
pip install -q requests python-dotenv 2>/dev/null
deactivate
echo "   ✅ Done"

# ─────────────────────────────────────────────────────
# PART 9: Restart everything
# ─────────────────────────────────────────────────────
echo ""
echo "🚀 Restarting all services..."

sudo systemctl daemon-reload
sudo systemctl enable brahmastra.service
sudo systemctl restart brahmastra.service
echo "   ✅ Backend restarted"

sudo systemctl enable brahmastra-healer.service
sudo systemctl start brahmastra-healer.service
echo "   ✅ Self-healer started"

sudo systemctl reload nginx || sudo systemctl restart nginx
echo "   ✅ Nginx reloaded"

# ─────────────────────────────────────────────────────
# PART 10: Verify
# ─────────────────────────────────────────────────────
echo ""
echo "⏳ Waiting 5s for startup..."
sleep 5

echo ""
echo "════════════════════════════════════════"
echo "   Backend:  $(sudo systemctl is-active brahmastra 2>/dev/null)"
echo "   Healer:   $(sudo systemctl is-active brahmastra-healer 2>/dev/null)"
echo "   Nginx:    $(sudo systemctl is-active nginx 2>/dev/null)"
echo "════════════════════════════════════════"

if curl -sf http://localhost:8000/health > /dev/null; then
    echo "✅ API is healthy!"
else
    echo "❌ API not responding. Check: sudo journalctl -u brahmastra -n 30"
fi

echo ""
echo "════════════════════════════════════════"
echo "✅ PHASE 3 SETUP COMPLETE!"
echo "════════════════════════════════════════"
echo ""
echo "🌐 Dashboard: http://${PUBLIC_IP}:8080"
echo "🔌 API Docs:  http://${PUBLIC_IP}:8000/docs"
echo ""
