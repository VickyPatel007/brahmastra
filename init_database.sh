#!/bin/bash
# Initialize Brahmastra Database on EC2

set -e

echo "🔧 Initializing Brahmastra Database..."

# Get database password from Terraform
cd /Users/vivekpatel/.gemini/antigravity/scratch/brahmastra/infrastructure
DB_PASSWORD=$(terraform output -raw db_password)
DB_ENDPOINT="brahmastra-db.ctuc8ygwmfbb.ap-south-1.rds.amazonaws.com"
DB_NAME="brahmastra_db"
DB_USER="brahmastra_admin"

# Create DATABASE_URL
DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_ENDPOINT}/${DB_NAME}"

echo "✅ Database credentials retrieved"
echo "📊 Endpoint: $DB_ENDPOINT"

# SSH to EC2 and set up database
echo "🚀 Connecting to EC2 to set up database..."

# Note: This requires SSH access. For now, we'll create a setup script
# that can be run manually on EC2

cat > ../setup_database_on_ec2.sh << 'EOFSCRIPT'
#!/bin/bash
# Run this script on EC2 instance

set -e

echo "🔧 Setting up database on EC2..."

# Set DATABASE_URL environment variable
export DATABASE_URL="$1"

cd /home/ubuntu/brahmastra

# Activate virtual environment
source venv/bin/activate

# Install database dependencies
echo "📦 Installing database dependencies..."
pip install psycopg2-binary sqlalchemy alembic

# Create database tables
echo "🗄️  Creating database tables..."
python3 << 'EOFPYTHON'
from backend.database import engine, Base
from backend.models import Metric, ThreatScore, SystemEvent

# Create all tables
Base.metadata.create_all(bind=engine)
print("✅ Database tables created successfully!")
EOFPYTHON

# Add DATABASE_URL to systemd service
echo "⚙️  Updating systemd service..."
sudo sed -i '/Environment="PATH=/a Environment="DATABASE_URL='"$DATABASE_URL"'"' /etc/systemd/system/brahmastra.service

# Reload and restart service
sudo systemctl daemon-reload
sudo systemctl restart brahmastra

echo "✅ Database setup complete!"
echo "🧪 Testing database connection..."

curl http://localhost:8000/health

EOFSCRIPT

chmod +x ../setup_database_on_ec2.sh

echo "✅ Setup script created: setup_database_on_ec2.sh"
echo ""
echo "📋 Next steps:"
echo "1. Connect to EC2 Instance Connect"
echo "2. Run: curl -O https://raw.githubusercontent.com/YOUR_REPO/setup_database_on_ec2.sh"
echo "   OR manually copy the script content"
echo "3. Run: bash setup_database_on_ec2.sh '$DATABASE_URL'"
echo ""
echo "🔗 DATABASE_URL: $DATABASE_URL"
