"""Email thông báo khi câu hỏi / đánh giá của khách có phản hồi mới."""

from __future__ import annotations

import html
import logging
from typing import Iterable, Optional, Sequence

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.product import Product
from app.models.product_question import ProductQuestion
from app.models.product_review import ProductReview
from app.models.user import User
from app.services.email_service import send_email

logger = logging.getLogger(__name__)

QUESTION_REPLY_SLOTS: tuple[tuple[str, str, str], ...] = (
    ("reply_admin_name", "reply_admin_content", "188.COM.VN"),
    ("reply_user_one_name", "reply_user_one_content", "Người mua"),
    ("reply_user_two_name", "reply_user_two_content", "Người mua"),
)


def _norm_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _text_preview(text: str, *, max_len: int = 240) -> str:
    cleaned = _norm_text(text)
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def _frontend_origin() -> str:
    fe = (settings.FRONTEND_BASE_URL or settings.WEBSITE_URL or "").strip().rstrip("/")
    return fe or "https://188.com.vn"


def _product_path_segment(product: Optional[Product]) -> str:
    if not product:
        return ""
    slug = (getattr(product, "slug", None) or "").strip()
    if slug:
        if slug.startswith("/products/"):
            return slug.split("/products/", 1)[-1].split("/")[0].split("?")[0]
        if slug.startswith("http://") or slug.startswith("https://"):
            try:
                from urllib.parse import urlparse

                path = urlparse(slug).path.strip("/").split("/")
                if "products" in path:
                    idx = path.index("products")
                    if idx + 1 < len(path):
                        return path[idx + 1]
                if path:
                    return path[-1]
            except Exception:
                pass
        return slug.split("/")[0].split("?")[0]
    return (getattr(product, "product_id", None) or "").strip()


def _user_email(db: Session, user_id: Optional[int]) -> Optional[str]:
    if not user_id:
        return None
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        return None
    email = (getattr(user, "email", None) or "").strip()
    if "@" not in email:
        return None
    return email


def collect_new_question_replies(before: ProductQuestion, update_data: dict) -> list[tuple[str, str]]:
    """Trả danh sách (tên người trả lời, nội dung) vừa thêm hoặc đổi nội dung."""
    out: list[tuple[str, str]] = []
    for name_key, content_key, default_name in QUESTION_REPLY_SLOTS:
        if content_key not in update_data:
            continue
        new_content = _norm_text(update_data.get(content_key, ""))
        old_content = _norm_text(getattr(before, content_key, ""))
        if not new_content or new_content == old_content:
            continue
        name = _norm_text(update_data.get(name_key, getattr(before, name_key, ""))) or default_name
        out.append((name, new_content))
    return out


def collect_new_review_reply(before: ProductReview, update_data: dict) -> Optional[tuple[str, str]]:
    if "reply_content" not in update_data:
        return None
    new_content = _norm_text(update_data.get("reply_content", ""))
    old_content = _norm_text(getattr(before, "reply_content", ""))
    if not new_content or new_content == old_content:
        return None
    name = _norm_text(update_data.get("reply_name", getattr(before, "reply_name", ""))) or "188.COM.VN"
    return (name, new_content)


def _question_view_url(product: Optional[Product], question_id: int) -> str:
    segment = _product_path_segment(product)
    if not segment:
        return _frontend_origin()
    return f"{_frontend_origin()}/products/{segment}#question-{question_id}"


def _review_view_url(product: Optional[Product], review_id: int) -> str:
    segment = _product_path_segment(product)
    if not segment:
        return _frontend_origin()
    return f"{_frontend_origin()}/products/{segment}#review-{review_id}"


def _send_reply_email(
    *,
    to_email: str,
    customer_name: str,
    kind: str,
    original_snippet: str,
    replier_name: str,
    reply_content: str,
    view_url: str,
    product_name: str,
) -> None:
    if not to_email or not settings.is_smtp_configured():
        return

    display_name = (customer_name or "Quý khách").strip() or "Quý khách"
    replier = (replier_name or "188.COM.VN").strip() or "188.COM.VN"
    reply_body = _text_preview(reply_content)
    original = _text_preview(original_snippet)
    product_label = (product_name or "sản phẩm").strip() or "sản phẩm"

    if kind == "question":
        subject = "188.com.vn — Có phản hồi mới cho câu hỏi của bạn"
        lead = f"Câu hỏi của bạn về {product_label} đã có phản hồi mới."
        original_label = "Câu hỏi của bạn"
        cta = "Xem câu hỏi và phản hồi"
    else:
        subject = "188.com.vn — Shop đã phản hồi đánh giá của bạn"
        lead = f"Đánh giá của bạn về {product_label} đã được shop phản hồi."
        original_label = "Đánh giá của bạn"
        cta = "Xem đánh giá và phản hồi"

    if settings.EMAIL_SUBJECT_PREFIX:
        subject = f"{settings.EMAIL_SUBJECT_PREFIX} {subject}"

    text_body = (
        f"Xin chào {display_name},\n\n"
        f"{lead}\n\n"
        f"{original_label}:\n{original}\n\n"
        f"{replier} trả lời:\n{reply_body}\n\n"
        f"Xem chi tiết: {view_url}\n\n"
        "Trân trọng,\n188.com.vn"
    )

    html_body = f"""
<div style="font-family:system-ui,-apple-system,'Segoe UI',sans-serif;font-size:15px;line-height:1.55;color:#111827;max-width:560px;">
  <p>Xin chào <strong>{html.escape(display_name)}</strong>,</p>
  <p>{html.escape(lead)}</p>
  <div style="margin:16px 0;padding:12px 14px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;">
    <p style="margin:0 0 6px;font-size:12px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:.03em;">{html.escape(original_label)}</p>
    <p style="margin:0;color:#374151;">{html.escape(original)}</p>
  </div>
  <div style="margin:16px 0;padding:12px 14px;background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;">
    <p style="margin:0 0 6px;font-size:13px;font-weight:600;color:#c2410c;">{html.escape(replier)} trả lời</p>
    <p style="margin:0;color:#374151;">{html.escape(reply_body)}</p>
  </div>
  <p style="margin:20px 0 12px;">
    <a href="{html.escape(view_url)}" style="display:inline-block;padding:12px 22px;background:#ea580c;color:#ffffff !important;text-decoration:none;border-radius:10px;font-weight:600;">
      {html.escape(cta)}
    </a>
  </p>
  <p style="font-size:12px;color:#6b7280;word-break:break-all;">Hoặc mở liên kết: <a href="{html.escape(view_url)}">{html.escape(view_url)}</a></p>
  <p style="margin-top:24px;">Trân trọng,<br/>188.com.vn</p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;" />
  <p style="font-size:12px;color:#9ca3af;">Tin nhắn tự động từ 188.com.vn</p>
</div>
"""
    sent = send_email(to_email, subject, text_body, html_body)
    if sent:
        logger.info("product_reply_email sent kind=%s to=%s", kind, to_email)


