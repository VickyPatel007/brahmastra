#!/bin/bash
# Fixed Database Setup Script for EC2
# Run this on your EC2 instance

set -e

echo "🔧 Setting up Brahmastra Database..."

# Database connection details
export DATABASE_URL="postgresql://brahmastra_admin:F}3C64q:iR+)>hi#@brahmastra-db.ctuc8ygwmfbb.ap-south-1.rds.amazonaws.com:5432/brahmastra_db"

cd /home/ubuntu/brahmastra

# Activate virtual environment
source venv/bin/activate

echo "📦 Installing database dependencies..."
pip install psycopg2-binary sqlalchemy alembic

# Create backend directory structure if it doesn't exist
mkdir -p backend
touch backend/__init__.py

# Create database.py
cat > backend/database.py << 'EOFDB'
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://brahmastra_admin:password@localhost:5432/brahmastra_db"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
EOFDB

# Create models.py
cat > backend/models.py << 'EOFMODELS'
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from datetime import datetime
from backend.database import Base

class Metric(Base):
    __tablename__ = "metrics"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    cpu_percent = Column(Float)
    memory_percent = Column(Float)
    disk_percent = Column(Float)
    status = Column(String(20))

class ThreatScore(Base):
    __tablename__ = "threat_scores"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    threat_score = Column(Integer)
    threat_level = Column(String(20))

class SystemEvent(Base):
    __tablename__ = "system_events"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    event_type = Column(String(50), index=True)
    description = Column(Text)
    severity = Column(String(20))
EOFMODELS

# Create schemas.py
cat > backend/schemas.py << 'EOFSCHEMAS'
from pydantic import BaseModel
from datetime import datetime

class MetricBase(BaseModel):
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    status: str

class MetricResponse(MetricBase):
    id: int
    timestamp: datetime
    class Config:
        from_attributes = True

class ThreatScoreBase(BaseModel):
    threat_score: int
    threat_level: str

class ThreatScoreResponse(ThreatScoreBase):
    id: int
    timestamp: datetime
    class Config:
        from_attributes = True
EOFSCHEMAS

echo "🗄️  Creating database tables..."

# Test database connection and create tables
python3 << 'EOFPYTHON'
import os
os.environ["DATABASE_URL"] = "postgresql://brahmastra_admin:F}3C64q:iR+)>hi#@brahmastra-db.ctuc8ygwmfbb.ap-south-1.rds.amazonaws.com:5432/brahmastra_db"

from backend.database import engine, Base
from backend.models import Metric, ThreatScore, SystemEvent

print("Testing database connection...")
try:
    connection = engine.connect()
    print("✅ Database connection successful!")
    connection.close()
except Exception as e:
    print(f"❌ Connection failed: {e}")
    exit(1)

print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("✅ Database tables created successfully!")

# Verify tables
from sqlalchemy import inspect
inspector = inspect(engine)
tables = inspector.get_table_names()
print(f"📊 Tables created: {tables}")
EOFPYTHON

echo ""
echo "⚙️  Updating systemd service with DATABASE_URL..."

# Update systemd service to include DATABASE_URL
sudo tee /etc/systemd/system/brahmastra.service > /dev/null << EOFSVC
[Unit]
Description=Brahmastra Self-Healing Infrastructure API
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/brahmastra
Environment="PATH=/home/ubuntu/brahmastra/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="DATABASE_URL=postgresql://brahmastra_admin:F}3C64q:iR+)>hi#@brahmastra-db.ctuc8ygwmfbb.ap-south-1.rds.amazonaws.com:5432/brahmastra_db"
ExecStart=/home/ubuntu/brahmastra/venv/bin/python3 /home/ubuntu/brahmastra/main.py
Restart=always
RestartSec=10
StandardOutput=append:/home/ubuntu/brahmastra/app.log
StandardError=append:/home/ubuntu/brahmastra/app.log

[Install]
WantedBy=multi-user.target
EOFSVC

echo "🔄 Reloading and restarting service..."
sudo systemctl daemon-reload
sudo systemctl restart brahmastra

echo ""
echo "⏳ Waiting for service to start..."
sleep 3

echo "🧪 Testing service..."
sudo systemctl status brahmastra --no-pager

echo ""
echo "🌐 Testing API..."
curl http://localhost:8000/health

echo ""
echo "✅ Database setup complete!"
echo ""
echo "📋 Useful commands:"
echo "  - Check service: sudo systemctl status brahmastra"
echo "  - View logs: sudo journalctl -u brahmastra -f"
echo "  - Test API: curl http://localhost:8000/health"
