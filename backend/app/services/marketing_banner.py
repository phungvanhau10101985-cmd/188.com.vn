from __future__ import annotations

import hashlib
import html
import io
import logging
import re
import time
import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from PIL import Image
from sqlalchemy import extract, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.admin import AdminUser
from app.models.marketing_banner import MarketingBannerAsset
from app.models.user import User
from app.services.birthday_discount import BIRTHDAY_DISCOUNT_PERCENT
from app.services.bunny_storage import build_public_object_url, upload_file_to_zone
from app.services.category_size_guide_gemini import gemini_generate_image_from_text
from app.services.email_service import send_email
from app.services.sale_calendar import list_upcoming_events

logger = logging.getLogger(__name__)
VN_TZ = timezone(timedelta(hours=7))
ASPECT_RATIO = "21:9"


def _pct_key(value: float | Decimal) -> str:
    normalized = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return normalized.replace(".", "_")


def campaign_key(kind: str, day: int, month: int, discount_percent: float) -> str:
    return f"{kind}-{month:02d}-{day:02d}-p{_pct_key(discount_percent)}"


def _display_pct(value: float | Decimal) -> str:
    return f"{float(value):g}%"


def build_banner_prompt(
    *,
    kind: str,
    day: int,
    month: int,
    discount_percent: float,
) -> str:
    label = f"{day:02d}/{month:02d}"
    pct = _display_pct(discount_percent)
    shared = (
        "Tạo đúng MỘT banner thương mại điện tử siêu rộng 21:9, chất lượng 2K, "
        "dùng nguyên ảnh trên desktop lẫn mobile, không crop. Phong cách cao cấp, "
        "ấn tượng, chuyển đổi cao, màu cam-đỏ-trắng theo thương hiệu 188.com.vn. "
        "Logo chữ 188.com.vn rõ ràng. Chữ tiếng Việt phải lớn, ít, đúng chính tả, "
        "độ tương phản cao; không thêm mức giảm khác. Không dùng watermark hoặc logo hãng khác. "
    )
    if kind == "sale":
        return shared + (
            f'Bắt buộc ghi nguyên văn: "SALE {day}.{month} - GIẢM {pct}". '
            'Một câu vần ngắn: "Ngày tháng trùng nhau - deal xịn trao tay". '
            'CTA dạng nút: "MUA NGAY HÔM NAY". '
            "Dùng hình sản phẩm thời trang, giày dép, phụ kiện hiện đại; tạo cảm giác khẩn cấp. "
            "Đặt toàn bộ chữ quan trọng ở giữa ảnh và đủ lớn để đọc trên màn hình điện thoại."
        )
    return shared + (
        f'Bắt buộc ghi nguyên văn: "MỪNG SINH NHẬT {label} - TẶNG {pct}". '
        'Một câu thơ ngắn: "Thêm tuổi thêm vui - quà xinh đang đợi". '
        'CTA dạng nút: "NHẬN QUÀ SINH NHẬT". '
        "Không ghi tên khách và không ghi năm sinh. Trang trí quà tặng, bánh sinh nhật, "
        "confetti vừa đủ, sang trọng và ấm áp. Đặt toàn bộ chữ quan trọng ở giữa ảnh "
        "và đủ lớn để đọc trên màn hình điện thoại."
    )


def _image_dimensions(data: bytes) -> tuple[Optional[int], Optional[int], str]:
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            fmt = (image.format or "PNG").lower()
            ext = ".jpg" if fmt in ("jpeg", "jpg") else f".{fmt}"
            return width, height, ext if ext in (".png", ".jpg", ".webp") else ".png"
    except Exception:
        return None, None, ".png"


def _upload_banner(data: bytes, *, kind: str, key: str, version: int) -> str:
    zone = (getattr(settings, "BUNNY_STORAGE_ZONE_NAME", "") or "").strip()
    access_key = (getattr(settings, "BUNNY_STORAGE_ACCESS_KEY", "") or "").strip()
    public_base = (getattr(settings, "BUNNY_CDN_PUBLIC_BASE", "") or "").strip()
    if not zone or not access_key or not public_base:
        raise RuntimeError("Thiếu cấu hình Bunny Storage/CDN cho banner.")
    _, _, ext = _image_dimensions(data)
    safe_key = re.sub(r"[^a-zA-Z0-9_-]+", "-", key).strip("-")
    digest = hashlib.sha1(data).hexdigest()[:12]
    prefix = (getattr(settings, "BUNNY_UPLOAD_PATH_PREFIX", "") or "site").strip("/")
    remote_path = (
        f"{prefix}/marketing-banners/{kind}/{safe_key}/"
        f"v{version}-{int(time.time())}-{digest}{ext}"
    )
    upload_file_to_zone(
        zone_name=zone,
        access_key=access_key,
        remote_path=remote_path,
        data=data,
        content_type="image/jpeg" if ext == ".jpg" else f"image/{ext.lstrip('.')}",
    )
    return build_public_object_url(public_base, remote_path)