def _load_product(db: Session, product_id: Optional[int]) -> Optional[Product]:
    if not product_id:
        return None
    return db.query(Product).filter(Product.id == int(product_id)).first()


def notify_question_replies_task(
    question_id: int,
    replies: Sequence[tuple[str, str]],
    *,
    exclude_replier_user_id: Optional[int] = None,
) -> None:
    """Gửi email cho người hỏi — mỗi phản hồi mới một email."""
    if not replies:
        return

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        question = db.query(ProductQuestion).filter(ProductQuestion.id == question_id).first()
        if not question or bool(getattr(question, "is_imported", False)):
            return
        ask_user_id = getattr(question, "ask_user_id", None)
        if not ask_user_id:
            return
        if exclude_replier_user_id is not None and int(ask_user_id) == int(exclude_replier_user_id):
            return

        to_email = _user_email(db, int(ask_user_id))
        if not to_email:
            logger.info("question_reply_email skip: no email question_id=%s user_id=%s", question_id, ask_user_id)
            return

        user = db.query(User).filter(User.id == int(ask_user_id)).first()
        customer_name = (
            (getattr(user, "full_name", None) or "").strip()
            or (getattr(question, "user_name", None) or "").strip()
            or "Quý khách"
        )
        product = _load_product(db, getattr(question, "product_id", None))
        product_name = (getattr(product, "name", None) or "").strip() if product else "sản phẩm"
        view_url = _question_view_url(product, question.id)
        original = getattr(question, "content", "") or ""

        for replier_name, reply_content in replies:
            _send_reply_email(
                to_email=to_email,
                customer_name=customer_name,
                kind="question",
                original_snippet=original,
                replier_name=replier_name,
                reply_content=reply_content,
                view_url=view_url,
                product_name=product_name,
            )
    except Exception:
        logger.exception("question_reply_email failed question_id=%s", question_id)
    finally:
        db.close()


def notify_review_reply_task(
    review_id: int,
    replier_name: str,
    reply_content: str,
) -> None:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        review = db.query(ProductReview).filter(ProductReview.id == review_id).first()
        if not review or bool(getattr(review, "is_imported", False)):
            return
        user_id = getattr(review, "user_id", None)
        if not user_id:
            return

        to_email = _user_email(db, int(user_id))
        if not to_email:
            logger.info("review_reply_email skip: no email review_id=%s user_id=%s", review_id, user_id)
            return

        user = db.query(User).filter(User.id == int(user_id)).first()
        customer_name = (
            (getattr(user, "full_name", None) or "").strip()
            or (getattr(review, "user_name", None) or "").strip()
            or "Quý khách"
        )
        product = _load_product(db, getattr(review, "product_id", None))
        product_name = (getattr(product, "name", None) or "").strip() if product else "sản phẩm"
        view_url = _review_view_url(product, review.id)
        original = getattr(review, "content", "") or ""

        _send_reply_email(
            to_email=to_email,
            customer_name=customer_name,
            kind="review",
            original_snippet=original,
            replier_name=replier_name,
            reply_content=reply_content,
            view_url=view_url,
            product_name=product_name,
        )
    except Exception:
        logger.exception("review_reply_email failed review_id=%s", review_id)
    finally:
        db.close()


def schedule_question_reply_emails(
    background_tasks,
    question_id: int,
    replies: Iterable[tuple[str, str]],
    *,
    exclude_replier_user_id: Optional[int] = None,
) -> None:
    reply_list = list(replies)
    if not reply_list:
        return
    background_tasks.add_task(
        notify_question_replies_task,
        question_id,
        reply_list,
        exclude_replier_user_id=exclude_replier_user_id,
    )


def schedule_review_reply_email(
    background_tasks,
    review_id: int,
    replier_name: str,
    reply_content: str,
) -> None:
    if not _norm_text(reply_content):
        return
    background_tasks.add_task(
        notify_review_reply_task,
        review_id,
        replier_name,
        reply_content,
    )
