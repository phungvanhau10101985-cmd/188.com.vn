"""Kiểm tra chuỗi tên danh mục (cấp 1→2→3) khớp taxonomy và đúng quan hệ cha-con."""

from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.models.category import Category


def validate_taxonomy_chain_by_names(
    db: Session,
    level1_name: str,
    level2_name: str,
    level3_name: str,
    *,
    path_label: str,
) -> None:
    """
    Đảm bảo cả ba tên tồn tại trong bảng `categories`, `is_active=True`,
    và L2.parent_id = L1, L3.parent_id = L2.
    So khớp tên: trim + lower (giống hướng xử lý `category_field_equals_ci` trên Product).
    """
    n1 = (level1_name or "").strip()
    n2 = (level2_name or "").strip()
    n3 = (level3_name or "").strip()
    if not n1 or not n2 or not n3:
        raise HTTPException(status_code=400, detail=f"{path_label}: thiếu tên cấp 1, 2 hoặc 3.")

    ln1, ln2, ln3 = n1.lower(), n2.lower(), n3.lower()

    c1 = (
        db.query(Category)
        .filter(
            Category.level == 1,
            Category.is_active.is_(True),
            sql_func.lower(sql_func.trim(Category.name)) == ln1,
        )
        .first()
    )
    if not c1:
        raise HTTPException(
            status_code=400,
            detail=f"{path_label}: cấp 1 «{n1}» không có trong taxonomy (hoặc đang tắt).",
        )

    c2 = (
        db.query(Category)
        .filter(
            Category.level == 2,
            Category.parent_id == c1.id,
            Category.is_active.is_(True),
            sql_func.lower(sql_func.trim(Category.name)) == ln2,
        )
        .first()
    )
    if not c2:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{path_label}: cấp 2 «{n2}» không thuộc cấp 1 «{n1}» trong taxonomy "
                f"(hoặc không tồn tại / đang tắt)."
            ),
        )

    c3 = (
        db.query(Category)
        .filter(
            Category.level == 3,
            Category.parent_id == c2.id,
            Category.is_active.is_(True),
            sql_func.lower(sql_func.trim(Category.name)) == ln3,
        )
        .first()
    )
    if not c3:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{path_label}: cấp 3 «{n3}» không thuộc cấp 2 «{n2}» trong taxonomy "
                f"(hoặc không tồn tại / đang tắt)."
            ),
        )


def validate_final_mapping_row_paths(db: Session, row: dict, *, row_index: int) -> None:
    """Import JSON một dòng: kiểm tra nguồn (nếu có cấp 3) và đích (nếu có đủ ba cấp)."""
    prefix = f"Dòng import {row_index}"
    fc = row.get("from_category") or ""
    fs = row.get("from_subcategory") or ""
    fss = row.get("from_sub_subcategory") or ""
    if (fss or "").strip():
        try:
            validate_taxonomy_chain_by_names(db, fc, fs, fss, f"{prefix} — nguồn")
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, str) else str(e.detail)
            raise HTTPException(status_code=400, detail=f"{prefix}: {detail}") from e

    tc = row.get("to_category") or ""
    ts = row.get("to_subcategory") or ""
    tss = row.get("to_sub_subcategory") or ""
    if (tc or "").strip() or (ts or "").strip() or (tss or "").strip():
        if not ((tc or "").strip() and (ts or "").strip() and (tss or "").strip()):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{prefix}: đích phải đủ tên cấp 1, 2 và 3 theo taxonomy "
                    f"(hoặc để trống cả ba nếu dòng không hợp lệ — thường không dùng)."
                ),
            )
        try:
            validate_taxonomy_chain_by_names(db, tc, ts, tss, f"{prefix} — đích")
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, str) else str(e.detail)
            raise HTTPException(status_code=400, detail=f"{prefix}: {detail}") from e
