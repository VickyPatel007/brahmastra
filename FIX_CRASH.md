# Fix Backend Crash - Final Solution

## 🔧 **Problem Identified**

The service is running but the app crashes with `exit-code=2` (INVALIDARGUMENT).

This means `main.py` wasn't created correctly.

---

## ✅ **Solution: Recreate main.py**

Run these commands in your EC2 terminal:

```bash
# Stop the crashing service first
sudo systemctl stop brahmastra

# Go to the brahmastra directory
cd /home/ubuntu/brahmastra

# Delete the broken main.py
rm -f main.py

# Create main.py correctly (copy this ENTIRE block)
cat > main.py << 'ENDOFFILE'
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
ENDOFFILE

# Verify the file was created
cat main.py

# Restart the service
sudo systemctl start brahmastra

# Wait 2 seconds
sleep 2

# Check status
sudo systemctl status brahmastra

# Test it
curl http://localhost:8000/health
```

---

## ✅ **Expected Output**

After running these commands, you should see:

1. ✅ Service status: **active (running)** (no more crashes!)
2. ✅ Health check: `{"status":"healthy","timestamp":"..."}`

---

**Copy the entire block above and paste it into your EC2 terminal!** 🚀
