"""Báo cáo admin: sản phẩm nghi hàng giả."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.security import require_module_permission
from app.db.session import get_db
from app.models.admin import AdminUser
from app.services.counterfeit_report import (
    build_counterfeit_export_xlsx,
    counterfeit_list_item,
    counterfeit_products_query,
)

router = APIRouter()


@router.get("/admin/counterfeit-report")
def list_counterfeit_report(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    q: str = Query(""),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    query = counterfeit_products_query(db, q)
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [counterfeit_list_item(row) for row in rows],
    }


@router.get("/admin/counterfeit-report/export")
def export_counterfeit_report(
    q: str = Query(""),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    products = counterfeit_products_query(db, q).all()
    payload = build_counterfeit_export_xlsx(products)
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="bao-cao-hang-gia.xlsx"'},
    )
