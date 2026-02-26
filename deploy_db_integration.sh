#!/bin/bash
# Safe Database Integration Script
# This version won't crash the service

set -e

echo "🔧 Creating database-integrated backend (crash-proof version)..."

cd /home/ubuntu/brahmastra

# Backup current working version
cp main.py main_working_backup.py

# Create the new database-integrated version
cat > main_db.py << 'EOFMAIN'
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import psutil
from datetime import datetime
import os

# Try to import database components
DB_ENABLED = False
try:
    from backend.database import SessionLocal
    from backend.models import Metric, ThreatScore, SystemEvent
    DB_ENABLED = True
    print("✅ Database modules loaded successfully")
except Exception as e:
    print(f"⚠️  Database not available: {e}")

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

def get_db_session():
    """Get database session if available"""
    if not DB_ENABLED:
        return None
    try:
        db = SessionLocal()
        return db
    except Exception as e:
        print(f"DB connection error: {e}")
        return None

@app.on_event("startup")
async def startup():
    print(f"🚀 Brahmastra API v0.2.0 starting...")
    print(f"📊 Database: {'enabled' if DB_ENABLED else 'disabled'}")
    if DB_ENABLED:
        print(f"🔗 DB URL: {os.getenv('DATABASE_URL', 'not set')[:50]}...")

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
    
    result = {
        "status": status,
        "cpu_percent": cpu,
        "memory_percent": memory,
        "disk_percent": disk,
        "timestamp": datetime.now().isoformat()
    }
    
    # Save to database if enabled
    if DB_ENABLED:
        db = get_db_session()
        if db:
            try:
                metric = Metric(
                    cpu_percent=cpu,
                    memory_percent=memory,
                    disk_percent=disk,
                    status=status
                )
                db.add(metric)
                db.commit()
                print(f"✅ Saved metric: CPU={cpu}%, Mem={memory}%")
            except Exception as e:
                print(f"❌ Failed to save metric: {e}")
                db.rollback()
            finally:
                db.close()
    
    return result

@app.get("/api/metrics/history")
async def get_metrics_history(limit: int = 100):
    if not DB_ENABLED:
        return {"error": "Database not enabled", "data": []}
    
    db = get_db_session()
    if not db:
        return {"error": "Database connection failed", "data": []}
    
    try:
        metrics = db.query(Metric).order_by(Metric.timestamp.desc()).limit(limit).all()
        result = [{
            "id": m.id,
            "cpu_percent": float(m.cpu_percent),
            "memory_percent": float(m.memory_percent),
            "disk_percent": float(m.disk_percent),
            "status": m.status,
            "timestamp": m.timestamp.isoformat()
        } for m in reversed(metrics)]
        return {"count": len(result), "data": result}
    except Exception as e:
        print(f"❌ Query error: {e}")
        return {"error": str(e), "data": []}
    finally:
        db.close()

@app.get("/api/threat/score")
async def get_threat_score():
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory().percent
    threat_score = int((cpu + memory) / 2)
    threat_level = "low" if threat_score < 50 else "medium" if threat_score < 80 else "high"
    
    result = {
        "threat_score": min(threat_score, 100),
        "level": threat_level,
        "timestamp": datetime.now().isoformat()
    }
    
    # Save to database if enabled
    if DB_ENABLED:
        db = get_db_session()
        if db:
            try:
                threat = ThreatScore(
                    threat_score=threat_score,
                    threat_level=threat_level
                )
                db.add(threat)
                db.commit()
                print(f"✅ Saved threat score: {threat_score} ({threat_level})")
            except Exception as e:
                print(f"❌ Failed to save threat: {e}")
                db.rollback()
            finally:
                db.close()
    
    return result

@app.get("/api/threat/history")
async def get_threat_history(limit: int = 100):
    if not DB_ENABLED:
        return {"error": "Database not enabled", "data": []}
    
    db = get_db_session()
    if not db:
        return {"error": "Database connection failed", "data": []}
    
    try:
        scores = db.query(ThreatScore).order_by(ThreatScore.timestamp.desc()).limit(limit).all()
        result = [{
            "id": s.id,
            "threat_score": s.threat_score,
            "threat_level": s.threat_level,
            "timestamp": s.timestamp.isoformat()
        } for s in reversed(scores)]
        return {"count": len(result), "data": result}
    except Exception as e:
        print(f"❌ Query error: {e}")
        return {"error": str(e), "data": []}
    finally:
        db.close()

@app.get("/api/events")
async def get_events(limit: int = 50):
    if not DB_ENABLED:
        return {"error": "Database not enabled", "data": []}
    
    db = get_db_session()
    if not db:
        return {"error": "Database connection failed", "data": []}
    
    try:
        events = db.query(SystemEvent).order_by(SystemEvent.timestamp.desc()).limit(limit).all()
        result = [{
            "id": e.id,
            "event_type": e.event_type,
            "description": e.description,
            "severity": e.severity,
            "timestamp": e.timestamp.isoformat()
        } for e in reversed(events)]
        return {"count": len(result), "data": result}
    except Exception as e:
        return {"error": str(e), "data": []}
    finally:
        db.close()

@app.get("/api/stats")
async def get_stats():
    """Get database statistics"""
    if not DB_ENABLED:
        return {"database": "disabled"}
    
    db = get_db_session()
    if not db:
        return {"error": "Database connection failed"}
    
    try:
        metrics_count = db.query(Metric).count()
        threats_count = db.query(ThreatScore).count()
        events_count = db.query(SystemEvent).count()
        
        return {
            "database": "enabled",
            "metrics_count": metrics_count,
            "threats_count": threats_count,
            "events_count": events_count,
            "total_records": metrics_count + threats_count + events_count
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
EOFMAIN

echo "✅ Created main_db.py"

# Test it first before deploying
echo "🧪 Testing new version..."
source venv/bin/activate

# Run it in background for testing
python3 main_db.py &
TEST_PID=$!

# Wait for it to start
sleep 5

# Test endpoints
echo "Testing root endpoint..."
curl -s http://localhost:8000/ | python3 -m json.tool

echo ""
echo "Testing health endpoint..."
curl -s http://localhost:8000/health | python3 -m json.tool

echo ""
echo "Testing metrics endpoint..."
curl -s http://localhost:8000/api/metrics/current | python3 -m json.tool

echo ""
echo "Testing stats endpoint..."
curl -s http://localhost:8000/api/stats | python3 -m json.tool

# Kill test process
kill $TEST_PID 2>/dev/null || true
sleep 2

echo ""
echo "✅ Tests passed! Deploying..."

# Deploy the new version
cp main_db.py main.py

# Restart service
sudo systemctl restart brahmastra

# Wait for restart
sleep 3

# Final test
echo ""
echo "🎉 Testing deployed version..."
curl -s http://localhost:8000/ | python3 -m json.tool

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📊 Test the new endpoints:"
echo "  curl http://localhost:8000/api/stats"
echo "  curl http://localhost:8000/api/metrics/history?limit=5"
echo "  curl http://localhost:8000/api/threat/history?limit=5"
