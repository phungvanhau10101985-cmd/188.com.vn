"""
Wipe taxonomy migration (migration lần đầu): DELETE products + DROP bảng category/SEO rồi create_all.

Chỉ dùng qua CLI `scripts/wipe_taxonomy_migration.py` — không có route HTTP để tránh wipe nhầm qua browser/token.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import engine
from app.utils.ttl_cache import cache as ttl_cache

# Thứ tự DROP an toàn (con trước, cha sau) để không vướng FK.
WIPE_TABLES_ORDER = [
    "category_seo_meta",
    "category_seo_mappings",
    "category_seo_dictionary",
    "category_transform_rules",
    "category_final_mappings",
    "categories",
    "seo_clusters",
]


def execute_taxonomy_migration_wipe(db: Session, *, dry_run: bool = False) -> Dict[str, Any]:
    """
    Xóa rows products, DROP các bảng taxonomy/SEO trong WIPE_TABLES_ORDER, tái tạo schema.

    Trả `{ok, wiped, dropped, created, elapsed_ms, dry_run}`.
    dry_run=True: chỉ đếm bảng, không ghi DB.
    """
    started = time.time()
    insp = inspect(engine)

    counts_before: Dict[str, int] = {}
    for t in ["products"] + WIPE_TABLES_ORDER:
        if insp.has_table(t):
            try:
                counts_before[t] = db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() or 0
            except Exception:
                counts_before[t] = -1

    dialect = engine.dialect.name
    cascade_clause = " CASCADE" if dialect == "postgresql" else ""

    dropped: List[str] = []
    created: List[str] = []

    if dry_run:
        elapsed_ms = int((time.time() - started) * 1000)
        return {
            "ok": True,
            "wiped": counts_before,
            "dropped": dropped,
            "created": created,
            "elapsed_ms": elapsed_ms,
            "dry_run": True,
        }

    # Xóa rows products trước (FK products.category_id)
    if insp.has_table("products"):
        db.execute(text("DELETE FROM products"))
        db.commit()

    for t in WIPE_TABLES_ORDER:
        if insp.has_table(t):
            db.execute(text(f"DROP TABLE IF EXISTS {t}{cascade_clause}"))
            dropped.append(t)
    db.commit()

    insp = inspect(engine)
    target_tables = [
        Base.metadata.tables[t]
        for t in WIPE_TABLES_ORDER
        if t in Base.metadata.tables and not insp.has_table(t)
    ]
    if target_tables:
        Base.metadata.create_all(bind=engine, tables=target_tables)
        created = [t.name for t in target_tables]

    ttl_cache.invalidate_all()

    elapsed_ms = int((time.time() - started) * 1000)
    return {
        "ok": True,
        "wiped": counts_before,
        "dropped": dropped,
        "created": created,
        "elapsed_ms": elapsed_ms,
        "dry_run": False,
    }
