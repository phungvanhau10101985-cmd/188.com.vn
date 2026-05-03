# backend/app/api/endpoints/taxonomy_admin.py
"""
Admin endpoint quản lý taxonomy (cây danh mục + SEO cluster) qua file Excel 4 sheet.

- POST /api/v1/taxonomy/import : upload taxonomy_import.xlsx → seed categories + seo_clusters.
- GET  /api/v1/taxonomy/sample : ưu tiên `temp_uploads/taxonomy_import.xlsx` (dữ liệu đầy đủ),
  sau đó `assets/taxonomy_import_template.xlsx` (mẫu đủ cột + vài dòng minh họa),
  cuối cùng sinh workbook trong code (cùng schema).

Yêu cầu Bearer admin (Depends(require_module_permission("taxonomy"))).

Import là **upsert / hợp nhất** theo cột `id` (chuỗi, lưu DB là `external_id`):
- **Đã có** `id` đó → **cập nhật** slug, tên, full_slug, cha, cluster, seo_index, v.v. theo file;
- **Chưa có** → **thêm mới**.
- Có thể chạy lại nhiều lần an toàn; không xóa dòng chỉ vì thiếu trong file.
"""
from __future__ import annotations

import io
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models
from app.core.security import require_module_permission
from app.db.session import get_db
from app.models.category import Category
from app.models.seo_cluster import SeoCluster
from app.utils.slug import create_slug as slugify_text
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


def _upsert_clusters(db: Session, df: pd.DataFrame) -> Tuple[Dict[str, int], List[str], Dict[str, int]]:
    """Upsert SeoCluster theo external_id. Trả map external_id → db_id, lỗi, và đếm inserted/updated (chỉ dòng xử lý được trong sheet)."""
    errors: List[str] = []
    ext_to_id: Dict[str, int] = {}
    counts = {"inserted": 0, "updated": 0}

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
            counts["inserted"] += 1
        else:
            counts["updated"] += 1
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
    return ext_to_id, errors, counts


def _insert_categories(
    db: Session, df: pd.DataFrame, cluster_ext_to_id: Dict[str, int]
) -> Tuple[Dict[str, int], Dict[str, Dict[str, int]], List[str]]:
    """
    Insert/upsert Category theo external_id, sắp xếp theo level 1 → 2 → 3 để parent_id sẵn sàng.
    Trả: (cat_ext_to_id, {"inserted": {1:..,2:..,3:..}, "updated": {..}}, errors).
    """
    errors: List[str] = []

    # Chuẩn hoá level + sort
    df = df.copy()
    df["__level"] = df["level"].apply(_safe_int)
    df = df.sort_values(by=["__level"]).reset_index(drop=True)

    # Map ext_id → db_id (load các cat đã có nếu có)
    existing = {c.external_id: c for c in db.query(Category).all() if c.external_id}
    cat_ext_to_id: Dict[str, int] = {ext: c.id for ext, c in existing.items()}
    inserted: Dict[int, int] = {1: 0, 2: 0, 3: 0}
    updated: Dict[int, int] = {1: 0, 2: 0, 3: 0}

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
            inserted[level] = inserted.get(level, 0) + 1
        else:
            updated[level] = updated.get(level, 0) + 1
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

    db.commit()
    return cat_ext_to_id, {"inserted": inserted, "updated": updated}, errors


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


