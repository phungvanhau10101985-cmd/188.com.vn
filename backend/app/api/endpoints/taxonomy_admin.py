# backend/app/api/endpoints/taxonomy_admin.py
"""
Admin endpoint quản lý taxonomy (cây danh mục + SEO cluster) qua file Excel 4 sheet.

- POST /api/v1/taxonomy/wipe   : xóa products + 6 bảng category/seo cũ, tạo lại schema mới.
- POST /api/v1/taxonomy/import : upload taxonomy_import.xlsx → seed categories + seo_clusters.
- GET  /api/v1/taxonomy/sample : ưu tiên `temp_uploads/taxonomy_import.xlsx` (dữ liệu đầy đủ),
  sau đó `assets/taxonomy_import_template.xlsx` (mẫu đủ cột + vài dòng minh họa),
  cuối cùng sinh workbook trong code (cùng schema).

Yêu cầu Bearer admin (Depends(get_current_admin)). Idempotent: import có thể chạy lại nhiều lần,
upsert theo `external_id` (cột `id` trong Excel).
"""
from __future__ import annotations

import io
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
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

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_ATTACHMENT_TAXONOMY = 'attachment; filename="taxonomy_import.xlsx"'


def _taxonomy_backend_dir() -> Path:
    """Thư mục `backend/` (cha của package `app`)."""
    return Path(__file__).resolve().parents[3]


def _taxonomy_sample_disk_path() -> Path:
    """File taxonomy đầy đủ dòng — thường commit (`backend/temp_uploads/taxonomy_import.xlsx`)."""
    return _taxonomy_backend_dir() / "temp_uploads" / "taxonomy_import.xlsx"


def _taxonomy_bundled_schema_template_path() -> Path:
    """Mẫu đủ sheet/cột + ví dụ ít dòng — trong repo (`backend/assets/taxonomy_import_template.xlsx`)."""
    return _taxonomy_backend_dir() / "assets" / "taxonomy_import_template.xlsx"


# Đủ cột khớp file taxonomy production (sheet category_paths có thêm mô tả cat1–cat3).
TAXONOMY_TEMPLATE_CATEGORY_PATH_COLUMNS: Tuple[str, ...] = (
    "cat1_id",
    "cat1_name",
    "cat1_slug",
    "cat2_id",
    "cat2_name",
    "cat2_slug",
    "cat3_id",
    "cat3_name",
    "cat3_slug",
    "full_slug",
    "seo_cluster_id",
    "seo_cluster_slug",
)


