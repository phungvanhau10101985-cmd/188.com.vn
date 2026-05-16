from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.product_import_draft import ProductImportDraft


def create_draft(
    db: Session,
    *,
    job_id: str,
    source_url: str,
    source_offer_id: Optional[str] = None,
    created_by: Optional[int] = None,
    source: str = "1688",
    excel_overlays: Optional[Dict[str, Any]] = None,
) -> ProductImportDraft:
    draft = ProductImportDraft(
        job_id=job_id,
        source=source or "1688",
        source_url=source_url,
        source_offer_id=source_offer_id,
        status="queued",
        phase="queued",
        message="Đã nhận link import, đang vào hàng đợi...",
        percent=0,
        created_by=created_by,
        excel_overlays=excel_overlays,
        errors=[],
        warnings=[],
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def get_by_job_id(db: Session, job_id: str) -> Optional[ProductImportDraft]:
    return db.query(ProductImportDraft).filter(ProductImportDraft.job_id == job_id).first()


def get_by_id(db: Session, draft_id: int) -> Optional[ProductImportDraft]:
    return db.query(ProductImportDraft).filter(ProductImportDraft.id == draft_id).first()


def get_by_ids_map(db: Session, draft_ids: List[int]) -> Dict[int, ProductImportDraft]:
    """Một truy vấn SQL IN — tra cứu theo id (không giữ thứ tự input)."""
    if not draft_ids:
        return {}
    rows = db.query(ProductImportDraft).filter(ProductImportDraft.id.in_(draft_ids)).all()
    return {r.id: r for r in rows}


def list_drafts(
    db: Session,
    *,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[ProductImportDraft], int]:
    """Trả danh sách drafts + tổng (filter status nếu có)."""
    q = db.query(ProductImportDraft)
    if status:
        q = q.filter(ProductImportDraft.status == status)
    total = q.count()
    rows = (
        q.order_by(ProductImportDraft.created_at.desc())
        .offset(max(0, offset))
        .limit(min(500, max(1, limit)))
        .all()
    )
    return rows, total


def update_draft(db: Session, draft: ProductImportDraft, **kwargs: Any) -> ProductImportDraft:
    for key, value in kwargs.items():
        if hasattr(draft, key):
            setattr(draft, key, value)
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def mark_running(db: Session, draft: ProductImportDraft, phase: str, message: str, percent: int) -> ProductImportDraft:
    return update_draft(
        db,
        draft,
        status="running",
        phase=phase,
        message=message,
        percent=max(0, min(99, int(percent))),
    )


def mark_done(
    db: Session,
    draft: ProductImportDraft,
    *,
    raw_payload: Dict[str, Any],
    product_data: Dict[str, Any],
    warnings: Optional[List[str]] = None,
    success_message: Optional[str] = None,
) -> ProductImportDraft:
    return update_draft(
        db,
        draft,
        status="done",
        phase="done",
        message=success_message or "Đã tạo bản nháp từ link nguồn.",
        percent=100,
        raw_payload=raw_payload,
        product_data=product_data,
        warnings=warnings or [],
        finished_at=datetime.now(),
    )


def mark_error(
    db: Session,
    draft: ProductImportDraft,
    *,
    message: str,
    errors: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
) -> ProductImportDraft:
    return update_draft(
        db,
        draft,
        status="error",
        phase="error",
        message=message,
        percent=None,
        errors=errors or [message],
        warnings=warnings or [],
        finished_at=datetime.now(),
    )


def delete_draft_by_id(db: Session, draft_id: int) -> bool:
    """Xóa bản nháp theo id. Trả False nếu không tìm thấy."""
    row = db.query(ProductImportDraft).filter(ProductImportDraft.id == draft_id).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True

