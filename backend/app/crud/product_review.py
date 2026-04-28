from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import List, Optional
from datetime import datetime, timezone

from app.models.product_review import ProductReview, ProductReviewUsefulVote
from app.schemas.product_review import ProductReviewCreate, ProductReviewUpdate, ProductReviewSubmit


def get_review(db: Session, review_id: int) -> Optional[ProductReview]:
    return db.query(ProductReview).filter(ProductReview.id == review_id).first()


def get_reviews_for_product(
    db: Session,
    product_db_id: int,
    group_rating: int,
    limit: int = 100,
) -> List[ProductReview]:
    """
    Lấy đánh giá hiển thị trên trang sản phẩm (giống logic câu hỏi).
    - Khách đánh giá: product_id = product.id → hiển thị theo sản phẩm đã mua.
    - Import: group = product.group_rating, product_id NULL → hiển thị theo nhóm.
    Sắp xếp: useful DESC, created_at DESC.
    """
    q = db.query(ProductReview).filter(
        ProductReview.is_active == True,
        or_(
            and_(ProductReview.group == group_rating, ProductReview.product_id.is_(None)),
            ProductReview.product_id == product_db_id,
        ),
    ).order_by(ProductReview.useful.desc(), ProductReview.created_at.desc())
    return q.limit(limit).all()


def get_user_reviewed_product_ids(db: Session, user_id: int, product_ids: List[int]) -> set:
    """Sản phẩm mà user đã đánh giá (review có user_id và product_id)."""
    if not product_ids:
        return set()
    rows = (
        db.query(ProductReview.product_id)
        .filter(
            ProductReview.user_id == user_id,
            ProductReview.product_id.in_(product_ids),
        )
        .distinct()
        .all()
    )
    return {r[0] for r in rows if r[0]}


def get_user_voted_review_ids(db: Session, user_id: int, review_ids: List[int]) -> set:
    if not review_ids:
        return set()
    rows = (
        db.query(ProductReviewUsefulVote.review_id)
        .filter(
            ProductReviewUsefulVote.user_id == user_id,
            ProductReviewUsefulVote.review_id.in_(review_ids),
        )
        .all()
    )
    return {r[0] for r in rows}


def toggle_useful_vote(
    db: Session, review_id: int, user_id: int
) -> Optional[tuple[ProductReview, bool]]:
    obj = get_review(db, review_id)
    if not obj:
        return None
    vote = (
        db.query(ProductReviewUsefulVote)
        .filter(
            ProductReviewUsefulVote.review_id == review_id,
            ProductReviewUsefulVote.user_id == user_id,
        )
        .first()
    )
    if vote:
        db.delete(vote)
        obj.useful = max(0, (obj.useful or 0) - 1)
        user_has_voted_after = False
    else:
        db.add(ProductReviewUsefulVote(review_id=review_id, user_id=user_id))
        obj.useful = (obj.useful or 0) + 1
        user_has_voted_after = True
    obj.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return (obj, user_has_voted_after)


def create_customer_review(
    db: Session,
    product_id: int,
    user_name: str,
    star: int,
    content: str,
    title: str = "",
    images: Optional[List[str]] = None,
    user_id: Optional[int] = None,
) -> ProductReview:
    """Khách đăng nhập gửi đánh giá thực tế."""
    from app.models.product import Product
    product = db.query(Product).filter(Product.id == product_id).first()
    group_val = (product.group_rating or 0) if product else 0
    star_val = max(1, min(5, star))
    title_val = (title or "").strip()
    if not title_val:
        titles = {1: "Rất không hài lòng", 2: "Không hài lòng", 3: "Tạm được", 4: "Hài lòng", 5: "Cực hài lòng"}
        title_val = titles.get(star_val, "Đánh giá")
    obj = ProductReview(
        user_name=user_name or "Khách",
        star=star_val,
        title=title_val,
        content=(content or "").strip(),
        user_id=user_id,
        group=group_val,
        product_id=product_id,
        useful=0,
        reply_name="",
        reply_content="",
        images=images or [],
        is_active=True,
        is_imported=False,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def create_review(db: Session, data: ProductReviewCreate) -> ProductReview:
    obj = ProductReview(
        user_name=data.user_name or "",
        star=data.star,
        title=data.title or "",
        content=data.content or "",
        group=data.group,
        product_id=data.product_id,
        useful=data.useful,
        reply_name=data.reply_name or "",
        reply_content=data.reply_content or "",
        images=data.images or [],
        is_active=data.is_active,
        is_imported=getattr(data, "is_imported", False),
    )
    if getattr(data, "created_at", None) is not None:
        obj.created_at = data.created_at
    if obj.reply_content and getattr(data, "created_at", None) is not None:
        obj.reply_at = data.created_at
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_review(db: Session, review_id: int, data: ProductReviewUpdate) -> Optional[ProductReview]:
    obj = get_review(db, review_id)
    if not obj:
        return None
    now = datetime.now(timezone.utc)
    update_data = data.model_dump(exclude_unset=True)
    if "reply_name" in update_data or "reply_content" in update_data:
        update_data["reply_at"] = now
    for k, v in update_data.items():
        if hasattr(obj, k):
            setattr(obj, k, v)
    obj.updated_at = now
    db.commit()
    db.refresh(obj)
    return obj


def delete_review(db: Session, review_id: int) -> bool:
    obj = get_review(db, review_id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True