def serialize_asset(row: MarketingBannerAsset) -> Dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.kind,
        "campaign_key": row.campaign_key,
        "date_key": row.date_key,
        "discount_percent": float(row.discount_percent),
        "image_url": row.image_url,
        "aspect_ratio": row.aspect_ratio,
        "image_width": row.image_width,
        "image_height": row.image_height,
        "prompt": row.prompt,
        "provider": row.provider,
        "model": row.model,
        "status": row.status,
        "error_message": row.error_message,
        "version": row.version,
        "is_active": bool(row.is_active),
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def find_active_asset(
    db: Session,
    *,
    kind: str,
    day: int,
    month: int,
    discount_percent: float,
) -> Optional[MarketingBannerAsset]:
    key = campaign_key(kind, day, month, discount_percent)
    return (
        db.query(MarketingBannerAsset)
        .filter(
            MarketingBannerAsset.kind == kind,
            MarketingBannerAsset.campaign_key == key,
            MarketingBannerAsset.status == "ready",
            MarketingBannerAsset.is_active.is_(True),
        )
        .order_by(MarketingBannerAsset.version.desc())
        .first()
    )


def _admin_preview_email(db: Session, row: MarketingBannerAsset) -> None:
    recipients = [
        email
        for (email,) in (
            db.query(AdminUser.email)
            .filter(AdminUser.is_active.is_(True))
            .order_by(AdminUser.id.asc())
            .limit(10)
            .all()
        )
        if email
    ]
    if not recipients:
        return
    admin_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/admin/promotions#ai-banners"
    title = "sinh nhật" if row.kind == "birthday" else "sale"
    subject = f"[188.com.vn] Banner {title} {row.date_key} vừa được tạo"
    safe_url = html.escape(row.image_url or "", quote=True)
    body = (
        f"Banner {title} {row.date_key}, giảm {float(row.discount_percent):g}% "
        f"(phiên bản {row.version}) vừa được tạo.\nXem và tạo lại: {admin_url}"
    )
    html_body = (
        f"<p>Banner <strong>{title} {html.escape(row.date_key)}</strong>, "
        f"giảm <strong>{float(row.discount_percent):g}%</strong> vừa được tạo.</p>"
        "<p>Preview desktop:</p>"
        f'<img src="{safe_url}" alt="Desktop preview" style="width:100%;max-width:900px;height:auto">'
        "<p>Preview mobile:</p>"
        f'<img src="{safe_url}" alt="Mobile preview" style="width:360px;max-width:100%;height:auto">'
        f'<p><a href="{html.escape(admin_url, quote=True)}">Xem hoặc tạo lại trong quản trị</a></p>'
    )
    for recipient in recipients:
        try:
            send_email(recipient, subject, body, html_body, prevent_threading=True)
        except Exception:
            logger.exception("Không gửi được email preview banner tới %s", recipient)


