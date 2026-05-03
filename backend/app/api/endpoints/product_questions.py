# backend/app/api/endpoints/product_questions.py - Câu hỏi Câu trả lời sản phẩm
import io
import random
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import tempfile
import os

from app.db.session import get_db
from app import crud
from app.models.admin import AdminUser
from app.models.user import User
from app.schemas.product_question import (
    ProductQuestionCreate,
    ProductQuestionUpdate,
    ProductQuestionResponse,
    ProductQuestionListResponse,
    ProductQuestionAskCreate,
    ProductQuestionReplyCreate,
    UsefulToggleResponse,
)
from app.core.admin_permissions import admin_allowed_operation
from app.core.security import get_current_user, get_current_user_optional, require_module_permission

router = APIRouter()


# ========== PUBLIC: cho trang chi tiết sản phẩm ==========
@router.get("/for-product", response_model=List[ProductQuestionResponse])
def get_questions_for_product(
    product_id: int = Query(..., description="ID sản phẩm (database id)"),
    limit: int = Query(100, le=200),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Lấy câu hỏi hiển thị trên trang chi tiết sản phẩm.
    Nếu có đăng nhập thì mỗi câu hỏi có thêm user_has_voted (đã bấm hữu ích chưa).
    """
    product = crud.product.get_product(db, product_id=product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Sản phẩm không tồn tại")
    group_question = getattr(product, "group_question", 0) or 0
    items = crud.product_question.get_questions_for_product(
        db, product_db_id=product_id, group_question=group_question, limit=limit
    )
    question_ids = [q.id for q in items]
    voted_ids = (
        crud.product_question.get_user_voted_question_ids(db, current_user.id, question_ids)
        if current_user else set()
    )
    now = datetime.now(timezone.utc)
    result = []
    for q in items:
        update = {"user_has_voted": q.id in voted_ids}
        if getattr(q, "is_imported", False):
            days_ago = random.randint(1, 20)
            update["display_created_at"] = now - timedelta(days=days_ago)
        result.append(ProductQuestionResponse.model_validate(q).model_copy(update=update))
    return result


@router.post("/ask", response_model=ProductQuestionResponse)
def ask_question(
    data: ProductQuestionAskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Khách đăng nhập đặt câu hỏi cho sản phẩm (lưu theo product_id)."""
    product = crud.product.get_product(db, product_id=data.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Sản phẩm không tồn tại")
    user_name = getattr(current_user, "full_name", None) or getattr(current_user, "phone", None) or "Khách"
    return crud.product_question.create_customer_question(
        db, product_id=data.product_id, content=data.content.strip(), user_name=user_name or "Khách"
    )


@router.post("/useful/{question_id}/toggle", response_model=UsefulToggleResponse)
def toggle_useful(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bấm/bỏ bấm nút Hữu ích. Bấm lần 1: tăng 1; bấm lại: giảm 1."""
    result = crud.product_question.toggle_useful_vote(db, question_id=question_id, user_id=current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Câu hỏi không tồn tại")
    q, user_has_voted = result
    return UsefulToggleResponse(useful=q.useful or 0, user_has_voted=user_has_voted)


@router.post("/reply/{question_id}", response_model=ProductQuestionResponse)
def reply_to_question(
    question_id: int,
    data: ProductQuestionReplyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Người dùng đã mua hàng trả lời câu hỏi (tối đa 2 người trả lời)."""
    q = crud.product_question.get_question(db, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Câu hỏi không tồn tại")
    if q.reply_count >= 2:
        raise HTTPException(status_code=400, detail="Câu hỏi đã đủ 2 người trả lời, không thể trả lời thêm")
    if not q.product_id:
        raise HTTPException(
            status_code=403,
            detail="Chỉ câu hỏi gắn sản phẩm mới cho phép người mua trả lời",
        )
    if not crud.order.has_user_purchased_product(db, current_user.id, q.product_id):
        raise HTTPException(
            status_code=403,
            detail="Chỉ người đã mua sản phẩm này mới được trả lời câu hỏi",
        )
    user_name = getattr(current_user, "full_name", None) or getattr(current_user, "phone", None) or "Người mua"
    updated = crud.product_question.add_user_reply(
        db, question_id=question_id, user_id=current_user.id, user_name=user_name, content=data.content.strip()
    )
    if not updated:
        raise HTTPException(status_code=400, detail="Không thể thêm trả lời")
    return updated


# ========== ADMIN ==========
@router.get("/admin/list", response_model=ProductQuestionListResponse)
def admin_list_questions(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    group: Optional[int] = Query(None, description="Lọc theo nhóm câu hỏi"),
    product_id: Optional[int] = Query(None, description="Lọc theo ID sản phẩm"),
    search_group: Optional[str] = Query(None, description="Tìm theo nhóm câu hỏi"),
    sort_by: str = Query("id", description="Sắp xếp theo"),
    sort_desc: bool = Query(True, description="Giảm dần"),
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(require_module_permission("product_questions")),
):
    """Danh sách tất cả câu hỏi (admin)."""
    from app.models.product import Product

    items_orm = crud.product_question.get_questions(
        db,
        group=group,
        product_id=product_id,
        skip=skip,
        limit=limit,
        search_group=search_group,
        sort_by=sort_by,
        sort_desc=sort_desc,
        active_only=False,
    )
    total = crud.product_question.get_questions_count(
        db, group=group, product_id=product_id, search_group=search_group, active_only=False
    )
    # Bổ sung product_slug cho câu hỏi có product_id (xem câu hỏi trên trang sản phẩm)
    product_ids = [q.product_id for q in items_orm if q.product_id]
    slug_map = {}
    if product_ids:
        for p in db.query(Product).filter(Product.id.in_(product_ids)).all():
            slug_map[p.id] = getattr(p, "slug", None) or ""
    items = [
        ProductQuestionResponse.model_validate(q).model_copy(update={"product_slug": slug_map.get(q.product_id)})
        for q in items_orm
    ]
    return ProductQuestionListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/admin/{question_id}", response_model=ProductQuestionResponse)
def admin_get_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(require_module_permission("product_questions")),
):
    q = crud.product_question.get_question(db, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Câu hỏi không tồn tại")
    return q


@router.post("/admin/", response_model=ProductQuestionResponse)
def admin_create_question(
    data: ProductQuestionCreate,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(require_module_permission("product_questions")),
):
    return crud.product_question.create_question(db, data)


@router.put("/admin/{question_id}", response_model=ProductQuestionResponse)
def admin_update_question(
    question_id: int,
    data: ProductQuestionUpdate,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(require_module_permission("product_questions")),
):
    obj = crud.product_question.update_question(db, question_id, data)
    if not obj:
        raise HTTPException(status_code=404, detail="Câu hỏi không tồn tại")
    return obj


@router.delete("/admin/{question_id}")
def admin_delete_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(require_module_permission("product_questions")),
):
    if not admin_allowed_operation(current_admin, db, "product_questions", "delete"):
        raise HTTPException(status_code=403, detail="Không được phép xóa câu hỏi với quyền hiện tại.")
    ok = crud.product_question.delete_question(db, question_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Câu hỏi không tồn tại")
    return {"message": "Đã xóa"}


# Excel columns: user_name, content, group, useful, reply_admin_name, reply_admin_content,
# reply_user_one_name, reply_user_one_conte, reply_user_two_name, reply_user_two_conte
EXCEL_COLUMN_MAP = {
    "user_name": "user_name",
    "Tên người hỏi": "user_name",
    "content": "content",
    "Nội dung": "content",
    "group": "group",
    "Nhóm": "group",
    "useful": "useful",
    "Hữu ích": "useful",
    "reply_admin_name": "reply_admin_name",
    "Tên admin trả lời": "reply_admin_name",
    "reply_admin_content": "reply_admin_content",
    "Nội dung admin trả lời": "reply_admin_content",
    "reply_user_one_name": "reply_user_one_name",
    "Tên user 1 trả lời": "reply_user_one_name",
    "reply_user_one_conte": "reply_user_one_content",
    "reply_user_one_content": "reply_user_one_content",
    "Nội dung user 1 trả lời": "reply_user_one_content",
    "reply_user_two_name": "reply_user_two_name",
    "Tên user 2 trả lời": "reply_user_two_name",
    "reply_user_two_conte": "reply_user_two_content",
    "reply_user_two_content": "reply_user_two_content",
    "Nội dung user 2 trả lời": "reply_user_two_content",
    "reply_count": "reply_count",
    "Số câu trả lời (0=cho trả lời, 2=khóa)": "reply_count",
    "Số câu trả lời": "reply_count",
}


# Cột mẫu cho file Excel (tiếng Việt)
SAMPLE_EXCEL_COLUMNS = [
    "Tên người hỏi",
    "Nội dung",
    "Nhóm",
    "Hữu ích",
    "Tên admin trả lời",
    "Nội dung admin trả lời",
    "Thời gian admin trả lời",
    "ID user one trả lời",
    "Tên user 1 trả lời",
    "Nội dung user 1 trả lời",
    "Thời gian user 1 trả lời",
    "ID user two trả lời",
    "Tên user 2 trả lời",
    "Nội dung user 2 trả lời",
    "Thời gian user 2 trả lời",
    "Số câu trả lời (0=cho trả lời, 2=khóa)",
]


@router.get("/admin/export/sample")
def admin_download_sample_excel(
    current_admin: AdminUser = Depends(require_module_permission("product_questions")),
):
    """Tải file Excel mẫu để import câu hỏi."""
    df = pd.DataFrame(
        [
            {
                "Tên người hỏi": "Nguyễn Văn A",
                "Nội dung": "Sản phẩm này còn hàng không?",
                "Nhóm": 0,
                "Hữu ích": 0,
                "Tên admin trả lời": "",
                "Nội dung admin trả lời": "",
                "Thời gian admin trả lời": "",
                "ID user one trả lời": "",
                "Tên user 1 trả lời": "",
                "Nội dung user 1 trả lời": "",
                "Thời gian user 1 trả lời": "",
                "ID user two trả lời": "",
                "Tên user 2 trả lời": "",
                "Nội dung user 2 trả lời": "",
                "Thời gian user 2 trả lời": "",
                "Số câu trả lời (0=cho trả lời, 2=khóa)": 0,
            }
        ],
        columns=SAMPLE_EXCEL_COLUMNS,
    )
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=cau_hoi_san_pham_mau.xlsx"},
    )


@router.post("/admin/import/excel")
async def admin_import_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(require_module_permission("product_questions")),
):
    """
    Import câu hỏi từ Excel.
    Cấu trúc: user_name, content, group, useful, reply_admin_name, reply_admin_content,
    reply_user_one_name, reply_user_one_conte, reply_user_two_name, reply_user_two_conte
    """
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file Excel (.xlsx, .xls)")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(await file.read())
            temp_path = tmp.name
        df = pd.read_excel(temp_path)
        created = 0
        for _, row in df.iterrows():
            raw = row.to_dict()
            data = {}
            for col_name, value in raw.items():
                if pd.isna(value):
                    continue
                col_str = str(col_name).strip()
                if col_str in EXCEL_COLUMN_MAP:
                    key = EXCEL_COLUMN_MAP[col_str]
                    if key in ("group", "useful", "reply_count"):
                        try:
                            data[key] = int(float(value))
                        except (ValueError, TypeError):
                            data[key] = 0 if key != "reply_count" else 0
                    else:
                        data[key] = str(value).strip() if value is not None else ""
            user_name = data.get("user_name", "")
            content = data.get("content", "")
            if not content:
                continue
            # Import Excel: thời gian ngẫu nhiên 1–20 ngày trước (hiển thị thực tế tính khi API trả về)
            now = datetime.now(timezone.utc)
            days_ago = random.randint(1, 20)
            created_at_import = now - timedelta(days=days_ago)
            reply_count_val = data.get("reply_count", 0)
            if not isinstance(reply_count_val, int):
                try:
                    reply_count_val = int(float(reply_count_val))
                except (ValueError, TypeError):
                    reply_count_val = 0
            create_data = ProductQuestionCreate(
                user_name=user_name or "Import",
                content=content,
                group=data.get("group", 0),
                product_id=None,
                useful=data.get("useful", 0),
                reply_admin_name=data.get("reply_admin_name", ""),
                reply_admin_content=data.get("reply_admin_content", ""),
                reply_user_one_name=data.get("reply_user_one_name", ""),
                reply_user_one_content=data.get("reply_user_one_content", ""),
                reply_user_two_name=data.get("reply_user_two_name", ""),
                reply_user_two_content=data.get("reply_user_two_content", ""),
                reply_count=min(2, max(0, reply_count_val)),
                is_active=True,
                created_at=created_at_import,
                is_imported=True,
            )
            crud.product_question.create_question(db, create_data)
            created += 1
        return {"message": f"Đã import {created} câu hỏi", "created": created}
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass
