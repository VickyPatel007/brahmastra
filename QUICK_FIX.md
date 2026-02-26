# Quick Fix - Manual Backend Setup

## 🔧 **Issue Found**

The user_data script failed because `python3-venv` package doesn't exist on Ubuntu 22.04.

**Error**: `ensurepip is not available`

---

## ✅ **Quick Fix (Copy-Paste in EC2 Terminal)**

Run these commands in your EC2 Instance Connect terminal:

```bash
# Install correct Python venv package
sudo apt-get install -y python3.10-venv

# Go to home directory
cd /home/ubuntu
mkdir -p brahmastra
cd brahmastra

# Create virtual environment (with correct package)
python3 -m venv venv
source venv/bin/activate

# Install Python packages
pip install --upgrade pip
pip install fastapi uvicorn psutil websockets pydantic

# Create main.py
cat > main.py << 'EOF'
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import psutil
from datetime import datetime

app = FastAPI(
    title="Brahmastra API",
    description="Self-Healing Infrastructure Monitoring System",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "app": "Brahmastra",
        "version": "0.1.0",
        "status": "running",
        "message": "Self-Healing Infrastructure Monitoring System",
        "location": "AWS Mumbai (ap-south-1)"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/metrics/current")
async def get_current_metrics():
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    
    return {
        "status": "healthy" if cpu < 80 and memory < 80 else "warning",
        "cpu_percent": cpu,
        "memory_percent": memory,
        "disk_percent": disk,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/threat/score")
async def get_threat_score():
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory().percent
    threat_score = int((cpu + memory) / 2)
    
    return {
        "threat_score": min(threat_score, 100),
        "level": "low" if threat_score < 50 else "medium" if threat_score < 80 else "high",
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
EOF

# Create systemd service
sudo tee /etc/systemd/system/brahmastra.service > /dev/null <<'EOFSVC'
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
EOFSVC

# Fix ownership
sudo chown -R ubuntu:ubuntu /home/ubuntu/brahmastra

# Start the service
sudo systemctl daemon-reload
sudo systemctl enable brahmastra.service
sudo systemctl start brahmastra.service

# Check status
sudo systemctl status brahmastra

# Test it
curl http://localhost:8000/health
```

---

## ✅ **Expected Output**

After running all commands, you should see:

1. **Service status**: `active (running)` ✅
2. **Health check**: `{"status":"healthy","timestamp":"..."}`

---

## 🧪 **Test from Your Mac**

```bash
curl http://15.206.82.159:8000/health
```

---

**This will take 2-3 minutes to complete. Just copy-paste the entire block!** 🚀