def _standard_taxonomy_template_bytes() -> bytes:
    """Workbook 4 sheet — đủ mọi cột trên từng sheet (category_paths đủ 12 cột); vài dòng ví dụ import được."""
    buf = io.BytesIO()
    cat_cols = [
        "id",
        "parent_id",
        "level",
        "name",
        "slug",
        "full_slug",
        "sort_order",
        "is_active",
        "seo_index",
        "seo_cluster_id",
    ]
    cluster_cols = ["id", "slug", "name", "canonical_path", "index_policy", "source", "notes"]
    cluster_rows = [
        {
            "id": "cluster__dep-sandal-nu-quai-ngang",
            "slug": "dep-sandal-nu-quai-ngang",
            "name": "Dép sandal nữ quai ngang",
            "canonical_path": "/c/dep-sandal-nu-quai-ngang",
            "index_policy": "index",
            "source": "sample_template",
            "notes": "Xóa/sửa — đây chỉ là ví dụ.",
        },
        {
            "id": "cluster__dep-tong-nu-xop-mot",
            "slug": "dep-tong-nu-xop-mot",
            "name": "Dép tông nữ xốp một",
            "canonical_path": "/c/dep-tong-nu-xop-mot",
            "index_policy": "index",
            "source": "sample_template",
            "notes": "",
        },
        {
            "id": "cluster__sneaker-giay-bet-nu",
            "slug": "sneaker-giay-bet-nu",
            "name": "Sneaker & giày bệt nữ",
            "canonical_path": "/c/sneaker-giay-bet-nu",
            "index_policy": "index",
            "source": "sample_template",
            "notes": "",
        },
    ]
    cat_rows = [
        {
            "id": "cat1__giay-dep-nu",
            "parent_id": "",
            "level": 1,
            "name": "Giày dép nữ",
            "slug": "giay-dep-nu",
            "full_slug": "giay-dep-nu",
            "sort_order": 1,
            "is_active": "1",
            "seo_index": "index",
            "seo_cluster_id": "",
        },
        {
            "id": "cat2__giay-dep-nu__dep-sandal-nu",
            "parent_id": "cat1__giay-dep-nu",
            "level": 2,
            "name": "Dép sandal Nữ",
            "slug": "dep-sandal-nu",
            "full_slug": "giay-dep-nu/dep-sandal-nu",
            "sort_order": 1,
            "is_active": "1",
            "seo_index": "index",
            "seo_cluster_id": "",
        },
        {
            "id": "cat2__giay-dep-nu__sneaker-giay-bet-nu",
            "parent_id": "cat1__giay-dep-nu",
            "level": 2,
            "name": "Sneaker & giày bệt",
            "slug": "sneaker-giay-bet-nu",
            "full_slug": "giay-dep-nu/sneaker-giay-bet-nu",
            "sort_order": 2,
            "is_active": "1",
            "seo_index": "index",
            "seo_cluster_id": "",
        },
        {
            "id": "cat3__giay-dep-nu__dep-sandal-nu__dep-quai-ngang-nu",
            "parent_id": "cat2__giay-dep-nu__dep-sandal-nu",
            "level": 3,
            "name": "Dép quai ngang nữ",
            "slug": "dep-quai-ngang-nu",
            "full_slug": "giay-dep-nu/dep-sandal-nu/dep-quai-ngang-nu",
            "sort_order": 1,
            "is_active": "1",
            "seo_index": "index",
            "seo_cluster_id": "cluster__dep-sandal-nu-quai-ngang",
        },
        {
            "id": "cat3__giay-dep-nu__dep-sandal-nu__dep-tong-nu-xop-mot",
            "parent_id": "cat2__giay-dep-nu__dep-sandal-nu",
            "level": 3,
            "name": "Dép tông nữ xốp một",
            "slug": "dep-tong-nu-xop-mot",
            "full_slug": "giay-dep-nu/dep-sandal-nu/dep-tong-nu-xop-mot",
            "sort_order": 2,
            "is_active": "1",
            "seo_index": "noindex",
            "seo_cluster_id": "cluster__dep-tong-nu-xop-mot",
        },
        {
            "id": "cat3__giay-dep-nu__sneaker-giay-bet-nu__giay-bup-be-nu",
            "parent_id": "cat2__giay-dep-nu__sneaker-giay-bet-nu",
            "level": 3,
            "name": "Giày búp bê nữ",
            "slug": "giay-bup-be-nu",
            "full_slug": "giay-dep-nu/sneaker-giay-bet-nu/giay-bup-be-nu",
            "sort_order": 1,
            "is_active": "1",
            "seo_index": "index",
            "seo_cluster_id": "cluster__sneaker-giay-bet-nu",
        },
    ]
    path_rows = [
        {
            "cat1_id": "cat1__giay-dep-nu",
            "cat1_name": "Giày dép nữ",
            "cat1_slug": "giay-dep-nu",
            "cat2_id": "cat2__giay-dep-nu__dep-sandal-nu",
            "cat2_name": "Dép sandal Nữ",
            "cat2_slug": "dep-sandal-nu",
            "cat3_id": "cat3__giay-dep-nu__dep-sandal-nu__dep-quai-ngang-nu",
            "cat3_name": "Dép quai ngang nữ",
            "cat3_slug": "dep-quai-ngang-nu",
            "full_slug": "giay-dep-nu/dep-sandal-nu/dep-quai-ngang-nu",
            "seo_cluster_id": "cluster__dep-sandal-nu-quai-ngang",
            "seo_cluster_slug": "dep-sandal-nu-quai-ngang",
        },
        {
            "cat1_id": "cat1__giay-dep-nu",
            "cat1_name": "Giày dép nữ",
            "cat1_slug": "giay-dep-nu",
            "cat2_id": "cat2__giay-dep-nu__dep-sandal-nu",
            "cat2_name": "Dép sandal Nữ",
            "cat2_slug": "dep-sandal-nu",
            "cat3_id": "cat3__giay-dep-nu__dep-sandal-nu__dep-tong-nu-xop-mot",
            "cat3_name": "Dép tông nữ xốp một",
            "cat3_slug": "dep-tong-nu-xop-mot",
            "full_slug": "giay-dep-nu/dep-sandal-nu/dep-tong-nu-xop-mot",
            "seo_cluster_id": "cluster__dep-tong-nu-xop-mot",
            "seo_cluster_slug": "dep-tong-nu-xop-mot",
        },
        {
            "cat1_id": "cat1__giay-dep-nu",
            "cat1_name": "Giày dép nữ",
            "cat1_slug": "giay-dep-nu",
            "cat2_id": "cat2__giay-dep-nu__sneaker-giay-bet-nu",
            "cat2_name": "Sneaker & giày bệt",
            "cat2_slug": "sneaker-giay-bet-nu",
            "cat3_id": "cat3__giay-dep-nu__sneaker-giay-bet-nu__giay-bup-be-nu",
            "cat3_name": "Giày búp bê nữ",
            "cat3_slug": "giay-bup-be-nu",
            "full_slug": "giay-dep-nu/sneaker-giay-bet-nu/giay-bup-be-nu",
            "seo_cluster_id": "cluster__sneaker-giay-bet-nu",
            "seo_cluster_slug": "sneaker-giay-bet-nu",
        },
    ]
    df_clusters = pd.DataFrame(cluster_rows)[cluster_cols]
    df_cats = pd.DataFrame(cat_rows)[cat_cols]
    df_paths = pd.DataFrame(path_rows)[list(TAXONOMY_TEMPLATE_CATEGORY_PATH_COLUMNS)]
    df_meta = pd.DataFrame(
        [
            {
                "key": "template_note",
                "value": "Đây là mẫu đủ cột (category_paths có cat1–cat3 + slug cluster). Xóa ví dụ, thêm dòng thật.",
            },
            {"key": "categories_columns", "value": ", ".join(cat_cols)},
            {"key": "category_paths_columns", "value": ", ".join(TAXONOMY_TEMPLATE_CATEGORY_PATH_COLUMNS)},
            {"key": "seo_clusters_columns", "value": ", ".join(cluster_cols)},
            {"key": "external_id", "value": "Cột id trong categories/seo_clusters là external_id — giữ khi re-import."},
        ]
    )
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_clusters.to_excel(writer, sheet_name="seo_clusters", index=False)
        df_cats.to_excel(writer, sheet_name="categories", index=False)
        df_paths.to_excel(writer, sheet_name="category_paths", index=False)
        df_meta.to_excel(writer, sheet_name="meta", index=False)
    return buf.getvalue()


