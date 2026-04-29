# backend/app/db/session.py
"""
Database session management - PostgreSQL / SQLite
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL or "sqlite:///./app.db"
is_sqlite = SQLALCHEMY_DATABASE_URL.startswith("sqlite")

# Create engine
engine_kwargs = {}
if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL: connection pool, pre-ping
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_size"] = settings.DATABASE_POOL_SIZE
    engine_kwargs["max_overflow"] = settings.DATABASE_MAX_OVERFLOW
    engine_kwargs["pool_recycle"] = settings.DATABASE_POOL_RECYCLE
    engine_kwargs["pool_timeout"] = settings.DATABASE_POOL_TIMEOUT

engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_kwargs)

# Create SessionLocal
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# Dependency for FastAPI
def get_db():
    """
    Database dependency for FastAPI endpoints
    Usage: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()