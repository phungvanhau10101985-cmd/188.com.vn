"""Email thông báo khi câu hỏi / đánh giá của khách có phản hồi mới."""

from __future__ import annotations

import hashlib
import html
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.models.product_question import ProductQuestion
from app.models.product_review import ProductReview
from app.models.user import User
from app.services.email_service import send_email

logger = logging.getLogger(__name__)

_VN_TZ = timezone(timedelta(hours=7))

# Admin sửa nhanh: gom email — 2 phút sau lần sửa cuối mới gửi 1 mail (nội dung DB lúc đó).
ADMIN_REPLY_EMAIL_DEBOUNCE_SECONDS = max(
    30,
    int(os.getenv("ADMIN_REPLY_EMAIL_DEBOUNCE_SECONDS", "120") or 120),
)

QUESTION_REPLY_SLOTS: tuple[tuple[str, str, str, str], ...] = (
    ("admin", "reply_admin_name", "reply_admin_content", "188.COM.VN"),
    ("user_one", "reply_user_one_name", "reply_user_one_content", "Người mua"),
    ("user_two", "reply_user_two_name", "reply_user_two_content", "Người mua"),
)

_QUESTION_SLOT_MAP = {slot: (name_key, content_key, default_name) for slot, name_key, content_key, default_name in QUESTION_REPLY_SLOTS}

_REPLY_EMAIL_SENT_DEDUP_MINUTES = max(
    1,
    int(os.getenv("PRODUCT_REPLY_EMAIL_DEDUP_MINUTES", "15") or 15),
)
_REPLY_EMAIL_POLL_SECONDS = max(
    5,
    int(os.getenv("PRODUCT_REPLY_EMAIL_POLL_SECONDS", "15") or 15),
)
_reply_email_daemon_started = False
_reply_email_daemon_lock = threading.Lock()


def _norm_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _subject_part(text: str, *, max_len: int = 42) -> str:
    cleaned = _norm_text(text)
    if not cleaned:
        return ""
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def _notify_stamp() -> str:
    """Mốc thời gian duy nhất — Gmail gom thread chủ yếu theo Subject."""
    now = datetime.now(_VN_TZ)
    return now.strftime("%d/%m %H:%M:%S") + f".{now.microsecond // 1000:03d}"


def build_reply_email_subject(
    *,
    kind: str,
    replier_name: str,
    product_name: str,
    reply_content: str,
    stamp: Optional[str] = None,
) -> str:
    """Subject khác nhau mỗi lần gửi — tránh Gmail gom thành 1 thread."""
    replier = _subject_part(replier_name or "188.COM.VN", max_len=28) or "188.COM.VN"
    product = _subject_part(product_name or "sản phẩm", max_len=40) or "sản phẩm"
    preview = _subject_part(reply_content, max_len=32)
    when = stamp or _notify_stamp()
    if kind == "question":
        base = f"{when} · Phản hồi câu hỏi · {product} · {replier}"
    else:
        base = f"{when} · Phản hồi đánh giá · {product} · {replier}"
    if preview:
        return f"{base}: {preview}"
    return base


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


