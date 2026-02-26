# Backend Not Starting - Troubleshooting Guide

## ⚠️ **Issue: Backend API Not Responding**

After 5 minutes, the backend isn't responding at `http://15.206.82.159:8000`

This means the user_data script might have encountered an issue.

---

## 🔍 **Let's Check What's Happening**

### **Step 1: Connect to EC2 Instance**

1. Go to: https://ap-south-1.console.aws.amazon.com/ec2/home?region=ap-south-1#ConnectToInstance:instanceId=i-0a3af150703469ec1
2. Click **"Connect"**
3. You'll get a browser terminal

---

### **Step 2: Check Installation Logs**

Run these commands in the EC2 terminal:

```bash
# Check if user_data script finished
sudo tail -100 /var/log/cloud-init-output.log
```

Look for:
- ✅ "Cloud-init v. X.X.X finished" = Script completed
- ❌ Error messages = Something failed

---

### **Step 3: Check if Backend Service Exists**

```bash
# Check if systemd service was created
sudo systemctl status brahmastra
```

**If it says "could not be found":**
- The user_data script didn't finish
- We need to run setup manually

**If it says "active (running)":**
- Service is running but not accessible
- Might be a firewall issue

**If it says "failed":**
- Service tried to start but crashed
- Check logs: `sudo journalctl -u brahmastra -n 50`

---

### **Step 4: Manual Setup (If Needed)**

If the service doesn't exist, run this:

```bash
cd /home/ubuntu
mkdir -p brahmastra
cd brahmastra

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
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

# Start the service
sudo systemctl daemon-reload
sudo systemctl enable brahmastra.service
sudo systemctl start brahmastra.service

# Check status
sudo systemctl status brahmastra
```

---

### **Step 5: Test from EC2**

```bash
curl http://localhost:8000/health
```

Should return:
```json
{"status":"healthy","timestamp":"..."}
```

---

### **Step 6: Test from Your Computer**

```bash
curl http://15.206.82.159:8000/health
```

---

## 🎯 **What to Report Back**

After running the checks, tell me:

1. **What does the cloud-init log show?** (finished or error?)
2. **Does the systemd service exist?** (yes/no)
3. **Is it running?** (active/failed/not found)
4. **Can you curl localhost:8000?** (yes/no)

Then I can help you fix it! 🚀

---

## 💡 **Most Likely Issues**

1. **User_data still running** → Wait 2 more minutes
2. **Python installation failed** → Run manual setup
3. **Service crashed** → Check logs
4. **Port blocked** → Check security group (should be open on port 8000)
