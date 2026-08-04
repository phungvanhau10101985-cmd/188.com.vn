"""
Engine/pool RIÊNG cho các tác vụ đọc nặng, chạy lâu (export Excel toàn catalog,
đồng bộ Google Sheet catalog ~41 cột). Mục đích: không giữ connection của pool
chính (dùng cho PDP/listing của khách) trong suốt vài phút quét ~100k sản phẩm —
tránh lỗi 503 "Cơ sở dữ liệu tạm thời không phản hồi" cho khách trong lúc sync/export chạy.

Pool này CHỦ ĐỘNG nhỏ (mặc định 2 + overflow 1) vì chỉ 1 job chạy tại một thời điểm
(đã có _SYNC_LOCK / lock tương tự ở nơi gọi).
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.session import SQLALCHEMY_DATABASE_URL, is_sqlite

if is_sqlite:
    _export_engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    from app.db.pool_relief import apply_postgres_connect_timeouts

    _export_engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=settings.DATABASE_EXPORT_POOL_SIZE,
        max_overflow=settings.DATABASE_EXPORT_MAX_OVERFLOW,
        pool_recycle=settings.DATABASE_POOL_RECYCLE,
        pool_timeout=settings.DATABASE_POOL_TIMEOUT,
        pool_reset_on_return="rollback",
        connect_args=apply_postgres_connect_timeouts(
            {
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5,
            }
        ),
    )

ExportSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_export_engine)


def get_export_db_session():
    """Mở session riêng cho job export/sync nặng — nhớ close() trong finally."""
    return ExportSessionLocal()