def _norm_display_name(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _valid_email(value: object) -> Optional[str]:
    email = str(value or "").strip()
    if "@" not in email:
        return None
    return email


def _email_from_user_orders(
    db: Session,
    user_id: int,
    *,
    product_id: Optional[int] = None,
) -> Optional[str]:
    """Khách đăng nhập SĐT thường không có email trên tài khoản — lấy từ đơn hàng gần nhất."""
    q = db.query(Order).filter(
        Order.user_id == int(user_id),
        Order.customer_email.isnot(None),
        Order.customer_email != "",
    )
    if product_id:
        q = q.filter(
            Order.id.in_(
                db.query(OrderItem.order_id).filter(OrderItem.product_id == int(product_id))
            )
        )
    for order in q.order_by(Order.created_at.desc()).limit(10):
        email = _valid_email(getattr(order, "customer_email", None))
        if email:
            return email
    return None


def _resolve_recipient_email(
    db: Session,
    user: Optional[User],
    *,
    product_id: Optional[int] = None,
) -> Optional[str]:
    if not user:
        return None
    email = _valid_email(getattr(user, "email", None))
    if email:
        return email
    return _email_from_user_orders(db, int(user.id), product_id=product_id)


def _find_user_by_display_name(db: Session, display_name: str) -> Optional[User]:
    """Khớp tên hiển thị khi câu hỏi/đánh giá legacy chưa gắn user_id."""
    raw = str(display_name or "").strip()
    email = _valid_email(raw)
    if email:
        by_email = (
            db.query(User)
            .filter(User.is_active == True, func.lower(User.email) == email.lower())
            .first()
        )
        if by_email:
            return by_email

    norm = _norm_display_name(raw)
    if not norm:
        return None
    rows = (
        db.query(User)
        .filter(User.is_active == True)
        .filter(
            or_(
                func.lower(func.trim(User.full_name)) == norm,
                func.lower(func.trim(User.phone)) == norm,
            )
        )
        .limit(20)
        .all()
    )
    matched = [
        u
        for u in rows
        if _norm_display_name(getattr(u, "full_name", None)) == norm
        or _norm_display_name(getattr(u, "phone", None)) == norm
    ]
    if len(matched) == 1:
        return matched[0]
    if len(matched) > 1:
        with_email = [u for u in matched if _valid_email(getattr(u, "email", None))]
        if len(with_email) == 1:
            return with_email[0]
    return None


def _is_real_shop_customer_question(question: ProductQuestion) -> bool:
    """Câu khách trên SP (/ask hoặc legacy group=0 + product_id), không phải import Excel."""
    if bool(getattr(question, "is_imported", False)):
        return False
    if not getattr(question, "product_id", None):
        return False
    return int(getattr(question, "group", 0) or 0) == 0


def _resolve_question_asker_user(db: Session, question: ProductQuestion) -> Optional[User]:
    ask_user_id = getattr(question, "ask_user_id", None)
    if ask_user_id:
        return db.query(User).filter(User.id == int(ask_user_id)).first()
    if not _is_real_shop_customer_question(question):
        return None
    return _find_user_by_display_name(db, getattr(question, "user_name", "") or "")


def _is_real_customer_review(review: ProductReview) -> bool:
    return not bool(getattr(review, "is_imported", False))


def _resolve_review_author_user(db: Session, review: ProductReview) -> Optional[User]:
    user_id = getattr(review, "user_id", None)
    if user_id:
        return db.query(User).filter(User.id == int(user_id)).first()
    if not _is_real_customer_review(review):
        return None
    if not getattr(review, "product_id", None):
        return None
    return _find_user_by_display_name(db, getattr(review, "user_name", "") or "")


def _reply_pair_complete(name: object, content: object) -> bool:
    return bool(_norm_text(name)) and bool(_norm_text(content))


def _merged_update_value(before: object, update_data: dict, key: str) -> str:
    if key in update_data:
        return _norm_text(update_data.get(key, ""))
    return _norm_text(getattr(before, key, ""))


def collect_new_question_replies(before: ProductQuestion, update_data: dict) -> list[tuple[str, str, str]]:
    """Trả (slot, tên, nội dung) khi cặp tên+nội dung vừa đủ hoặc đổi."""
    out: list[tuple[str, str, str]] = []
    for slot_key, name_key, content_key, _default_name in QUESTION_REPLY_SLOTS:
        if name_key not in update_data and content_key not in update_data:
            continue
        old_name = _norm_text(getattr(before, name_key, ""))
        old_content = _norm_text(getattr(before, content_key, ""))
        new_name = _merged_update_value(before, update_data, name_key)
        new_content = _merged_update_value(before, update_data, content_key)
        if not _reply_pair_complete(new_name, new_content):
            continue
        old_complete = _reply_pair_complete(old_name, old_content)
        if not old_complete or new_content != old_content or new_name != old_name:
            out.append((slot_key, new_name, new_content))
    return out


def extract_question_reply_slots(replies: Iterable[tuple[str, str, str]]) -> list[str]:
    return list(dict.fromkeys(slot for slot, _, _ in replies))


def _question_slot_fingerprint(question: ProductQuestion, slot: str) -> Optional[str]:
    slot_info = _QUESTION_SLOT_MAP.get(slot)
    if not slot_info:
        return None
    name_key, content_key, default_name = slot_info
    name = _norm_text(getattr(question, name_key, "")) or default_name
    content = _norm_text(getattr(question, content_key, ""))
    if not _reply_pair_complete(name, content):
        return None
    raw = f"{name}|{content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _review_reply_fingerprint(review: ProductReview) -> Optional[str]:
    name = _norm_text(getattr(review, "reply_name", "")) or "188.COM.VN"
    content = _norm_text(getattr(review, "reply_content", ""))
    if not _reply_pair_complete(name, content):
        return None
    raw = f"{name}|{content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _was_reply_email_sent_recently(
    db: Session,
    *,
    kind: str,
    entity_id: int,
    slot: str,
    content_fingerprint: str,
) -> bool:
    from app.models.pending_product_reply_email import ProductReplyEmailSentLog

    since = datetime.now(timezone.utc) - timedelta(minutes=_REPLY_EMAIL_SENT_DEDUP_MINUTES)
    return (
        db.query(ProductReplyEmailSentLog)
        .filter(
            ProductReplyEmailSentLog.kind == kind,
            ProductReplyEmailSentLog.entity_id == int(entity_id),
            ProductReplyEmailSentLog.slot == slot,
            ProductReplyEmailSentLog.content_fingerprint == content_fingerprint,
            ProductReplyEmailSentLog.sent_at >= since,
        )
        .first()
        is not None
    )


