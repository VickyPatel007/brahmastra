#!/bin/bash
# Brahmastra Backend Deployment Script

set -e

echo "🚀 Deploying Brahmastra Backend..."

# Update system
echo "📦 Updating system packages..."
sudo apt-get update -y
sudo apt-get upgrade -y

# Install Python and dependencies
echo "🐍 Installing Python and pip..."
sudo apt-get install -y python3-pip python3-venv git

# Create app directory
echo "📁 Creating application directory..."
mkdir -p ~/brahmastra
cd ~/brahmastra

# Create virtual environment
echo "🔧 Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Create requirements.txt
cat > requirements.txt << 'EOF'
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
pydantic>=2.10.0
psutil>=6.1.0
python-multipart>=0.0.20
websockets>=14.0
EOF

# Install Python packages
echo "📚 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create main.py
cat > main.py << 'EOFPY'
"""
Project Brahmastra - Backend API
FastAPI application for self-healing infrastructure monitoring
"""

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psutil
import time
import asyncio
from datetime import datetime
from typing import List, Dict

app = FastAPI(
    title="Brahmastra API",
    description="Self-Healing Infrastructure Monitoring System",
    version="0.1.0"
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage
incidents: List[Dict] = []
metrics_history: List[Dict] = []


class HealthStatus(BaseModel):
    status: str
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    timestamp: str


class Incident(BaseModel):
    id: int
    type: str
    severity: int
    description: str
    timestamp: str
    resolved: bool


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


@app.get("/api/metrics/current", response_model=HealthStatus)
async def get_current_metrics():
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    
    metrics = {
        "status": "healthy" if cpu < 80 and memory < 80 else "warning",
        "cpu_percent": cpu,
        "memory_percent": memory,
        "disk_percent": disk,
        "timestamp": datetime.now().isoformat()
    }
    
    metrics_history.append(metrics)
    if len(metrics_history) > 1000:
        metrics_history.pop(0)
    
    return metrics


@app.get("/api/metrics/history")
async def get_metrics_history(limit: int = 100):
    return metrics_history[-limit:]


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


@app.get("/api/incidents", response_model=List[Incident])
async def get_incidents(limit: int = 50):
    return incidents[-limit:]


@app.post("/api/incidents")
async def create_incident(incident: Incident):
    incidents.append(incident.dict())
    return {"status": "created", "incident": incident}


@app.post("/api/kill-switch")
async def trigger_kill_switch():
    incident = {
        "id": len(incidents) + 1,
        "type": "manual_kill_switch",
        "severity": 10,
        "description": "Manual kill-switch triggered by admin",
        "timestamp": datetime.now().isoformat(),
        "resolved": False
    }
    incidents.append(incident)
    
    return {
        "status": "triggered",
        "message": "Kill-switch activated. Auto-healing in progress...",
        "incident_id": incident["id"]
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            cpu = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory().percent
            
            data = {
                "type": "metrics_update",
                "cpu": cpu,
                "memory": memory,
                "timestamp": datetime.now().isoformat()
            }
            
            await websocket.send_json(data)
            await asyncio.sleep(5)
    except Exception as e:
        print(f"WebSocket error: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
EOFPY

echo "✅ Backend code deployed!"
echo "🚀 Starting Brahmastra API..."

# Run the app in background
nohup python3 main.py > app.log 2>&1 &

echo "✅ Brahmastra is now running!"
echo "📊 Check logs: tail -f ~/brahmastra/app.log"
echo "🌐 API URL: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8000"