def write_taxonomy_schema_template_to_disk(path: Optional[Path] = None) -> Path:
    """Ghi file .xlsx mẫu schema (đủ cột) — dùng script regenerate; mặc định `assets/taxonomy_import_template.xlsx`."""
    target = path or _taxonomy_bundled_schema_template_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_standard_taxonomy_template_bytes())
    return target


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
    blank_template: bool = Query(
        False,
        description="true: bỏ qua temp_uploads/taxonomy_import.xlsx — chỉ trả mẫu đủ cột (assets hoặc sinh trong code)",
    ),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    """Mặc định: taxonomy đầy đủ trong temp_uploads → assets mẫu cột → sinh trong code. blank_template=1: chỉ (assets → sinh)."""
    paths_primary = ()
    if not blank_template:
        paths_primary = (_taxonomy_sample_disk_path(),)
    for disk in (*paths_primary, _taxonomy_bundled_schema_template_path()):
        if disk.is_file():
            try:
                return FileResponse(
                    str(disk),
                    media_type=_XLSX_MEDIA,
                    filename="taxonomy_import.xlsx",
                )
            except OSError as exc:
                logger.warning("Không đọc được taxonomy sample tại %s: %s — thử nguồn khác.", disk, exc)
    body = _standard_taxonomy_template_bytes()
    return Response(
        content=body,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": _ATTACHMENT_TAXONOMY},
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
