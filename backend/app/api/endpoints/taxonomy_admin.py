# backend/app/api/endpoints/taxonomy_admin.py
"""
Admin endpoint quản lý taxonomy (cây danh mục + SEO cluster) qua file Excel 4 sheet.

- POST /api/v1/taxonomy/wipe   : xóa products + 6 bảng category/seo cũ, tạo lại schema mới.
- POST /api/v1/taxonomy/import : upload taxonomy_import.xlsx → seed categories + seo_clusters.
- GET  /api/v1/taxonomy/sample : tải file mẫu nếu có (`backend/temp_uploads/taxonomy_import.xlsx`).

Yêu cầu Bearer admin (Depends(get_current_admin)). Idempotent: import có thể chạy lại nhiều lần,
upsert theo `external_id` (cột `id` trong Excel).
"""
from __future__ import annotations

import io
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app import models
from app.core.security import get_current_admin
from app.db.base import Base
from app.db.session import engine, get_db
from app.models.category import Category
from app.models.seo_cluster import SeoCluster
from app.utils.ttl_cache import cache as ttl_cache

logger = logging.getLogger(__name__)
router = APIRouter()

REQUIRED_SHEETS = {"categories", "category_paths", "seo_clusters", "meta"}

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


def _truthy_active(val: Any) -> bool:
    s = str(val).strip().lower()
    return s in ("1", "true", "yes", "y")


def _truthy_index(val: Any) -> bool:
    s = str(val).strip().lower()
    return s == "index"


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(str(val).strip() or default)
    except (TypeError, ValueError):
        return default


# ---------- WIPE ----------
@router.post("/wipe")
def wipe_taxonomy_and_products(
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
) -> Dict[str, Any]:
    """
    Xóa products + 7 bảng taxonomy/SEO cũ, sau đó tạo lại theo schema mới.
    GIỮ NGUYÊN orders/users/cart/notifications/...

    Trả `{wiped: {...}, created: [...], elapsed_ms}`.
    """
    started = time.time()
    insp = inspect(engine)

    # Đếm trước khi xoá
    counts_before: Dict[str, int] = {}
    for t in ["products"] + WIPE_TABLES_ORDER:
        if insp.has_table(t):
            try:
                counts_before[t] = db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() or 0
            except Exception:
                counts_before[t] = -1

    # Xoá row trong products trước (để FK products.category_id không vướng khi DROP categories)
    if insp.has_table("products"):
        db.execute(text("DELETE FROM products"))
        db.commit()

    # DROP TABLE CASCADE (Postgres) — bảng cũ có thể không có cột mới (vd parent_id);
    # cách an toàn nhất là drop rồi để Base.metadata.create_all dựng lại.
    dialect = engine.dialect.name
    cascade_clause = " CASCADE" if dialect == "postgresql" else ""
    dropped: List[str] = []
    for t in WIPE_TABLES_ORDER:
        if insp.has_table(t):
            db.execute(text(f"DROP TABLE IF EXISTS {t}{cascade_clause}"))
            dropped.append(t)
    db.commit()

    # Re-create từ Base.metadata
    insp = inspect(engine)
    created: List[str] = []
    target_tables = [
        Base.metadata.tables[t]
        for t in WIPE_TABLES_ORDER
        if t in Base.metadata.tables and not insp.has_table(t)
    ]
    if target_tables:
        Base.metadata.create_all(bind=engine, tables=target_tables)
        created = [t.name for t in target_tables]

    # Reset cache cây danh mục cũ (kẻo trả tree cũ)
    ttl_cache.invalidate_all()

    elapsed_ms = int((time.time() - started) * 1000)
    return {
        "ok": True,
        "wiped": counts_before,
        "dropped": dropped,
        "created": created,
        "elapsed_ms": elapsed_ms,
    }


# ---------- IMPORT ----------
def _parse_upload(file_bytes: bytes) -> Dict[str, pd.DataFrame]:
    sheets = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None, dtype=str)
    sheets = {k: v.fillna("") for k, v in sheets.items()}
    missing = REQUIRED_SHEETS - set(sheets.keys())
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"File thiếu sheet bắt buộc: {sorted(missing)}. Có: {sorted(sheets.keys())}",
        )
    return sheets