def _mark_reply_email_sent(
    db: Session,
    *,
    kind: str,
    entity_id: int,
    slot: str,
    content_fingerprint: str,
) -> None:
    from app.models.pending_product_reply_email import ProductReplyEmailSentLog

    db.add(
        ProductReplyEmailSentLog(
            kind=kind,
            entity_id=int(entity_id),
            slot=slot,
            content_fingerprint=content_fingerprint,
        )
    )
    db.commit()


def enqueue_pending_reply_email(
    db: Session,
    *,
    kind: str,
    entity_id: int,
    slot: str,
    debounce_seconds: int,
    exclude_replier_user_id: Optional[int] = None,
) -> None:
    """Ghi hàng đợi DB — mỗi lần sửa reset send_after (debounce)."""
    from app.models.pending_product_reply_email import PendingProductReplyEmail

    send_after = datetime.now(timezone.utc) + timedelta(seconds=max(1, int(debounce_seconds)))
    row = (
        db.query(PendingProductReplyEmail)
        .filter(
            PendingProductReplyEmail.kind == kind,
            PendingProductReplyEmail.entity_id == int(entity_id),
            PendingProductReplyEmail.slot == slot,
        )
        .first()
    )
    if row:
        row.send_after = send_after
        row.exclude_replier_user_id = exclude_replier_user_id
    else:
        db.add(
            PendingProductReplyEmail(
                kind=kind,
                entity_id=int(entity_id),
                slot=slot,
                send_after=send_after,
                exclude_replier_user_id=exclude_replier_user_id,
            )
        )
    db.commit()
    logger.info(
        "reply_email enqueued kind=%s entity_id=%s slot=%s send_after=%s debounce=%ss",
        kind,
        entity_id,
        slot,
        send_after.isoformat(),
        debounce_seconds,
    )


