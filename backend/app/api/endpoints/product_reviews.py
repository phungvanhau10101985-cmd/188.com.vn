# backend/app/api/endpoints/product_reviews.py - Đánh giá sản phẩm (chỉ admin trả lời)
import io
import json
import os
import random
import tempfile
from datetime import datetime, timezone, timedelta

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app import crud
from app.models.admin import AdminUser
from app.models.user import User
from app.schemas.product_review import (
    ProductReviewCreate,
    ProductReviewUpdate,
    ProductReviewResponse,
    ProductReviewSubmit,
    UsefulToggleResponse,
)
from app.core.security import get_current_admin, get_current_user, get_current_user_optional

router = APIRouter()


@router.get("/user-reviewed-ids")
def get_user_reviewed_product_ids(
    product_ids: str = Query(..., description="Danh sách product_id cách nhau bằng dấu phẩy"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lấy các product_id mà user đã đánh giá."""
    ids = [int(x.strip()) for x in product_ids.split(",") if x.strip().isdigit()]
    reviewed = crud.product_review.get_user_reviewed_product_ids(db, current_user.id, ids)
    return {"product_ids": list(reviewed)}


@router.get("/can-review")
def can_review_product(
    product_id: int = Query(..., description="ID sản phẩm"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Kiểm tra user đăng nhập có được phép đánh giá sản phẩm (đã mua và nhận hàng)."""
    if not current_user:
        return {"can_review": False, "reason": "Chưa đăng nhập"}
    product = crud.product.get_product(db, product_id=product_id)
    if not product:
        return {"can_review": False, "reason": "Sản phẩm không tồn tại"}
    ok = crud.order.has_user_purchased_product_for_review(db, current_user.id, product_id)
    return {"can_review": ok, "reason": None if ok else "Bạn chưa mua hoặc chưa nhận hàng sản phẩm này"}


@router.get("/for-product", response_model=List[ProductReviewResponse])
def get_reviews_for_product(
    product_id: int = Query(..., description="ID sản phẩm"),
    limit: int = Query(100, le=200),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Lấy đánh giá cho trang sản phẩm. Đánh giá của user đăng nhập xếp lên đầu, còn lại theo useful DESC."""
    product = crud.product.get_product(db, product_id=product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Sản phẩm không tồn tại")
    group_rating = getattr(product, "group_rating", 0) or 0
    items = crud.product_review.get_reviews_for_product(
        db, product_db_id=product_id, group_rating=group_rating, limit=limit
    )
    review_ids = [r.id for r in items]
    voted_ids = (
        crud.product_review.get_user_voted_review_ids(db, current_user.id, review_ids)
        if current_user else set()
    )
    now = datetime.now(timezone.utc)
    result = []
    for r in items:
        is_mine = bool(current_user and getattr(r, "user_id", None) == current_user.id)
        update = {"user_has_voted": r.id in voted_ids, "is_current_user": is_mine}
        if getattr(r, "is_imported", False):
            days_ago = random.randint(1, 20)
            update["display_created_at"] = now - timedelta(days=days_ago)
        result.append(ProductReviewResponse.model_validate(r).model_copy(update=update))
    # Đánh giá của khách đang xem (is_current_user) lên trên nhất, còn lại giữ thứ tự useful/created
    result.sort(key=lambda x: (not (x.is_current_user or False), -(x.useful or 0)))
    return result


@router.post("/submit", response_model=ProductReviewResponse)
def submit_review(
    data: ProductReviewSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Khách hàng đăng nhập gửi đánh giá thực tế. Chỉ khách đã mua và nhận hàng mới được đánh giá."""
    product = crud.product.get_product(db, product_id=data.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Sản phẩm không tồn tại")
    if not crud.order.has_user_purchased_product_for_review(db, current_user.id, data.product_id):
        raise HTTPException(
            status_code=403,
            detail="Chỉ khách hàng đã mua và nhận hàng mới được đánh giá sản phẩm này.",
        )
    user_name = getattr(current_user, "full_name", None) or getattr(current_user, "phone", None) or "Khách"
    review = crud.product_review.create_customer_review(
        db,
        product_id=data.product_id,
        user_name=user_name,
        star=data.star,
        content=data.content.strip(),
        title=data.title.strip() if data.title else "",
        images=data.images or [],
        user_id=current_user.id,
    )
    # Khi khách đánh giá 1 sản phẩm trong đơn → cập nhật đơn sang "đã đánh giá"
    crud.order.mark_order_completed_if_reviewed(db, current_user.id, data.product_id)
    return review


@router.post("/useful/{review_id}/toggle", response_model=UsefulToggleResponse)
def toggle_useful(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bấm/bỏ bấm Hữu ích."""
    res = crud.product_review.toggle_useful_vote(db, review_id=review_id, user_id=current_user.id)
    if not res:
        raise HTTPException(status_code=404, detail="Đánh giá không tồn tại")
    r, user_has_voted = res
    return UsefulToggleResponse(useful=r.useful or 0, user_has_voted=user_has_voted)


# ========== ADMIN ==========
@router.get("/admin/list")
def admin_list_reviews(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
):
    """
    Danh sách đánh giá (admin).
    - Khách đánh giá (is_imported=False): hiển thị trên sản phẩm đã mua (product_id).
    - Đánh giá import (is_imported=True): hiển thị trên sản phẩm có group_rating = group.
    """
    from app.models.product_review import ProductReview
    from app.models.product import Product

    q = db.query(ProductReview).filter().order_by(ProductReview.id.desc())
    total = q.count()
    items = q.offset(skip).limit(limit).all()
    product_ids = [r.product_id for r in items if r.product_id]
    slug_map = {}
    if product_ids:
        for p in db.query(Product).filter(Product.id.in_(product_ids)).all():
            slug_map[p.id] = getattr(p, "slug", None) or ""
    group_ratings = list({r.group or 0 for r in items if not r.product_id})
    group_slug_map = {}
    if group_ratings:
        for p in db.query(Product).filter(Product.group_rating.in_(group_ratings), Product.slug.isnot(None)).limit(500).all():
            g = getattr(p, "group_rating", 0) or 0
            if g not in group_slug_map and p.slug:
                group_slug_map[g] = p.slug
    result = []
    for r in items:
        slug = slug_map.get(r.product_id) if r.product_id else group_slug_map.get(r.group or 0)
        result.append(
            ProductReviewResponse.model_validate(r).model_copy(update={"product_slug": slug})
        )
    return {"items": result, "total": total, "skip": skip, "limit": limit}


@router.post("/admin/", response_model=ProductReviewResponse)
def admin_create_review(
    data: ProductReviewCreate,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
):
    return crud.product_review.create_review(db, data)


@router.put("/admin/{review_id}", response_model=ProductReviewResponse)
def admin_update_review(
    review_id: int,
    data: ProductReviewUpdate,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
):
    obj = crud.product_review.update_review(db, review_id, data)
    if not obj:
        raise HTTPException(status_code=404, detail="Đánh giá không tồn tại")
    return obj


@router.delete("/admin/{review_id}")
def admin_delete_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
):
    ok = crud.product_review.delete_review(db, review_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Đánh giá không tồn tại")
    return {"message": "Đã xóa"}


# ========== IMPORT / EXPORT ==========
REVIEW_EXCEL_COLUMNS = [
    "Tên người",
    "Số sao",
    "Tiêu đề",
    "Nội dung",
    "Tên người trả lời",
    "Nội dung trả lời",
    "Số đánh giá hữu ích",
    "Nhóm đánh giá",
    "Ảnh đánh giá",
]
REVIEW_EXCEL_COLUMN_MAP = {
    "user_name": "user_name",
    "Tên người": "user_name",
    "star": "star",
    "Số sao": "star",
    "title": "title",
    "Tiêu đề": "title",
    "content": "content",
    "Nội dung": "content",
    "reply_name": "reply_name",
    "Tên người trả lời": "reply_name",
    "reply_content": "reply_content",
    "Nội dung trả lời": "reply_content",
    "useful": "useful",
    "Số đánh giá hữu ích": "useful",
    "Số đánh gi": "useful",
    "group": "group",
    "Nhóm đánh giá": "group",
    "img_fake": "images",
    "Ảnh đánh giá": "images",
}


@router.get("/admin/export/sample")
def admin_download_sample_excel(
    current_admin: AdminUser = Depends(get_current_admin),
):
    """Tải file Excel mẫu để import đánh giá sản phẩm."""
    df = pd.DataFrame(
        [
            {
                "Tên người": "Anh An",
                "Số sao": 4,
                "Tiêu đề": "Hài lòng",
                "Nội dung": "Tôi đánh giá Mr.Admin",
                "Tên người trả lời": "Mr.Admin",
                "Nội dung trả lời": "Rất cảm ơn bạn đã đánh giá",
                "Số đánh giá hữu ích": 50,
                "Nhóm đánh giá": 1,
                "Ảnh đánh giá": '["https://example.com/img1.jpg"]',
            }
        ],
        columns=REVIEW_EXCEL_COLUMNS,
    )
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=danh_gia_san_pham_mau.xlsx"},
    )


@router.post("/admin/import/excel")
async def admin_import_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
):
    """Import đánh giá sản phẩm từ Excel. Cột: user_name, star, title, content, reply_name, reply_content, useful, group, img_fake (ảnh JSON)."""
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file Excel (.xlsx, .xls)")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(await file.read())
            temp_path = tmp.name
        df = pd.read_excel(temp_path)
        created = 0
        now = datetime.now(timezone.utc)
        for _, row in df.iterrows():
            raw = row.to_dict()
            data = {}
            for col_name, value in raw.items():
                if pd.isna(value):
                    continue
                col_str = str(col_name).strip()
                if col_str in REVIEW_EXCEL_COLUMN_MAP:
                    key = REVIEW_EXCEL_COLUMN_MAP[col_str]
                    if key in ("star", "useful", "group"):
                        try:
                            data[key] = int(float(value))
                        except (ValueError, TypeError):
                            data[key] = 5 if key == "star" else 0
                    elif key == "images":
                        img_val = str(value).strip() if value is not None else "[]"
                        try:
                            parsed = json.loads(img_val) if img_val else []
                            data[key] = [str(u).strip() for u in parsed] if isinstance(parsed, list) else []
                            for i, u in enumerate(data[key]):
                                if u.startswith("//"):
                                    data[key][i] = "https:" + u
                        except (json.JSONDecodeError, TypeError):
                            data[key] = []
                    else:
                        data[key] = str(value).strip() if value is not None else ""
            content = data.get("content", "")
            if not content:
                continue
            star_val = max(1, min(5, data.get("star", 5)))
            group_val = max(0, data.get("group", 0))
            useful_val = max(0, data.get("useful", 0))
            days_ago = random.randint(1, 20)
            created_at_import = now - timedelta(days=days_ago)
            create_data = ProductReviewCreate(
                user_name=data.get("user_name", "Import") or "Import",
                star=star_val,
                title=data.get("title", ""),
                content=content,
                group=group_val,
                product_id=None,
                useful=useful_val,
                reply_name=data.get("reply_name", ""),
                reply_content=data.get("reply_content", ""),
                images=data.get("images", []),
                is_active=True,
                created_at=created_at_import,
                is_imported=True,
            )
            crud.product_review.create_review(db, create_data)
            created += 1
        return {"message": f"Đã import {created} đánh giá", "created": created}
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass
