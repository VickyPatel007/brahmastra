#!/bin/bash
# Database migration script to create users table

echo "🔐 Creating users table in database..."

# Create migration script
cat > /tmp/create_users_table.py << 'EOF'
import sys
sys.path.insert(0, '/home/ubuntu/brahmastra')

from backend.database import engine
from backend.models import Base, User

print("Creating users table...")
Base.metadata.create_all(bind=engine)
print("✅ Users table created successfully!")
EOF

# Run the migration
python3 /tmp/create_users_table.py

echo "✅ Database migration complete!"
