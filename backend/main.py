"""
Project Brahmastra - Backend API
FastAPI application for self-healing infrastructure monitoring
"""

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psutil
import time
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
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage (will move to PostgreSQL later)
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
    """Root endpoint"""
    return {
        "app": "Brahmastra",
        "version": "0.1.0",
        "status": "running",
        "message": "Self-Healing Infrastructure Monitoring System"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/api/metrics/current", response_model=HealthStatus)
async def get_current_metrics():
    """Get current system metrics"""
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
    
    # Store in history
    metrics_history.append(metrics)
    if len(metrics_history) > 1000:  # Keep last 1000 entries
        metrics_history.pop(0)
    
    return metrics


@app.get("/api/metrics/history")
async def get_metrics_history(limit: int = 100):
    """Get historical metrics"""
    return metrics_history[-limit:]


@app.get("/api/threat/score")
async def get_threat_score():
    """Calculate current threat score (0-100)"""
    # Simple calculation based on system metrics
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory().percent
    
    # Basic threat score calculation
    threat_score = int((cpu + memory) / 2)
    
    return {
        "threat_score": min(threat_score, 100),
        "level": "low" if threat_score < 50 else "medium" if threat_score < 80 else "high",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/incidents", response_model=List[Incident])
async def get_incidents(limit: int = 50):
    """Get recent security incidents"""
    return incidents[-limit:]


@app.post("/api/incidents")
async def create_incident(incident: Incident):
    """Log a new security incident"""
    incidents.append(incident.dict())
    return {"status": "created", "incident": incident}


@app.post("/api/kill-switch")
async def trigger_kill_switch():
    """Trigger emergency kill-switch (manual)"""
    # TODO: Implement actual kill-switch logic
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
    """WebSocket for real-time updates to dashboard"""
    await websocket.accept()
    try:
        while True:
            # Send current metrics every 5 seconds
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
