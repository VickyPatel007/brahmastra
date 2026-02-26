#!/bin/bash
# Script to update Brahmastra backend files on EC2 with authentication

echo "🔐 Updating Brahmastra with Authentication Support"
echo "=================================================="

# Navigate to brahmastra directory
cd /home/ubuntu/brahmastra/backend || exit 1

echo ""
echo "📦 Step 1: Installing new dependencies..."
pip3 install python-jose[cryptography] passlib[bcrypt]

echo ""
echo "🗄️  Step 2: Creating users table in database..."
python3 << 'PYEOF'
import sys
sys.path.insert(0, '/home/ubuntu/brahmastra')

try:
    from backend.database import engine
    from backend.models import Base, User
    
    print("Creating users table...")
    Base.metadata.create_all(bind=engine)
    print("✅ Users table created successfully!")
except Exception as e:
    print(f"❌ Error: {e}")
    print("This is normal if table already exists")
PYEOF

echo ""
echo "🔄 Step 3: Restarting backend service..."
sudo systemctl restart brahmastra

echo ""
echo "⏳ Waiting for service to start..."
sleep 3

echo ""
echo "📊 Step 4: Checking service status..."
sudo systemctl status brahmastra --no-pager -l

echo ""
echo "✅ Deployment complete!"
echo ""
echo "🧪 Test the authentication:"
echo "1. Register: curl -X POST http://13.234.113.97:8000/api/auth/register -H 'Content-Type: application/json' -d '{\"email\":\"test@example.com\",\"password\":\"test123\",\"full_name\":\"Test User\"}'"
echo "2. Login: curl -X POST http://13.234.113.97:8000/api/auth/login -H 'Content-Type: application/json' -d '{\"email\":\"test@example.com\",\"password\":\"test123\"}'"
echo "3. Check API docs: http://13.234.113.97:8000/docs"