def execute_taxonomy_sheets(db: Session, sheets: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """Chạy cùng pipeline với upload Excel (4 sheet)."""
    started = time.time()
    df_clusters = sheets["seo_clusters"]
    df_cats = sheets["categories"]
    df_paths = sheets["category_paths"]
    df_meta = sheets["meta"]

    cluster_ext_to_id, e_clusters, cluster_counts = _upsert_clusters(db, df_clusters)
    cat_ext_to_id, cat_counts, e_cats = _insert_categories(db, df_cats, cluster_ext_to_id)
    e_paths = _validate_paths(df_paths, cat_ext_to_id, cluster_ext_to_id)

    ttl_cache.invalidate_all()

    meta_kv: Dict[str, str] = {}
    if {"key", "value"} <= set(df_meta.columns):
        for _, row in df_meta.iterrows():
            k = str(row.get("key") or "").strip()
            v = str(row.get("value") or "").strip()
            if k:
                meta_kv[k] = v

    ins = cat_counts["inserted"]
    upd = cat_counts["updated"]
    elapsed_ms = int((time.time() - started) * 1000)
    return {
        "ok": True,
        "summary": {
            "categories": {
                "1": {
                    "inserted": int(ins.get(1, 0)),
                    "updated": int(upd.get(1, 0)),
                },
                "2": {
                    "inserted": int(ins.get(2, 0)),
                    "updated": int(upd.get(2, 0)),
                },
                "3": {
                    "inserted": int(ins.get(3, 0)),
                    "updated": int(upd.get(3, 0)),
                },
            },
            "clusters": {
                "inserted": int(cluster_counts["inserted"]),
                "updated": int(cluster_counts["updated"]),
                "in_database_after": len(cluster_ext_to_id),
            },
        },
        "errors": {
            "seo_clusters": e_clusters,
            "categories": e_cats,
            "category_paths": e_paths,
        },
        "meta": meta_kv,
        "elapsed_ms": elapsed_ms,
    }


@router.post("/import")
async def import_taxonomy(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(require_module_permission("taxonomy")),
) -> Dict[str, Any]:
    """
    Upload taxonomy_import.xlsx (4 sheet).

    **Upsert theo cột `id` (external_id):** dòng đã có trong DB → cập nhật theo file;
    dòng chưa có → thêm mới. Có thể import lặp lại; không xóa nhánh chỉ vì không
    nằm trong file.
    """
    name = (file.filename or "").lower()
    if not name.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận file .xlsx hoặc .xls")

    raw = await file.read()
    sheets = _parse_upload(raw)
    return execute_taxonomy_sheets(db, sheets)


class TaxonomyManualUpsertIn(BaseModel):
    """Giống một dòng nhánh đủ 3 cấp + cluster trong file import."""

    cat1_existing_external_id: Optional[str] = Field(None, description="Cấp 1 đã có trong DB (external_id)")
    cat1_name: Optional[str] = None
    cat1_slug: Optional[str] = None

    cat2_existing_external_id: Optional[str] = Field(None, description="Cấp 2 đã có — bắt buộc kèm cấp 1 đã có")
    cat2_name: Optional[str] = None
    cat2_slug: Optional[str] = None

    cat3_name: str
    cat3_slug: Optional[str] = None

    cluster_existing_external_id: Optional[str] = None
    cluster_name: Optional[str] = None
    cluster_slug: Optional[str] = None
    cluster_index_policy: Literal["index", "noindex"] = "index"

    cat3_seo_index: Literal["index", "noindex"] = "noindex"
    cat3_sort_order: int = 0
    is_active: bool = True


def _norm_slug(user_slug: Optional[str], name: str) -> str:
    base = (user_slug or "").strip()
    return slugify_text(base if base else (name or "").strip())


def _category_row(
    ext_id: str,
    parent_ext: str,
    level: int,
    name: str,
    slug: str,
    full_slug: str,
    *,
    sort_order: int,
    is_active: bool,
    seo_index_lit: str,
    cluster_ext: str,
) -> Dict[str, Any]:
    return {
        "id": ext_id,
        "parent_id": parent_ext,
        "level": level,
        "name": name,
        "slug": slug,
        "full_slug": full_slug,
        "sort_order": sort_order,
        "is_active": "1" if is_active else "0",
        "seo_index": seo_index_lit,
        "seo_cluster_id": cluster_ext,
    }


def _build_manual_taxonomy_sheets(db: Session, body: TaxonomyManualUpsertIn) -> Dict[str, pd.DataFrame]:
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

    cat1_rows: List[Dict[str, Any]] = []
    cat2_rows: List[Dict[str, Any]] = []

    if body.cat1_existing_external_id:
        c1e = body.cat1_existing_external_id.strip()
        c1 = db.query(Category).filter(Category.external_id == c1e).first()
        if not c1 or c1.level != 1:
            raise HTTPException(status_code=400, detail="Cấp 1 (external_id) không tồn tại hoặc không phải level 1")
        cat1_ext = (c1.external_id or "").strip()
        if not cat1_ext:
            raise HTTPException(
                status_code=400,
                detail="Danh mục cấp 1 đã chọn chưa có external_id — cập nhật qua import Excel hoặc DB trước.",
            )
        cat1_name = c1.name
        cat1_slug = c1.slug
    else:
        if not (body.cat1_name or "").strip():
            raise HTTPException(status_code=400, detail="Thiếu tên cấp 1 hoặc chọn cấp 1 có sẵn")
        cat1_name = body.cat1_name.strip()
        cat1_slug = _norm_slug(body.cat1_slug, cat1_name)
        if not cat1_slug:
            raise HTTPException(status_code=400, detail="Slug cấp 1 không hợp lệ")
        cat1_ext = f"cat1__{cat1_slug}"
        cat1_rows.append(
            _category_row(
                cat1_ext,
                "",
                1,
                cat1_name,
                cat1_slug,
                cat1_slug,
                sort_order=0,
                is_active=body.is_active,
                seo_index_lit="index",
                cluster_ext="",
            )
        )

    if body.cat2_existing_external_id:
        if not body.cat1_existing_external_id:
            raise HTTPException(
                status_code=400,
                detail="Chọn cấp 2 có sẵn thì phải chọn cấp 1 có sẵn (không tạo cấp 1 mới + cấp 2 cũ)",
            )
        c2e = body.cat2_existing_external_id.strip()
        c2 = db.query(Category).filter(Category.external_id == c2e).first()
        if not c2 or c2.level != 2:
            raise HTTPException(status_code=400, detail="Cấp 2 không tồn tại hoặc không phải level 2")
        if c2.parent_id != c1.id:
            raise HTTPException(status_code=400, detail="Cấp 2 không thuộc cấp 1 đã chọn")
        cat2_ext = (c2.external_id or "").strip()
        if not cat2_ext:
            raise HTTPException(
                status_code=400,
                detail="Danh mục cấp 2 đã chọn chưa có external_id — cập nhật qua import Excel hoặc DB trước.",
            )
        cat2_name = c2.name
        cat2_slug = c2.slug
    else:
        if not (body.cat2_name or "").strip():
            raise HTTPException(status_code=400, detail="Thiếu tên cấp 2 hoặc chọn cấp 2 có sẵn")
        cat2_name = body.cat2_name.strip()
        cat2_slug = _norm_slug(body.cat2_slug, cat2_name)
        if not cat2_slug:
            raise HTTPException(status_code=400, detail="Slug cấp 2 không hợp lệ")
        cat2_ext = f"cat2__{cat1_slug}__{cat2_slug}"
        cat2_rows.append(
            _category_row(
                cat2_ext,
                cat1_ext,
                2,
                cat2_name,
                cat2_slug,
                f"{cat1_slug}/{cat2_slug}",
                sort_order=0,
                is_active=body.is_active,
                seo_index_lit="index",
                cluster_ext="",
            )
        )

    c3name = body.cat3_name.strip()
    if not c3name:
        raise HTTPException(status_code=400, detail="Thiếu tên cấp 3")
    cat3_slug = _norm_slug(body.cat3_slug, c3name)
    if not cat3_slug:
        raise HTTPException(status_code=400, detail="Slug cấp 3 không hợp lệ")
    cat3_ext = f"cat3__{cat1_slug}__{cat2_slug}__{cat3_slug}"

    cluster_rows: List[Dict[str, Any]] = []
    if body.cluster_existing_external_id:
        cl_e = body.cluster_existing_external_id.strip()
        cl = db.query(SeoCluster).filter(SeoCluster.external_id == cl_e).first()
        if not cl:
            raise HTTPException(status_code=400, detail="SEO cluster (external_id) không tồn tại")
        cluster_ext = (cl.external_id or "").strip()
        if not cluster_ext:
            raise HTTPException(
                status_code=400,
                detail="Cluster đã chọn chưa có external_id — cập nhật qua import trước.",
            )
        cluster_slug = cl.slug
    else:
        if not (body.cluster_name or "").strip():
            raise HTTPException(status_code=400, detail="Thiếu tên cluster hoặc chọn cluster có sẵn")
        cname = body.cluster_name.strip()
        cluster_slug = _norm_slug(body.cluster_slug, cname)
        if not cluster_slug:
            raise HTTPException(status_code=400, detail="Slug cluster không hợp lệ")
        cluster_ext = f"cluster__{cluster_slug}"
        cluster_rows.append(
            {
                "id": cluster_ext,
                "slug": cluster_slug,
                "name": cname,
                "canonical_path": f"/c/{cluster_slug}",
                "index_policy": body.cluster_index_policy,
                "source": "manual_taxonomy_form",
                "notes": "",
            }
        )

    cat3_row = _category_row(
        cat3_ext,
        cat2_ext,
        3,
        c3name,
        cat3_slug,
        f"{cat1_slug}/{cat2_slug}/{cat3_slug}",
        sort_order=body.cat3_sort_order,
        is_active=body.is_active,
        seo_index_lit=body.cat3_seo_index,
        cluster_ext=cluster_ext,
    )

    all_cat_rows = cat1_rows + cat2_rows + [cat3_row]
    path_row = {
        "cat1_id": cat1_ext,
        "cat1_name": cat1_name,
        "cat1_slug": cat1_slug,
        "cat2_id": cat2_ext,
        "cat2_name": cat2_name,
        "cat2_slug": cat2_slug,
        "cat3_id": cat3_ext,
        "cat3_name": c3name,
        "cat3_slug": cat3_slug,
        "full_slug": f"{cat1_slug}/{cat2_slug}/{cat3_slug}",
        "seo_cluster_id": cluster_ext,
        "seo_cluster_slug": cluster_slug,
    }

    df_cats = pd.DataFrame(all_cat_rows)[cat_cols]
    df_clusters = pd.DataFrame(cluster_rows)[cluster_cols] if cluster_rows else pd.DataFrame(columns=cluster_cols)
    df_paths = pd.DataFrame([path_row])[list(TAXONOMY_TEMPLATE_CATEGORY_PATH_COLUMNS)]
    df_meta = pd.DataFrame([{"key": "manual_form", "value": cat3_ext}])

    return {
        "categories": df_cats,
        "seo_clusters": df_clusters,
        "category_paths": df_paths,
        "meta": df_meta,
    }


@router.get("/form-tree")
def taxonomy_form_tree(
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(require_module_permission("taxonomy")),
) -> Dict[str, Any]:
    """Cây categories kèm external_id — chọn trên form thủ công."""

    def _sort_children(nodes: List[Dict[str, Any]]) -> None:
        nodes.sort(key=lambda n: (int(n.get("sort_order") or 0), str(n.get("name") or ""), int(n.get("db_id") or 0)))
        for n in nodes:
            _sort_children(n.get("children") or [])

    rows = (
        db.query(Category)
        .order_by(Category.level, Category.sort_order, Category.id)
        .all()
    )
    by_id: Dict[int, Dict[str, Any]] = {}
    for c in rows:
        by_id[c.id] = {
            "db_id": c.id,
            "external_id": c.external_id,
            "parent_id": c.parent_id,
            "level": c.level,
            "name": c.name,
            "slug": c.slug,
            "full_slug": c.full_slug,
            "sort_order": c.sort_order,
            "seo_index": c.seo_index,
            "children": [],
        }
    roots: List[Dict[str, Any]] = []
    for node in by_id.values():
        pid = node["parent_id"]
        if pid and pid in by_id:
            by_id[pid]["children"].append(node)
        elif node["level"] == 1:
            roots.append(node)
    _sort_children(roots)
    return {"tree": roots}


@router.get("/clusters-list")
def taxonomy_clusters_list(
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(require_module_permission("taxonomy")),
) -> Dict[str, Any]:
    rows = db.query(SeoCluster).order_by(SeoCluster.slug).all()
    return {
        "clusters": [
            {
                "external_id": r.external_id,
                "slug": r.slug,
                "name": r.name,
                "index_policy": r.index_policy,
            }
            for r in rows
        ]
    }


@router.post("/manual-upsert")
def taxonomy_manual_upsert(
    body: TaxonomyManualUpsertIn,
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(require_module_permission("taxonomy")),
) -> Dict[str, Any]:
    """
    Thêm / cập nhật một nhánh cat1–cat3 + cluster — **cùng upsert** như Excel:
    `id`/`external_id` đã có thì cập nhật, chưa có thì tạo mới.
    """
    sheets = _build_manual_taxonomy_sheets(db, body)
    sheets_out = {
        "seo_clusters": sheets["seo_clusters"],
        "categories": sheets["categories"],
        "category_paths": sheets["category_paths"],
        "meta": sheets["meta"],
    }
    return execute_taxonomy_sheets(db, sheets_out)


# ---------- SAMPLE FILE ----------
@router.get("/sample")
def download_sample_taxonomy_file(
    blank_template: bool = Query(
        False,
        description="true: bỏ qua temp_uploads/taxonomy_import.xlsx — chỉ trả mẫu đủ cột (assets hoặc sinh trong code)",
    ),
    _admin: models.AdminUser = Depends(require_module_permission("taxonomy")),
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
    _admin: models.AdminUser = Depends(require_module_permission("taxonomy")),
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