def generate_banner(
    db: Session,
    *,
    kind: str,
    day: int,
    month: int,
    discount_percent: float,
    force: bool = False,
    notify_admin: bool = True,
) -> MarketingBannerAsset:
    if kind not in ("sale", "birthday"):
        raise ValueError("kind phải là sale hoặc birthday")
    key = campaign_key(kind, day, month, discount_percent)
    if not force:
        existing = find_active_asset(
            db,
            kind=kind,
            day=day,
            month=month,
            discount_percent=discount_percent,
        )
        if existing:
            return existing

    latest = (
        db.query(MarketingBannerAsset)
        .filter(
            MarketingBannerAsset.kind == kind,
            MarketingBannerAsset.campaign_key == key,
        )
        .order_by(MarketingBannerAsset.version.desc())
        .first()
    )
    version = int(latest.version if latest else 0) + 1
    model = (
        getattr(settings, "IMAGE_LOCALIZATION_GEMINI_IMAGE_MODEL", "")
        or "gemini-3-pro-image-preview"
    ).strip()
    prompt = build_banner_prompt(
        kind=kind,
        day=day,
        month=month,
        discount_percent=discount_percent,
    )
    row = MarketingBannerAsset(
        kind=kind,
        campaign_key=key,
        date_key=f"{month:02d}-{day:02d}",
        discount_percent=discount_percent,
        prompt=prompt,
        model=model,
        version=version,
        status="generating",
        is_active=False,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = (
            db.query(MarketingBannerAsset)
            .filter(
                MarketingBannerAsset.kind == kind,
                MarketingBannerAsset.campaign_key == key,
            )
            .order_by(MarketingBannerAsset.version.desc())
            .first()
        )
        if concurrent:
            return concurrent
        raise
    db.refresh(row)

    try:
        raw = gemini_generate_image_from_text(
            prompt,
            image_model=model,
            image_size="2K",
            aspect_ratio=ASPECT_RATIO,
        )
        width, height, _ = _image_dimensions(raw)
        image_url = _upload_banner(raw, kind=kind, key=key, version=version)
        (
            db.query(MarketingBannerAsset)
            .filter(
                MarketingBannerAsset.kind == kind,
                MarketingBannerAsset.campaign_key == key,
                MarketingBannerAsset.id != row.id,
            )
            .update({"is_active": False}, synchronize_session=False)
        )
        row.image_url = image_url
        row.image_width = width
        row.image_height = height
        row.status = "ready"
        row.is_active = True
        row.generated_at = datetime.now(timezone.utc)
        row.error_message = None
        db.commit()
        db.refresh(row)
        if notify_admin:
            _admin_preview_email(db, row)
        return row
    except Exception as exc:
        row.status = "failed"
        row.error_message = str(exc)[:4000]
        row.is_active = False
        db.commit()
        logger.exception("Tạo banner %s thất bại", key)
        raise


def _birthday_dates_with_customers(db: Session, today: date) -> list[date]:
    targets = [today + timedelta(days=offset) for offset in range(8)]
    clauses = []
    for target in targets:
        clause = (
            (extract("month", User.date_of_birth) == target.month)
            & (extract("day", User.date_of_birth) == target.day)
        )
        if target.month == 2 and target.day == 28 and not calendar.isleap(target.year):
            clause = clause | (
                (extract("month", User.date_of_birth) == 2)
                & (extract("day", User.date_of_birth) == 29)
            )
        clauses.append(clause)
    rows = (
        db.query(User.date_of_birth)
        .filter(
            User.is_active.is_(True),
            User.date_of_birth.isnot(None),
            or_(*clauses),
        )
        .distinct()
        .all()
    )
    present = {(dob.month, dob.day) for (dob,) in rows if dob}
    return [
        target
        for target in targets
        if (target.month, target.day) in present
        or (
            target.month == 2
            and target.day == 28
            and not calendar.isleap(target.year)
            and (2, 29) in present
        )
    ]


def ensure_daily_banners(db: Session, *, today: Optional[date] = None) -> Dict[str, Any]:
    current = today or datetime.now(VN_TZ).date()
    result: Dict[str, Any] = {
        "birthday": {"created": 0, "reused": 0, "failed": 0},
        "sale": {"created": 0, "reused": 0, "failed": 0},
    }

    for target in _birthday_dates_with_customers(db, current):
        existing = find_active_asset(
            db,
            kind="birthday",
            day=target.day,
            month=target.month,
            discount_percent=BIRTHDAY_DISCOUNT_PERCENT,
        )
        if existing:
            result["birthday"]["reused"] += 1
            continue
        try:
            generate_banner(
                db,
                kind="birthday",
                day=target.day,
                month=target.month,
                discount_percent=BIRTHDAY_DISCOUNT_PERCENT,
            )
            result["birthday"]["created"] += 1
        except Exception:
            result["birthday"]["failed"] += 1

    upcoming = list_upcoming_events(db, limit=12)
    matching_event = None
    for event in upcoming:
        event_date = date.fromisoformat(str(event["event_date"])[:10])
        if event_date.day == event_date.month:
            matching_event = (event, event_date)
            break
    if matching_event:
        event, event_date = matching_event
        pct = float(event["discount_percent"])
        existing = find_active_asset(
            db,
            kind="sale",
            day=event_date.day,
            month=event_date.month,
            discount_percent=pct,
        )
        if existing:
            result["sale"]["reused"] += 1
        else:
            try:
                generate_banner(
                    db,
                    kind="sale",
                    day=event_date.day,
                    month=event_date.month,
                    discount_percent=pct,
                )
                result["sale"]["created"] += 1
            except Exception:
                result["sale"]["failed"] += 1
    return result
