# backend/app/db/session.py
"""
Database session management - PostgreSQL / SQLite
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.db.pool_relief import apply_postgres_connect_timeouts

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
    # Trả connection về pool sạch sau mỗi request — giảm «idle in transaction» tích tụ.
    engine_kwargs["pool_reset_on_return"] = "rollback"
    # Giữ TCP sống để giảm lỗi "SSL connection has been closed unexpectedly"
    # khi kết nối idle lâu qua proxy/LB.
    engine_kwargs["connect_args"] = apply_postgres_connect_timeouts(
        {
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        }
    )

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
    except Exception:
        db.rollback()
        raise
    finally:
        db.rollback()
        db.close()