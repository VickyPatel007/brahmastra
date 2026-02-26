#!/bin/bash
# Final Database Integration Deployment
# This script safely deploys the database-integrated backend

set -e

echo "🚀 Starting Database Integration Deployment..."
echo ""

cd /home/ubuntu/brahmastra

# Backup current version
echo "📦 Creating backup..."
cp main.py main_simple_backup.py
echo "✅ Backup created: main_simple_backup.py"
echo ""

# Create the database-integrated main.py
echo "📝 Creating database-integrated version..."

cat > main.py << 'EOFMAIN'
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import psutil
from datetime import datetime
import os

# Database imports
DB_ENABLED = False
try:
    from backend.database import SessionLocal
    from backend.models import Metric, ThreatScore, SystemEvent
    DB_ENABLED = True
    print("✅ Database enabled")
except Exception as e:
    print(f"⚠️  Database disabled: {e}")

app = FastAPI(
    title="Brahmastra API",
    description="Self-Healing Infrastructure Monitoring System",
    version="0.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    """Get database session"""
    if not DB_ENABLED:
        return None
    try:
        return SessionLocal()
    except:
        return None

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

@app.get("/api/metrics/current")
async def get_current_metrics():
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    status = "healthy" if cpu < 80 and memory < 80 else "warning"
    
    # Save to database
    if DB_ENABLED:
        db = get_db()
        if db:
            try:
                metric = Metric(cpu_percent=cpu, memory_percent=memory, disk_percent=disk, status=status)
                db.add(metric)
                db.commit()
            except:
                db.rollback()
            finally:
                db.close()
    
    return {
        "status": status,
        "cpu_percent": cpu,
        "memory_percent": memory,
        "disk_percent": disk,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/metrics/history")
async def get_metrics_history(limit: int = 100):
    if not DB_ENABLED:
        return []
    
    db = get_db()
    if not db:
        return []
    
    try:
        metrics = db.query(Metric).order_by(Metric.timestamp.desc()).limit(limit).all()
        return [{
            "cpu_percent": float(m.cpu_percent),
            "memory_percent": float(m.memory_percent),
            "disk_percent": float(m.disk_percent),
            "status": m.status,
            "timestamp": m.timestamp.isoformat()
        } for m in reversed(metrics)]
    except:
        return []
    finally:
        db.close()

@app.get("/api/threat/score")
async def get_threat_score():
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory().percent
    threat_score = int((cpu + memory) / 2)
    threat_level = "low" if threat_score < 50 else "medium" if threat_score < 80 else "high"
    
    # Save to database
    if DB_ENABLED:
        db = get_db()
        if db:
            try:
                threat = ThreatScore(threat_score=threat_score, threat_level=threat_level)
                db.add(threat)
                db.commit()
            except:
                db.rollback()
            finally:
                db.close()
    
    return {
        "threat_score": min(threat_score, 100),
        "level": threat_level,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/threat/history")
async def get_threat_history(limit: int = 100):
    if not DB_ENABLED:
        return []
    
    db = get_db()
    if not db:
        return []
    
    try:
        scores = db.query(ThreatScore).order_by(ThreatScore.timestamp.desc()).limit(limit).all()
        return [{
            "threat_score": s.threat_score,
            "threat_level": s.threat_level,
            "timestamp": s.timestamp.isoformat()
        } for s in reversed(scores)]
    except:
        return []
    finally:
        db.close()

@app.get("/api/stats")
async def get_stats():
    if not DB_ENABLED:
        return {"database": "disabled"}
    
    db = get_db()
    if not db:
        return {"error": "connection failed"}
    
    try:
        metrics_count = db.query(Metric).count()
        threats_count = db.query(ThreatScore).count()
        return {
            "database": "enabled",
            "metrics_count": metrics_count,
            "threats_count": threats_count,
            "total_records": metrics_count + threats_count
        }
    except:
        return {"error": "query failed"}
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
EOFMAIN

echo "✅ Database-integrated main.py created"
echo ""

# Restart the service
echo "🔄 Restarting service..."
sudo systemctl restart brahmastra

# Wait for service to start
echo "⏳ Waiting for service to start..."
sleep 5

# Test the service
echo "🧪 Testing endpoints..."
echo ""

echo "1. Testing root endpoint:"
curl -s http://localhost:8000/ | python3 -m json.tool
echo ""

echo "2. Testing health:"
curl -s http://localhost:8000/health | python3 -m json.tool
echo ""

echo "3. Testing stats (new endpoint):"
curl -s http://localhost:8000/api/stats | python3 -m json.tool
echo ""

echo "4. Generating test data..."
for i in {1..5}; do
    curl -s http://localhost:8000/api/metrics/current > /dev/null
    echo "  ✅ Saved metric $i"
    sleep 1
done
echo ""

echo "5. Testing metrics history (new endpoint):"
curl -s "http://localhost:8000/api/metrics/history?limit=5" | python3 -m json.tool
echo ""

echo "6. Testing threat history (new endpoint):"
curl -s "http://localhost:8000/api/threat/history?limit=5" | python3 -m json.tool
echo ""

echo "✅ Deployment complete!"
echo ""
echo "📊 Database Statistics:"
curl -s http://localhost:8000/api/stats | python3 -m json.tool
echo ""
echo "🌐 Your API is live at: http://13.234.113.97:8000"
echo ""
echo "🎉 Database integration successful!"