def _upsert_clusters(db: Session, df: pd.DataFrame) -> Tuple[Dict[str, int], List[str]]:
    """Upsert SeoCluster theo external_id. Trả map external_id → db_id và list lỗi."""
    errors: List[str] = []
    ext_to_id: Dict[str, int] = {}

    # Map các cluster hiện có
    existing = {c.external_id: c for c in db.query(SeoCluster).all()}

    for idx, row in df.iterrows():
        ext_id = str(row.get("id") or "").strip()
        if not ext_id:
            errors.append(f"seo_clusters row {idx + 2}: thiếu cột id")
            continue
        slug = str(row.get("slug") or "").strip()
        name = str(row.get("name") or "").strip()
        if not slug or not name:
            errors.append(f"seo_clusters row {idx + 2}: thiếu slug hoặc name")
            continue

        canonical_path = str(row.get("canonical_path") or f"/c/{slug}").strip()
        index_policy = str(row.get("index_policy") or "index").strip().lower() or "index"
        source = str(row.get("source") or "auto_from_cat3").strip() or "auto_from_cat3"
        notes = str(row.get("notes") or "").strip() or None

        c = existing.get(ext_id)
        if c is None:
            c = SeoCluster(external_id=ext_id)
            db.add(c)
        c.slug = slug
        c.name = name
        c.canonical_path = canonical_path
        c.index_policy = index_policy
        c.source = source
        c.notes = notes
        existing[ext_id] = c

    db.flush()
    for ext_id, c in existing.items():
        ext_to_id[ext_id] = c.id
    db.commit()
    return ext_to_id, errors


def _insert_categories(
    db: Session, df: pd.DataFrame, cluster_ext_to_id: Dict[str, int]
) -> Tuple[Dict[str, int], Dict[str, int], List[str]]:
    """
    Insert/upsert Category theo external_id, sắp xếp theo level 1 → 2 → 3 để parent_id sẵn sàng.
    Trả: (cat_ext_to_id, summary_by_level, errors).
    """
    errors: List[str] = []

    # Chuẩn hoá level + sort
    df = df.copy()
    df["__level"] = df["level"].apply(_safe_int)
    df = df.sort_values(by=["__level"]).reset_index(drop=True)

    # Map ext_id → db_id (load các cat đã có nếu có)
    existing = {c.external_id: c for c in db.query(Category).all() if c.external_id}
    cat_ext_to_id: Dict[str, int] = {ext: c.id for ext, c in existing.items()}
    summary: Dict[str, int] = {1: 0, 2: 0, 3: 0}

    for idx, row in df.iterrows():
        ext_id = str(row.get("id") or "").strip()
        if not ext_id:
            errors.append(f"categories row {idx + 2}: thiếu id")
            continue

        level = _safe_int(row.get("level"), 0)
        if level not in (1, 2, 3):
            errors.append(f"categories row {idx + 2} ({ext_id}): level không hợp lệ ({row.get('level')!r})")
            continue

        name = str(row.get("name") or "").strip()
        slug = str(row.get("slug") or "").strip()
        full_slug = str(row.get("full_slug") or "").strip()
        if not name or not slug or not full_slug:
            errors.append(f"categories row {idx + 2} ({ext_id}): thiếu name/slug/full_slug")
            continue

        parent_ext = str(row.get("parent_id") or "").strip()
        parent_db_id: Optional[int] = None
        if parent_ext:
            parent_db_id = cat_ext_to_id.get(parent_ext)
            if not parent_db_id:
                errors.append(
                    f"categories row {idx + 2} ({ext_id}): parent_id={parent_ext} không tồn tại (level đang xử lý {level})"
                )
                continue

        cluster_ext = str(row.get("seo_cluster_id") or "").strip()
        cluster_db_id: Optional[int] = None
        if cluster_ext:
            cluster_db_id = cluster_ext_to_id.get(cluster_ext)
            if not cluster_db_id:
                errors.append(
                    f"categories row {idx + 2} ({ext_id}): seo_cluster_id={cluster_ext} không có trong sheet seo_clusters"
                )

        c = existing.get(ext_id)
        if c is None:
            c = Category(external_id=ext_id)
            db.add(c)
        c.parent_id = parent_db_id
        c.level = level
        c.name = name
        c.slug = slug
        c.full_slug = full_slug
        c.sort_order = _safe_int(row.get("sort_order"), 0)
        c.is_active = _truthy_active(row.get("is_active"))
        c.seo_index = _truthy_index(row.get("seo_index"))
        c.seo_cluster_id = cluster_db_id

        db.flush()  # cần id ngay để cấp dưới có parent
        cat_ext_to_id[ext_id] = c.id
        existing[ext_id] = c
        summary[level] = summary.get(level, 0) + 1

    db.commit()
    return cat_ext_to_id, summary, errors