def process_due_pending_reply_emails(db: Session) -> int:
    """Gửi email đến hạn — 1 lần / slot với nội dung mới nhất trên DB."""
    from app.models.pending_product_reply_email import PendingProductReplyEmail

    now = datetime.now(timezone.utc)
    due_rows = (
        db.query(PendingProductReplyEmail)
        .filter(PendingProductReplyEmail.send_after <= now)
        .order_by(PendingProductReplyEmail.send_after.asc())
        .with_for_update(skip_locked=True)
        .limit(50)
        .all()
    )
    processed = 0
    for row in due_rows:
        kind = row.kind
        entity_id = row.entity_id
        slot = row.slot
        exclude_replier_user_id = row.exclude_replier_user_id
        try:
            db.delete(row)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "process_due_pending_reply_email claim failed kind=%s entity_id=%s slot=%s",
                kind,
                entity_id,
                slot,
            )
            continue
        try:
            if kind == "question":
                sent = _send_question_reply_slot_if_ready(
                    db,
                    entity_id,
                    slot,
                    exclude_replier_user_id=exclude_replier_user_id,
                )
            elif kind == "review":
                sent = _send_review_reply_if_ready(db, entity_id)
            else:
                sent = False
            if sent:
                processed += 1
        except Exception:
            logger.exception(
                "process_due_pending_reply_email failed kind=%s entity_id=%s slot=%s",
                kind,
                entity_id,
                slot,
            )
    return processed


def _send_question_reply_slot_if_ready(
    db: Session,
    question_id: int,
    slot: str,
    *,
    exclude_replier_user_id: Optional[int] = None,
) -> bool:
    question = db.query(ProductQuestion).filter(ProductQuestion.id == question_id).first()
    if not question:
        return False
    fp = _question_slot_fingerprint(question, slot)
    if not fp:
        return False
    if _was_reply_email_sent_recently(
        db,
        kind="question",
        entity_id=question_id,
        slot=slot,
        content_fingerprint=fp,
    ):
        logger.info(
            "question_reply_email skip duplicate question_id=%s slot=%s fp=%s",
            question_id,
            slot,
            fp,
        )
        return False
    sent = notify_question_reply_slot_task(
        question_id,
        slot,
        exclude_replier_user_id=exclude_replier_user_id,
    )
    if not sent:
        return False
    _mark_reply_email_sent(
        db,
        kind="question",
        entity_id=question_id,
        slot=slot,
        content_fingerprint=fp,
    )
    return True


def _send_review_reply_if_ready(db: Session, review_id: int) -> bool:
    review = db.query(ProductReview).filter(ProductReview.id == review_id).first()
    if not review:
        return False
    fp = _review_reply_fingerprint(review)
    if not fp:
        return False
    slot = "reply"
    if _was_reply_email_sent_recently(
        db,
        kind="review",
        entity_id=review_id,
        slot=slot,
        content_fingerprint=fp,
    ):
        logger.info(
            "review_reply_email skip duplicate review_id=%s fp=%s",
            review_id,
            fp,
        )
        return False
    sent = notify_review_reply_task(review_id)
    if not sent:
        return False
    _mark_reply_email_sent(
        db,
        kind="review",
        entity_id=review_id,
        slot=slot,
        content_fingerprint=fp,
    )
    return True


def _reply_email_daemon_loop() -> None:
    from app.db.session import SessionLocal

    while True:
        db = SessionLocal()
        try:
            n = process_due_pending_reply_emails(db)
            if n:
                logger.info("reply_email daemon processed=%s", n)
        except Exception:
            logger.exception("reply_email daemon tick failed")
        finally:
            db.close()
        time.sleep(_REPLY_EMAIL_POLL_SECONDS)


def start_product_reply_email_daemon_if_needed() -> None:
    global _reply_email_daemon_started
    with _reply_email_daemon_lock:
        if _reply_email_daemon_started:
            return
        thread = threading.Thread(
            target=_reply_email_daemon_loop,
            name="product-reply-email-daemon",
            daemon=True,
        )
        thread.start()
        _reply_email_daemon_started = True
        logger.info(
            "product_reply_email daemon started poll=%ss debounce_default=%ss",
            _REPLY_EMAIL_POLL_SECONDS,
            ADMIN_REPLY_EMAIL_DEBOUNCE_SECONDS,
        )


