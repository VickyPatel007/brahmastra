#!/bin/bash
# Deploy updated backend to EC2

set -e

echo "🚀 Deploying updated backend to EC2..."

# Create the updated main.py content
cat > /tmp/main.py << 'EOFMAIN'
"""
Project Brahmastra - Backend API
FastAPI application for self-healing infrastructure monitoring
"""

from fastapi import FastAPI, WebSocket, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
import psutil
import asyncio
from datetime import datetime
from typing import List, Dict, Optional
import os

# Import database components
try:
    from backend.database import get_db, engine, Base
    from backend.models import Metric, ThreatScore, SystemEvent
    from backend.schemas import MetricResponse, ThreatScoreResponse
    DB_ENABLED = True
except ImportError:
    DB_ENABLED = False
    print("⚠️  Database not configured, using in-memory storage")

app = FastAPI(
    title="Brahmastra API",
    description="Self-Healing Infrastructure Monitoring System",
    version="0.2.0"
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory fallback storage
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


@app.on_event("startup")
async def startup_event():
    if DB_ENABLED:
        print("✅ Database enabled")
    else:
        print("⚠️  Running without database")


@app.get("/")
async def root():
    return {
        "app": "Brahmastra",
        "version": "0.2.0",
        "status": "running",
        "message": "Self-Healing Infrastructure Monitoring System",
        "database": "enabled" if DB_ENABLED else "disabled"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/api/metrics/current", response_model=HealthStatus)
async def get_current_metrics(db: Session = Depends(get_db) if DB_ENABLED else None):
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    
    status = "healthy" if cpu < 80 and memory < 80 else "warning"
    
    metrics = {
        "status": status,
        "cpu_percent": cpu,
        "memory_percent": memory,
        "disk_percent": disk,
        "timestamp": datetime.now().isoformat()
    }
    
    if DB_ENABLED and db:
        try:
            db_metric = Metric(
                cpu_percent=cpu,
                memory_percent=memory,
                disk_percent=disk,
                status=status
            )
            db.add(db_metric)
            db.commit()
        except Exception as e:
            print(f"❌ Failed to save metric: {e}")
            db.rollback()
    else:
        metrics_history.append(metrics)
        if len(metrics_history) > 1000:
            metrics_history.pop(0)
    
    return metrics


@app.get("/api/metrics/history")
async def get_metrics_history(limit: int = 100, db: Session = Depends(get_db) if DB_ENABLED else None):
    if DB_ENABLED and db:
        try:
            metrics = db.query(Metric).order_by(Metric.timestamp.desc()).limit(limit).all()
            return [{
                "id": m.id,
                "cpu_percent": m.cpu_percent,
                "memory_percent": m.memory_percent,
                "disk_percent": m.disk_percent,
                "status": m.status,
                "timestamp": m.timestamp.isoformat()
            } for m in reversed(metrics)]
        except Exception as e:
            return []
    else:
        return metrics_history[-limit:]


@app.get("/api/threat/score")
async def get_threat_score(db: Session = Depends(get_db) if DB_ENABLED else None):
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory().percent
    
    threat_score = int((cpu + memory) / 2)
    threat_level = "low" if threat_score < 50 else "medium" if threat_score < 80 else "high"
    
    if DB_ENABLED and db:
        try:
            db_threat = ThreatScore(
                threat_score=threat_score,
                threat_level=threat_level
            )
            db.add(db_threat)
            db.commit()
        except Exception as e:
            db.rollback()
    
    return {
        "threat_score": min(threat_score, 100),
        "level": threat_level,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/threat/history")
async def get_threat_history(limit: int = 100, db: Session = Depends(get_db) if DB_ENABLED else None):
    if DB_ENABLED and db:
        try:
            scores = db.query(ThreatScore).order_by(ThreatScore.timestamp.desc()).limit(limit).all()
            return [{
                "id": s.id,
                "threat_score": s.threat_score,
                "threat_level": s.threat_level,
                "timestamp": s.timestamp.isoformat()
            } for s in reversed(scores)]
        except:
            return []
    return []


@app.get("/api/events")
async def get_events(limit: int = 50, event_type: Optional[str] = None, db: Session = Depends(get_db) if DB_ENABLED else None):
    if DB_ENABLED and db:
        try:
            query = db.query(SystemEvent)
            if event_type:
                query = query.filter(SystemEvent.event_type == event_type)
            events = query.order_by(SystemEvent.timestamp.desc()).limit(limit).all()
            return [{
                "id": e.id,
                "event_type": e.event_type,
                "description": e.description,
                "severity": e.severity,
                "timestamp": e.timestamp.isoformat()
            } for e in reversed(events)]
        except:
            return []
    return []


@app.post("/api/events")
async def create_event(event_type: str, description: str, severity: str = "info", db: Session = Depends(get_db) if DB_ENABLED else None):
    if DB_ENABLED and db:
        try:
            db_event = SystemEvent(
                event_type=event_type,
                description=description,
                severity=severity
            )
            db.add(db_event)
            db.commit()
            db.refresh(db_event)
            return {"status": "created", "event": {"id": db_event.id}}
        except Exception as e:
            db.rollback()
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "Database not enabled"}


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
EOFMAIN

echo "📋 Updated main.py created"
echo ""
echo "🔗 To deploy to EC2, run these commands in EC2 Instance Connect:"
echo ""
echo "cd /home/ubuntu/brahmastra"
echo "cat > main.py << 'EOF'"
echo "# Paste the content from /tmp/main.py"
echo "EOF"
echo "sudo systemctl restart brahmastra"
echo ""
echo "Or copy the file from: /tmp/main.py"
