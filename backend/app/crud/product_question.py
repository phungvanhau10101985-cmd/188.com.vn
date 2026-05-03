# backend/app/crud/product_question.py
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import List, Optional
from datetime import datetime, timezone

from app.models.product_question import ProductQuestion, ProductQuestionUsefulVote
from app.models.product import Product
from app.schemas.product_question import ProductQuestionCreate, ProductQuestionUpdate


def get_question(db: Session, question_id: int) -> Optional[ProductQuestion]:
    return db.query(ProductQuestion).filter(ProductQuestion.id == question_id).first()


def get_questions(
    db: Session,
    *,
    group: Optional[int] = None,
    product_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    search_group: Optional[str] = None,
    sort_by: str = "id",
    sort_desc: bool = True,
    active_only: bool = False,
) -> List[ProductQuestion]:
    q = db.query(ProductQuestion)
    if active_only:
        q = q.filter(ProductQuestion.is_active == True)
    if group is not None:
        q = q.filter(ProductQuestion.group == group)
    if product_id is not None:
        q = q.filter(ProductQuestion.product_id == product_id)
    if search_group is not None and search_group.strip():
        try:
            g = int(search_group.strip())
            q = q.filter(ProductQuestion.group == g)
        except ValueError:
            pass
    order_col = getattr(ProductQuestion, sort_by, ProductQuestion.id)
    q = q.order_by(order_col.desc() if sort_desc else order_col.asc())
    return q.offset(skip).limit(limit).all()


def get_questions_count(
    db: Session,
    *,
    group: Optional[int] = None,
    product_id: Optional[int] = None,
    search_group: Optional[str] = None,
    active_only: bool = False,
) -> int:
    q = db.query(ProductQuestion)
    if active_only:
        q = q.filter(ProductQuestion.is_active == True)
    if group is not None:
        q = q.filter(ProductQuestion.group == group)
    if product_id is not None:
        q = q.filter(ProductQuestion.product_id == product_id)
    if search_group is not None and search_group.strip():
        try:
            g = int(search_group.strip())
            q = q.filter(ProductQuestion.group == g)
        except ValueError:
            pass
    return q.count()


def create_question(db: Session, data: ProductQuestionCreate) -> ProductQuestion:
    now = datetime.now(timezone.utc)
    obj = ProductQuestion(
        user_name=data.user_name or "",
        content=data.content or "",
        group=data.group,
        product_id=data.product_id,
        useful=data.useful,
        reply_admin_name=data.reply_admin_name or "",
        reply_admin_content=data.reply_admin_content or "",
        reply_user_one_name=data.reply_user_one_name or "",
        reply_user_one_content=data.reply_user_one_content or "",
        reply_user_two_name=data.reply_user_two_name or "",
        reply_user_two_content=data.reply_user_two_content or "",
        reply_count=data.reply_count,
        is_active=data.is_active,
        is_imported=getattr(data, "is_imported", False),
    )
    if getattr(data, "created_at", None) is not None:
        obj.created_at = data.created_at
    if (data.reply_admin_content or data.reply_admin_name) and not obj.reply_admin_at:
        obj.reply_admin_at = now
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_question(db: Session, question_id: int, data: ProductQuestionUpdate) -> Optional[ProductQuestion]:
    obj = get_question(db, question_id)
    if not obj:
        return None
    now = datetime.now(timezone.utc)
    update_data = data.model_dump(exclude_unset=True)
    if "reply_admin_name" in update_data or "reply_admin_content" in update_data:
        update_data["reply_admin_at"] = now
    if "reply_user_one_name" in update_data or "reply_user_one_content" in update_data:
        update_data["reply_user_one_at"] = now
    if "reply_user_two_name" in update_data or "reply_user_two_content" in update_data:
        update_data["reply_user_two_at"] = now
    for k, v in update_data.items():
        if hasattr(obj, k):
            setattr(obj, k, v)
    obj.updated_at = now
    db.commit()
    db.refresh(obj)
    return obj