def collect_new_review_reply(before: ProductReview, update_data: dict) -> Optional[tuple[str, str]]:
    if "reply_content" not in update_data and "reply_name" not in update_data:
        return None
    old_name = _norm_text(getattr(before, "reply_name", ""))
    old_content = _norm_text(getattr(before, "reply_content", ""))
    new_name = _merged_update_value(before, update_data, "reply_name")
    new_content = _merged_update_value(before, update_data, "reply_content")
    if not _reply_pair_complete(new_name, new_content):
        return None
    old_complete = _reply_pair_complete(old_name, old_content)
    if not old_complete or new_content != old_content or new_name != old_name:
        return (new_name, new_content)
    return None


def _image_site_base() -> str:
    for candidate in (
        getattr(settings, "MERCHANT_FEED_IMAGE_BASE_URL", ""),
        getattr(settings, "BUNNY_CDN_PUBLIC_BASE", ""),
        settings.FRONTEND_BASE_URL or settings.WEBSITE_URL or "",
    ):
        base = str(candidate or "").strip().rstrip("/")
        if base:
            return base
    return "https://188.com.vn"


def _abs_media_url(path_or_url: Optional[str]) -> str:
    if not path_or_url:
        return ""
    u = str(path_or_url).strip()
    if u.startswith("http://") or u.startswith("https://"):
        return u
    base = _image_site_base().rstrip("/")
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return base + u
    return f"{base}/{u}"


def _product_thumbnail_url(product: Optional[Product]) -> str:
    if not product:
        return ""
    main = getattr(product, "main_image", None)
    if main:
        return _abs_media_url(str(main))
    imgs = product.images if isinstance(getattr(product, "images", None), list) else []
    for item in imgs:
        if isinstance(item, dict):
            raw = item.get("url") or item.get("src") or item.get("image") or ""
        else:
            raw = item
        url = _abs_media_url(str(raw)) if raw else ""
        if url:
            return url
    return ""


def _product_page_url(product: Optional[Product]) -> str:
    segment = _product_path_segment(product)
    if not segment:
        return _frontend_origin()
    return f"{_frontend_origin()}/products/{segment}"


