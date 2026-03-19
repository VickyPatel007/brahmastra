import os
from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://brahmastra_admin:HSwDlwniviFhP5RS@brahmastra-db.ctuc8ygwmfbb.ap-south-1.rds.amazonaws.com:5432/brahmastra_db?sslmode=require"
engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    users = conn.execute(text("SELECT id, email, hashed_password, length(hashed_password) FROM users")).fetchall()
    print("USERS:")
    for u in users:
        print(u)