def delete_question(db: Session, question_id: int) -> bool:
    obj = get_question(db, question_id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True


def get_questions_for_product(
    db: Session,
    product_db_id: int,
    group_question: int,
    limit: int = 100,
) -> List[ProductQuestion]:
    """
    Lấy câu hỏi hiển thị trên trang chi tiết sản phẩm:
    - Câu hỏi theo nhóm: group = product.group_question (và product_id NULL)
    - Câu hỏi theo sản phẩm: product_id = product.id (khách hỏi)
    """
    q = db.query(ProductQuestion).filter(
        ProductQuestion.is_active == True,
        or_(
            and_(ProductQuestion.group == group_question, ProductQuestion.product_id.is_(None)),
            ProductQuestion.product_id == product_db_id,
        ),
    ).order_by(ProductQuestion.useful.desc(), ProductQuestion.created_at.desc())
    return q.limit(limit).all()


def get_shop_questions_by_ask_user_for_product(
    db: Session,
    *,
    product_db_id: int,
    ask_user_id: int,
) -> List[ProductQuestion]:
    """Toàn bộ câu hỏi trên SP do user `/ask` (ask_user_id) — không cắt theo «top useful»."""
    return (
        db.query(ProductQuestion)
        .filter(
            ProductQuestion.is_active == True,
            ProductQuestion.product_id == product_db_id,
            ProductQuestion.ask_user_id == ask_user_id,
        )
        .order_by(ProductQuestion.created_at.desc())
        .all()
    )


def list_shop_questions_legacy_null_ask_user_for_product(
    db: Session,
    *,
    product_db_id: int,
) -> List[ProductQuestion]:
    """Câu khách có product_id (group=0) chưa gắn ask_user_id — chỉnh client-side theo alias tên."""
    return (
        db.query(ProductQuestion)
        .filter(
            ProductQuestion.is_active == True,
            ProductQuestion.product_id == product_db_id,
            ProductQuestion.group == 0,
            ProductQuestion.ask_user_id.is_(None),
        )
        .all()
    )


def create_customer_question(
    db: Session,
    product_id: int,
    content: str,
    user_name: str,
    ask_user_id: int,
) -> ProductQuestion:
    """
    Khách đăng nhập đặt câu hỏi: lưu theo product_id, group=0.
    """
    obj = ProductQuestion(
        user_name=user_name or "Khách",
        content=content,
        group=0,
        product_id=product_id,
        ask_user_id=ask_user_id,
        useful=0,
        reply_count=0,
        is_active=True,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def add_user_reply(
    db: Session,
    question_id: int,
    user_id: int,
    user_name: str,
    content: str,
) -> Optional[ProductQuestion]:
    """
    Người đã mua hàng trả lời câu hỏi. Ghi vào slot user 1 hoặc user 2 (tối đa 2 người).
    """
    obj = get_question(db, question_id)
    if not obj:
        return None
    if obj.reply_count >= 2:
        return None
    now = datetime.now(timezone.utc)
    name = (user_name or "").strip() or "Người mua"
    content_clean = (content or "").strip()
    if not content_clean:
        return None
    if not obj.reply_user_one_content:
        obj.reply_user_one_id = user_id
        obj.reply_user_one_name = name
        obj.reply_user_one_content = content_clean
        obj.reply_user_one_at = now
    else:
        obj.reply_user_two_id = user_id
        obj.reply_user_two_name = name
        obj.reply_user_two_content = content_clean
        obj.reply_user_two_at = now
    obj.reply_count = min(2, (obj.reply_count or 0) + 1)
    obj.updated_at = now
    db.commit()
    db.refresh(obj)
    return obj


def get_user_voted_question_ids(db: Session, user_id: int, question_ids: List[int]) -> set:
    """Trả về set các question_id mà user đã bấm hữu ích."""
    if not question_ids:
        return set()
    rows = (
        db.query(ProductQuestionUsefulVote.question_id)
        .filter(
            ProductQuestionUsefulVote.user_id == user_id,
            ProductQuestionUsefulVote.question_id.in_(question_ids),
        )
        .all()
    )
    return {r[0] for r in rows}


def toggle_useful_vote(
    db: Session, question_id: int, user_id: int
) -> Optional[tuple[ProductQuestion, bool]]:
    """
    Bấm/bỏ bấm hữu ích. Trả về (question, user_has_voted_sau_khi_toggle).
    user_has_voted = True nghĩa là user đang vote (đã bấm hữu ích).
    """
    obj = get_question(db, question_id)
    if not obj:
        return None
    vote = (
        db.query(ProductQuestionUsefulVote)
        .filter(
            ProductQuestionUsefulVote.question_id == question_id,
            ProductQuestionUsefulVote.user_id == user_id,
        )
        .first()
    )
    if vote:
        db.delete(vote)
        obj.useful = max(0, (obj.useful or 0) - 1)
        user_has_voted_after = False
    else:
        db.add(ProductQuestionUsefulVote(question_id=question_id, user_id=user_id))
        obj.useful = (obj.useful or 0) + 1
        user_has_voted_after = True
    obj.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return (obj, user_has_voted_after)