def _product_image_html(*, image_url: str, product_page_url: str, product_name: str) -> str:
    if not image_url:
        return ""
    alt = html.escape((product_name or "Sản phẩm").strip() or "Sản phẩm")
    return f"""
  <div style="margin:16px 0;text-align:center;">
    <a href="{html.escape(product_page_url)}" style="text-decoration:none;display:inline-block;">
      <img src="{html.escape(image_url)}" alt="{alt}" width="140" height="140"
           style="display:block;width:140px;height:140px;object-fit:cover;border-radius:12px;border:1px solid #e5e7eb;background:#f9fafb;" />
    </a>
    <p style="margin:8px 0 0;font-size:12px;color:#6b7280;">Bấm ảnh để xem sản phẩm</p>
  </div>
"""


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
    author_name: str,
    original_snippet: str,
    replier_name: str,
    reply_content: str,
    view_url: str,
    product_name: str,
    product_image_url: str = "",
    product_page_url: str = "",
) -> bool:
    if not to_email or not settings.is_smtp_configured():
        logger.warning(
            "product_reply_email skip send: smtp=%s to=%s kind=%s",
            settings.is_smtp_configured(),
            to_email or "(empty)",
            kind,
        )
        return False

    display_name = (customer_name or "Quý khách").strip() or "Quý khách"
    author = (author_name or display_name).strip() or display_name
    replier = (replier_name or "188.COM.VN").strip() or "188.COM.VN"
    reply_body = _norm_text(reply_content)
    original = _norm_text(original_snippet)
    product_label = (product_name or "sản phẩm").strip() or "sản phẩm"
    sent_at = datetime.now(_VN_TZ).strftime("%d/%m/%Y %H:%M")

    if kind == "question":
        lead = f"Câu hỏi của bạn về {product_label} đã có phản hồi mới."
        author_label = "Bạn hỏi"
        content_label = "Nội dung câu hỏi"
        cta = "Xem lại câu hỏi"
        link_label = "Link xem lại câu hỏi"
    else:
        lead = f"Đánh giá của bạn về {product_label} đã được shop phản hồi."
        author_label = "Bạn đánh giá"
        content_label = "Nội dung đánh giá"
        cta = "Xem lại đánh giá"
        link_label = "Link xem lại đánh giá"

    subject = build_reply_email_subject(
        kind=kind,
        replier_name=replier,
        product_name=product_label,
        reply_content=reply_body,
    )

    if settings.EMAIL_SUBJECT_PREFIX:
        subject = f"{settings.EMAIL_SUBJECT_PREFIX} {subject}"

    notify_id = str(uuid.uuid4())
    page_url = (product_page_url or view_url).strip()
    image_block = _product_image_html(
        image_url=product_image_url,
        product_page_url=page_url,
        product_name=product_label,
    )

    text_body = (
        f"Xin chào {display_name},\n\n"
        f"({sent_at}) {lead}\n\n"
    )
    if product_image_url:
        text_body += f"Ảnh sản phẩm: {product_image_url}\nXem sản phẩm: {page_url}\n\n"
    text_body += (
        f"{author_label}: {author}\n"
        f"{content_label}:\n{original}\n\n"
        f"Tên người trả lời: {replier}\n"
        f"Nội dung trả lời:\n{reply_body}\n\n"
        f"{link_label}: {view_url}\n\n"
        "Trân trọng,\n188.com.vn"
    )

    html_body = f"""
<div style="font-family:system-ui,-apple-system,'Segoe UI',sans-serif;font-size:15px;line-height:1.55;color:#111827;max-width:560px;">
  <p>Xin chào <strong>{html.escape(display_name)}</strong>,</p>
  <p><span style="color:#6b7280;font-size:13px;">({html.escape(sent_at)})</span> {html.escape(lead)}</p>
  {image_block}
  <div style="margin:16px 0;padding:12px 14px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;">
    <p style="margin:0 0 4px;font-size:13px;font-weight:600;color:#374151;">{html.escape(author_label)}: {html.escape(author)}</p>
    <p style="margin:8px 0 6px;font-size:12px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:.03em;">{html.escape(content_label)}</p>
    <p style="margin:0;color:#374151;white-space:pre-wrap;">{html.escape(original)}</p>
  </div>
  <div style="margin:16px 0;padding:12px 14px;background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;">
    <p style="margin:0 0 6px;font-size:13px;font-weight:600;color:#c2410c;">Tên người trả lời: {html.escape(replier)}</p>
    <p style="margin:0 0 6px;font-size:12px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:.03em;">Nội dung trả lời</p>
    <p style="margin:0;color:#374151;white-space:pre-wrap;">{html.escape(reply_body)}</p>
  </div>
  <p style="margin:20px 0 12px;">
    <a href="{html.escape(view_url)}" style="display:inline-block;padding:12px 22px;background:#ea580c;color:#ffffff !important;text-decoration:none;border-radius:10px;font-weight:600;">
      {html.escape(cta)}
    </a>
  </p>
  <p style="font-size:12px;color:#6b7280;word-break:break-all;">{html.escape(link_label)}: <a href="{html.escape(view_url)}">{html.escape(view_url)}</a></p>
  <p style="margin-top:24px;">Trân trọng,<br/>188.com.vn</p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;" />
  <p style="font-size:12px;color:#9ca3af;">Tin nhắn tự động từ 188.com.vn</p>
</div>
"""
    sent = send_email(
        to_email,
        subject,
        text_body,
        html_body,
        extra_headers={
            "X-188-Notify-Id": notify_id,
            "X-188-Notify-Type": kind,
        },
        prevent_threading=True,
    )
    if sent:
        logger.info("product_reply_email sent kind=%s to=%s", kind, to_email)
    else:
        logger.warning("product_reply_email not sent kind=%s to=%s", kind, to_email)
    return bool(sent)


