"""
Database configuration and connection management for Brahmastra
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Load .env file if present (for local development)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — env vars must be set manually

# Database URL will be set via environment variable
# Supports both single DATABASE_URL or individual components (for passwords with special chars)
_db_host = os.getenv("DB_HOST")
_db_user = os.getenv("DB_USER")
_db_pass = os.getenv("DB_PASSWORD")
_db_name = os.getenv("DB_NAME")
_db_port = os.getenv("DB_PORT", "5432")
_db_ssl  = os.getenv("DB_SSLMODE", "require")

if _db_host and _db_user and _db_pass and _db_name:
    # Build URL from individual components (avoids URL-encoding issues)
    from urllib.parse import quote_plus
    DATABASE_URL = (
        f"postgresql://{quote_plus(_db_user)}:{quote_plus(_db_pass)}"
        f"@{_db_host}:{_db_port}/{_db_name}?sslmode={_db_ssl}"
    )
else:
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://brahmastra_admin:password@localhost:5432/brahmastra_db"
    )

# Create SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=5,          # Connection pool size
    max_overflow=10       # Max overflow connections
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
