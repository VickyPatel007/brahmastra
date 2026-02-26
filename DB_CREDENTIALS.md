# Database Connection Information

## 🔒 **IMPORTANT: Keep These Credentials Secure!**

**Never commit this file to Git!**

---

## 📊 **Database Details**

- **Endpoint**: `brahmastra-db.ctuc8ygwmfbb.ap-south-1.rds.amazonaws.com:5432`
- **Database Name**: `brahmastra_db`
- **Username**: `brahmastra_admin`
- **Password**: *(Retrieve with: `cd infrastructure && terraform output -raw db_password`)*

---

## 🔗 **Connection String**

```bash
# Format
postgresql://brahmastra_admin:PASSWORD@brahmastra-db.ctuc8ygwmfbb.ap-south-1.rds.amazonaws.com:5432/brahmastra_db

# Get full connection string
cd infrastructure
export DB_PASSWORD=$(terraform output -raw db_password)
echo "postgresql://brahmastra_admin:$DB_PASSWORD@brahmastra-db.ctuc8ygwmfbb.ap-south-1.rds.amazonaws.com:5432/brahmastra_db"
```

---

## 🧪 **Test Connection**

```bash
# Get password
cd infrastructure
export DB_PASSWORD=$(terraform output -raw db_password)

# Test with psql (if installed)
psql "postgresql://brahmastra_admin:$DB_PASSWORD@brahmastra-db.ctuc8ygwmfbb.ap-south-1.rds.amazonaws.com:5432/brahmastra_db"

# Test with Python
python3 << EOF
import psycopg2
conn = psycopg2.connect(
    host="brahmastra-db.ctuc8ygwmfbb.ap-south-1.rds.amazonaws.com",
    port=5432,
    database="brahmastra_db",
    user="brahmastra_admin",
    password="$DB_PASSWORD"
)
print("✅ Connected successfully!")
conn.close()
EOF
```

---

## 🚀 **Next Steps**

1. Set environment variable on EC2
2. Create database tables
3. Update backend to use database
4. Test API endpoints

---

**Created**: 2026-02-14  
**Region**: ap-south-1 (Mumbai)  
**Instance**: db.t3.micro (Free Tier)