def _load_product(db: Session, product_id: Optional[int]) -> Optional[Product]:
    if not product_id:
        return None
    return db.query(Product).filter(Product.id == int(product_id)).first()


def notify_question_reply_slot_task(
    question_id: int,
    slot: str,
    *,
    exclude_replier_user_id: Optional[int] = None,
) -> bool:
    """Gửi 1 email — đọc nội dung trả lời mới nhất từ DB (sau debounce admin)."""
    slot_info = _QUESTION_SLOT_MAP.get(slot)
    if not slot_info:
        return False
    name_key, content_key, default_name = slot_info

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        question = db.query(ProductQuestion).filter(ProductQuestion.id == question_id).first()
        if not question or bool(getattr(question, "is_imported", False)):
            logger.info(
                "question_reply_email skip: missing or imported question_id=%s",
                question_id,
            )
            return False

        replier_name = _norm_text(getattr(question, name_key, "")) or default_name
        reply_content = _norm_text(getattr(question, content_key, ""))
        if not _reply_pair_complete(replier_name, reply_content):
            logger.info(
                "question_reply_email skip: incomplete slot=%s question_id=%s",
                slot,
                question_id,
            )
            return False

        user = _resolve_question_asker_user(db, question)
        if not user:
            logger.info(
                "question_reply_email skip: no asker user question_id=%s ask_user_id=%s user_name=%r",
                question_id,
                getattr(question, "ask_user_id", None),
                getattr(question, "user_name", None),
            )
            return False

        ask_user_id = int(user.id)
        if exclude_replier_user_id is not None and ask_user_id == int(exclude_replier_user_id):
            return False

        if not getattr(question, "ask_user_id", None):
            question.ask_user_id = ask_user_id
            db.commit()

        product_id = getattr(question, "product_id", None)
        to_email = _resolve_recipient_email(db, user, product_id=product_id)
        if not to_email:
            logger.info(
                "question_reply_email skip: no email question_id=%s user_id=%s",
                question_id,
                ask_user_id,
            )
            return False
        asker_name = (getattr(question, "user_name", None) or "").strip()
        customer_name = (
            (getattr(user, "full_name", None) or "").strip()
            or asker_name
            or "Quý khách"
        )
        product = _load_product(db, getattr(question, "product_id", None))
        product_name = (getattr(product, "name", None) or "").strip() if product else "sản phẩm"
        product_image_url = _product_thumbnail_url(product)
        product_page_url = _product_page_url(product)
        view_url = _question_view_url(product, question.id)
        original = getattr(question, "content", "") or ""

        sent = _send_reply_email(
            to_email=to_email,
            customer_name=customer_name,
            kind="question",
            author_name=asker_name or customer_name,
            original_snippet=original,
            replier_name=replier_name,
            reply_content=reply_content,
            view_url=view_url,
            product_name=product_name,
            product_image_url=product_image_url,
            product_page_url=product_page_url,
        )
        return sent
    except Exception:
        logger.exception("question_reply_email failed question_id=%s slot=%s", question_id, slot)
        return False
    finally:
        db.close()