def _validate_paths(
    df: pd.DataFrame, cat_ext_to_id: Dict[str, int], cluster_ext_to_id: Dict[str, int]
) -> List[str]:
    """Đối chiếu sheet category_paths: mỗi cat3_id phải tồn tại sau Pass 2."""
    errs: List[str] = []
    for idx, row in df.iterrows():
        cat3 = str(row.get("cat3_id") or "").strip()
        if cat3 and cat3 not in cat_ext_to_id:
            errs.append(f"category_paths row {idx + 2}: cat3_id={cat3} không có trong sheet categories")
        cluster = str(row.get("seo_cluster_id") or "").strip()
        if cluster and cluster not in cluster_ext_to_id:
            errs.append(f"category_paths row {idx + 2}: seo_cluster_id={cluster} không có trong sheet seo_clusters")
    return errs


@router.post("/import")
async def import_taxonomy(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
) -> Dict[str, Any]:
    """
    Upload taxonomy_import.xlsx (4 sheet) — seed cây + cluster.
    Upsert theo external_id, an toàn re-import.
    """
    started = time.time()
    name = (file.filename or "").lower()
    if not name.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận file .xlsx hoặc .xls")

    raw = await file.read()
    sheets = _parse_upload(raw)

    df_clusters = sheets["seo_clusters"]
    df_cats = sheets["categories"]
    df_paths = sheets["category_paths"]
    df_meta = sheets["meta"]

    cluster_ext_to_id, e_clusters = _upsert_clusters(db, df_clusters)
    cat_ext_to_id, summary_lvl, e_cats = _insert_categories(db, df_cats, cluster_ext_to_id)
    e_paths = _validate_paths(df_paths, cat_ext_to_id, cluster_ext_to_id)

    # Reset cache để menu/cluster công khai cập nhật ngay
    ttl_cache.invalidate_all()

    meta_kv: Dict[str, str] = {}
    if {"key", "value"} <= set(df_meta.columns):
        for _, row in df_meta.iterrows():
            k = str(row.get("key") or "").strip()
            v = str(row.get("value") or "").strip()
            if k:
                meta_kv[k] = v

    elapsed_ms = int((time.time() - started) * 1000)
    return {
        "ok": True,
        "summary": {
            "cat1": summary_lvl.get(1, 0),
            "cat2": summary_lvl.get(2, 0),
            "cat3": summary_lvl.get(3, 0),
            "clusters": len(cluster_ext_to_id),
        },
        "errors": {
            "seo_clusters": e_clusters,
            "categories": e_cats,
            "category_paths": e_paths,
        },
        "meta": meta_kv,
        "elapsed_ms": elapsed_ms,
    }


# ---------- SAMPLE FILE ----------
@router.get("/sample")
def download_sample_taxonomy_file(
    _admin: models.AdminUser = Depends(get_current_admin),
):
    """Trả file mẫu `backend/temp_uploads/taxonomy_import.xlsx` nếu admin đã upload sẵn."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.normpath(os.path.join(here, "..", "..", "..", "temp_uploads", "taxonomy_import.xlsx"))
    if not os.path.exists(candidate):
        raise HTTPException(
            status_code=404,
            detail="Chưa có file mẫu — đặt taxonomy_import.xlsx trong backend/temp_uploads/.",
        )
    return FileResponse(
        candidate,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="taxonomy_import.xlsx",
    )


# ---------- INFO ----------
@router.get("/info")
def taxonomy_info(
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
) -> Dict[str, Any]:
    """Tổng quan trạng thái hiện tại: số cat1/2/3, số cluster, số sản phẩm."""
    cat1 = db.query(Category).filter(Category.level == 1).count()
    cat2 = db.query(Category).filter(Category.level == 2).count()
    cat3 = db.query(Category).filter(Category.level == 3).count()
    clusters = db.query(SeoCluster).count()
    products = db.execute(text("SELECT COUNT(*) FROM products")).scalar() or 0
    products_linked = db.execute(
        text("SELECT COUNT(*) FROM products WHERE category_id IS NOT NULL")
    ).scalar() or 0
    return {
        "categories": {"cat1": cat1, "cat2": cat2, "cat3": cat3},
        "clusters": clusters,
        "products": {"total": products, "linked_to_cat3": products_linked},
    }