def notify_review_reply_task(review_id: int) -> bool:
    """Gửi email phản hồi đánh giá — đọc nội dung mới nhất từ DB."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        review = db.query(ProductReview).filter(ProductReview.id == review_id).first()
        if not review or bool(getattr(review, "is_imported", False)):
            logger.info(
                "review_reply_email skip: missing or imported review_id=%s",
                review_id,
            )
            return False

        replier_name = _norm_text(getattr(review, "reply_name", "")) or "188.COM.VN"
        reply_content = _norm_text(getattr(review, "reply_content", ""))
        if not _reply_pair_complete(replier_name, reply_content):
            logger.info(
                "review_reply_email skip: incomplete reply review_id=%s",
                review_id,
            )
            return False

        user = _resolve_review_author_user(db, review)
        if not user:
            logger.info(
                "review_reply_email skip: no author user review_id=%s user_id=%s user_name=%r",
                review_id,
                getattr(review, "user_id", None),
                getattr(review, "user_name", None),
            )
            return False

        user_id = int(user.id)
        if not getattr(review, "user_id", None):
            review.user_id = user_id
            db.commit()

        product_id = getattr(review, "product_id", None)
        to_email = _resolve_recipient_email(db, user, product_id=product_id)
        if not to_email:
            logger.info(
                "review_reply_email skip: no email review_id=%s user_id=%s",
                review_id,
                user_id,
            )
            return False
        reviewer_name = (getattr(review, "user_name", None) or "").strip()
        customer_name = (
            (getattr(user, "full_name", None) or "").strip()
            or reviewer_name
            or "Quý khách"
        )
        product = _load_product(db, getattr(review, "product_id", None))
        product_name = (getattr(product, "name", None) or "").strip() if product else "sản phẩm"
        product_image_url = _product_thumbnail_url(product)
        product_page_url = _product_page_url(product)
        view_url = _review_view_url(product, review.id)
        original = getattr(review, "content", "") or ""

        sent = _send_reply_email(
            to_email=to_email,
            customer_name=customer_name,
            kind="review",
            author_name=reviewer_name or customer_name,
            original_snippet=original,
            replier_name=replier_name,
            reply_content=reply_content,
            view_url=view_url,
            product_name=product_name,
            product_image_url=product_image_url,
            product_page_url=product_page_url,
        )
        return sent
    except Exception:
        logger.exception("review_reply_email failed review_id=%s", review_id)
        return False
    finally:
        db.close()


def _background_send_question_reply_slot(
    question_id: int,
    slot: str,
    *,
    exclude_replier_user_id: Optional[int] = None,
) -> None:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        _send_question_reply_slot_if_ready(
            db,
            question_id,
            slot,
            exclude_replier_user_id=exclude_replier_user_id,
        )
    finally:
        db.close()


def _background_send_review_reply(review_id: int) -> None:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        _send_review_reply_if_ready(db, review_id)
    finally:
        db.close()


def schedule_question_reply_emails(
    background_tasks,
    db: Session,
    question_id: int,
    reply_slots: Iterable[str],
    *,
    exclude_replier_user_id: Optional[int] = None,
    debounce_seconds: int = 0,
) -> None:
    slots = list(dict.fromkeys(str(s) for s in reply_slots if s))
    if not slots:
        return
    start_product_reply_email_daemon_if_needed()
    if debounce_seconds > 0:
        for slot in slots:
            enqueue_pending_reply_email(
                db,
                kind="question",
                entity_id=question_id,
                slot=slot,
                debounce_seconds=debounce_seconds,
                exclude_replier_user_id=exclude_replier_user_id,
            )
        return
    for slot in slots:
        background_tasks.add_task(
            _background_send_question_reply_slot,
            question_id,
            slot,
            exclude_replier_user_id=exclude_replier_user_id,
        )


def schedule_review_reply_email(
    background_tasks,
    db: Session,
    review_id: int,
    *,
    debounce_seconds: int = 0,
) -> None:
    start_product_reply_email_daemon_if_needed()
    if debounce_seconds > 0:
        enqueue_pending_reply_email(
            db,
            kind="review",
            entity_id=review_id,
            slot="reply",
            debounce_seconds=debounce_seconds,
        )
        return
    background_tasks.add_task(_background_send_review_reply, review_id)
