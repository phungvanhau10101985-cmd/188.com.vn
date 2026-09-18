from __future__ import annotations

import base64
import hashlib
import html
import io
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

import requests
from PIL import Image
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.admin import AdminUser
from app.models.marketing_icon import MarketingIconAsset
from app.services.bunny_storage import (
    build_public_object_url,
    delete_bunny_storage_objects_for_urls,
    upload_file_to_zone,
)
from app.services.image_localization_service import (
    _extract_first_image_bytes_from_gemini_generate_response,
    _normalize_gemini_image_size,
    _sanitize_model_id,
)
from app.services.marketing_banner import campaign_key
from app.services.sale_calendar import list_upcoming_events

logger = logging.getLogger(__name__)
VN_TZ = timezone(timedelta(hours=7))
ASPECT_RATIO = "1:1"
ICON_OUTPUT_SIZE = 512
STALE_GENERATING_AFTER = timedelta(minutes=20)
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def default_app_web_icon_url() -> str:
    configured = (getattr(settings, "APP_WEB_ICON_URL", "") or "").strip()
    if configured:
        return configured
    path = (getattr(settings, "APP_WEB_ICON_PATH", "") or "").strip() or (
        "/site/20260502/logo_1x1_0584d3f73e4a.png"
    )
    if not path.startswith("/"):
        path = f"/{path}"
    base = (getattr(settings, "BUNNY_CDN_PUBLIC_BASE", "") or "").rstrip("/")
    if base:
        return f"{base}{path}"
    frontend = (getattr(settings, "FRONTEND_BASE_URL", "") or "").rstrip("/")
    return f"{frontend}/favicon.png" if frontend else path


def _display_pct(value: float) -> str:
    return f"{float(value):g}%"


def build_icon_prompt(
    *,
    day: int,
    month: int,
    discount_percent: float,
    version: int,
) -> str:
    pct = _display_pct(discount_percent)
    return (
        "Chỉnh sửa ảnh logo vuông đang đính kèm — đây là favicon và ảnh đại diện web app "
        "188.com.vn trên điện thoại. Giữ nguyên nhân diện logo gốc: bố cục vuông, màu cam-đỏ-trắng, "
        "khối hình và chữ 188 nếu có. Không vẽ lại thành logo khác, không chữ nhật, không crop lệch. "
        "Tạo icon SALE ngày trùng tháng, tỷ lệ bắt buộc 1:1, chất lượng cao, đọc được khi thu nhỏ 32x32 "
        f"(favicon tab) và 180x180 (avatar web app iOS/Android). "
        f'Bắt buộc ghi rõ, ít chữ, tương phản cao: "SALE {day}.{month}" và "GIẢM {pct}". '
        "Huy hiệu sale nằm góc hoặc vòng quanh logo, không che mất phần nhận diện chính. "
        "Nội dung quan trọng nằm trong 80% giữa (PWA maskable). "
        "Không watermark hãng khác, không tiếng Trung, không thêm % khác. "
        f"Phiên bản sáng tạo {version}."
    )


def _image_square_png(data: bytes, size: int = ICON_OUTPUT_SIZE) -> tuple[bytes, int, int]:
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGBA")
        width, height = image.size
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        image = image.crop((left, top, left + side, top + side))
        if image.size != (size, size):
            image = image.resize((size, size), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        image.save(out, format="PNG", optimize=True)
        return out.getvalue(), size, size


def _guess_mime(url: str, content_type: Optional[str], data: bytes) -> str:
    header = (content_type or "").split(";", 1)[0].strip().lower()
    if header in ("image/png", "image/jpeg", "image/jpg", "image/webp"):
        return "image/jpeg" if header == "image/jpg" else header
    lowered = url.lower().split("?", 1)[0]
    if lowered.endswith(".webp"):
        return "image/webp"
    if lowered.endswith(".jpg") or lowered.endswith(".jpeg"):
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    return "image/png"


def download_source_icon(url: str) -> tuple[bytes, str]:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.content
    if not data:
        raise RuntimeError("Ảnh favicon gốc rỗng.")
    return data, _guess_mime(url, resp.headers.get("Content-Type"), data)


def gemini_edit_square_icon(
    source_bytes: bytes,
    source_mime: str,
    prompt: str,
    *,
    image_model: Optional[str] = None,
) -> bytes:
    api_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if len(api_key) < 10:
        raise RuntimeError("Thiếu GEMINI_API_KEY.")
    dm = (
        (
            image_model
            or getattr(settings, "IMAGE_LOCALIZATION_GEMINI_IMAGE_MODEL", "")
            or "gemini-3-pro-image-preview"
        ).strip()
        or "gemini-3-pro-image-preview"
    )
    model = _sanitize_model_id(dm, "gemini-3-pro-image-preview")
    timeout = max(60, int(getattr(settings, "IMAGE_LOCALIZATION_GEMINI_API_TIMEOUT_SEC", 300) or 300))
    b64 = base64.b64encode(source_bytes).decode("ascii")
    payload: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt.strip()},
                    {"inline_data": {"mime_type": source_mime, "data": b64}},
                ],
            }
        ],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {
                "imageSize": _normalize_gemini_image_size("2K") or "2K",
                "aspectRatio": ASPECT_RATIO,
            },
        },
    }
    url = f"{_GEMINI_BASE}/models/{model}:generateContent"
    res = requests.post(url, params={"key": api_key}, json=payload, timeout=timeout)
    if res.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {res.status_code}: {(res.text or '')[:400]}")
    body = res.json()
    fb = body.get("promptFeedback") or {}
    br = fb.get("blockReason") or fb.get("block_reason")
    if br:
        raise RuntimeError(f"Gemini từ chối prompt: {br}")
    out = _extract_first_image_bytes_from_gemini_generate_response(body)
    if not out:
        raise RuntimeError("Gemini không trả ảnh icon (kiểm tra model sinh ảnh).")
    return out


def _upload_icon(data: bytes, *, key: str, version: int) -> str:
    zone = (getattr(settings, "BUNNY_STORAGE_ZONE_NAME", "") or "").strip()
    access_key = (getattr(settings, "BUNNY_STORAGE_ACCESS_KEY", "") or "").strip()
    public_base = (getattr(settings, "BUNNY_CDN_PUBLIC_BASE", "") or "").strip()
    if not zone or not access_key or not public_base:
        raise RuntimeError("Thiếu cấu hình Bunny Storage/CDN cho icon sale.")
    safe_key = re.sub(r"[^a-zA-Z0-9_-]+", "-", key).strip("-")
    digest = hashlib.sha1(data).hexdigest()[:12]
    prefix = (getattr(settings, "BUNNY_UPLOAD_PATH_PREFIX", "") or "site").strip("/")
    remote_path = (
        f"{prefix}/marketing-icons/sale/{safe_key}/"
        f"v{version}-{int(time.time())}-{digest}.png"
    )
    upload_file_to_zone(
        zone_name=zone,
        access_key=access_key,
        remote_path=remote_path,
        data=data,
        content_type="image/png",
    )
    return build_public_object_url(public_base, remote_path)


def serialize_asset(row: MarketingIconAsset) -> Dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.kind,
        "campaign_key": row.campaign_key,
        "date_key": row.date_key,
        "discount_percent": float(row.discount_percent),
        "image_url": row.image_url,
        "source_image_url": row.source_image_url,
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


def find_active_icon(
    db: Session,
    *,
    day: int,
    month: int,
    discount_percent: float,
    kind: str = "sale",
) -> Optional[MarketingIconAsset]:
    key = campaign_key(kind, day, month, discount_percent)
    return (
        db.query(MarketingIconAsset)
        .filter(
            MarketingIconAsset.kind == kind,
            MarketingIconAsset.campaign_key == key,
            MarketingIconAsset.status == "ready",
            MarketingIconAsset.is_active.is_(True),
        )
        .order_by(MarketingIconAsset.version.desc())
        .first()
    )


def _aware_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_stale_generating(row: MarketingIconAsset) -> bool:
    started = _aware_utc(row.created_at) or _aware_utc(row.updated_at)
    if started is None:
        return True
    return datetime.now(timezone.utc) - started >= STALE_GENERATING_AFTER


def _mark_stale_generating(db: Session, row: MarketingIconAsset) -> None:
    row.status = "failed"
    row.is_active = False
    row.error_message = "Tạo icon bị treo (generating quá hạn)."
    db.commit()


def _find_generating_asset(
    db: Session, *, kind: str, key: str
) -> Optional[MarketingIconAsset]:
    return (
        db.query(MarketingIconAsset)
        .filter(
            MarketingIconAsset.kind == kind,
            MarketingIconAsset.campaign_key == key,
            MarketingIconAsset.status == "generating",
        )
        .order_by(MarketingIconAsset.version.desc())
        .first()
    )


def _delete_superseded_campaign_assets(
    db: Session, *, kind: str, key: str, keep_id: int
) -> None:
    old_rows = (
        db.query(MarketingIconAsset)
        .filter(
            MarketingIconAsset.kind == kind,
            MarketingIconAsset.campaign_key == key,
            MarketingIconAsset.id != keep_id,
        )
        .all()
    )
    if not old_rows:
        return
    urls = [row.image_url for row in old_rows if row.image_url]
    for row in old_rows:
        db.delete(row)
    db.commit()
    if not urls:
        return
    try:
        delete_bunny_storage_objects_for_urls(urls)
    except Exception:
        logger.exception("Không xóa được icon cũ trên CDN cho %s", key)


def _admin_preview_email(db: Session, row: MarketingIconAsset) -> None:
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
    from app.services.email_service import send_email

    admin_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/admin/promotions#ai-icons"
    subject = f"[188.com.vn] Favicon sale {row.date_key} vừa được tạo"
    safe_url = html.escape(row.image_url or "", quote=True)
    body = (
        f"Icon vuông sale {row.date_key}, giảm {float(row.discount_percent):g}% "
        f"(phiên bản {row.version}) vừa được tạo từ favicon gốc.\nXem: {admin_url}"
    )
    html_body = (
        f"<p>Favicon / ảnh đại diện web app <strong>sale {html.escape(row.date_key)}</strong>, "
        f"giảm <strong>{float(row.discount_percent):g}%</strong> vừa được tạo.</p>"
        "<p>Preview vuông:</p>"
        f'<img src="{safe_url}" alt="Sale icon" style="width:180px;height:180px;border-radius:24px">'
        f'<p><a href="{html.escape(admin_url, quote=True)}">Xem hoặc tạo lại trong quản trị</a></p>'
    )
    for recipient in recipients:
        try:
            send_email(recipient, subject, body, html_body, prevent_threading=True)
        except Exception:
            logger.exception("Không gửi được email preview icon tới %s", recipient)


def generate_sale_icon(
    db: Session,
    *,
    day: int,
    month: int,
    discount_percent: float,
    force: bool = False,
    notify_admin: bool = True,
) -> MarketingIconAsset:
    if day != month:
        raise ValueError("Icon sale chỉ áp dụng cho ngày trùng tháng.")
    kind = "sale"
    key = campaign_key(kind, day, month, discount_percent)
    if not force:
        existing = find_active_icon(
            db, day=day, month=month, discount_percent=discount_percent
        )
        if existing:
            return existing
        generating = _find_generating_asset(db, kind=kind, key=key)
        if generating and not _is_stale_generating(generating):
            return generating
        if generating:
            _mark_stale_generating(db, generating)

    latest = (
        db.query(MarketingIconAsset)
        .filter(
            MarketingIconAsset.kind == kind,
            MarketingIconAsset.campaign_key == key,
        )
        .order_by(MarketingIconAsset.version.desc())
        .first()
    )
    version = int(latest.version if latest else 0) + 1
    model = (
        getattr(settings, "IMAGE_LOCALIZATION_GEMINI_IMAGE_MODEL", "")
        or "gemini-3-pro-image-preview"
    ).strip()
    source_url = default_app_web_icon_url()
    prompt = build_icon_prompt(
        day=day,
        month=month,
        discount_percent=discount_percent,
        version=version,
    )
    row = MarketingIconAsset(
        kind=kind,
        campaign_key=key,
        date_key=f"{month:02d}-{day:02d}",
        discount_percent=discount_percent,
        source_image_url=source_url,
        aspect_ratio=ASPECT_RATIO,
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
            db.query(MarketingIconAsset)
            .filter(
                MarketingIconAsset.kind == kind,
                MarketingIconAsset.campaign_key == key,
            )
            .order_by(MarketingIconAsset.version.desc())
            .first()
        )
        if concurrent:
            return concurrent
        raise
    asset_id = int(row.id)

    try:
        source_bytes, source_mime = download_source_icon(source_url)
        raw = gemini_edit_square_icon(source_bytes, source_mime, prompt, image_model=model)
        squared, width, height = _image_square_png(raw)
        image_url = _upload_icon(squared, key=key, version=version)
        row = db.query(MarketingIconAsset).filter(MarketingIconAsset.id == asset_id).one()
        (
            db.query(MarketingIconAsset)
            .filter(
                MarketingIconAsset.kind == kind,
                MarketingIconAsset.campaign_key == key,
                MarketingIconAsset.id != row.id,
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
        _delete_superseded_campaign_assets(db, kind=kind, key=key, keep_id=int(row.id))
        row = db.query(MarketingIconAsset).filter(MarketingIconAsset.id == asset_id).one()
        if notify_admin:
            _admin_preview_email(db, row)
        return row
    except Exception as exc:
        row = db.query(MarketingIconAsset).filter(MarketingIconAsset.id == asset_id).first()
        if row is not None:
            row.status = "failed"
            row.error_message = str(exc)[:4000]
            row.is_active = False
            db.commit()
        logger.exception("Tạo icon sale %s thất bại", key)
        raise


def current_sale_icon_state(
    db: Session,
    *,
    user=None,
) -> Dict[str, Any]:
    from app.services import sale_calendar as sale_svc

    default_url = default_app_web_icon_url()
    sale = sale_svc.resolve_sale_calendar_state(db, user=user)
    payload: Dict[str, Any] = {
        "icon_url": default_url,
        "default_icon_url": default_url,
        "is_sale": False,
        "kind": None,
        "campaign_key": None,
        "date_key": None,
        "discount_percent": None,
        "event_date": None,
        "event_label": sale.event_label,
        "phase": sale.phase,
        "version": None,
    }
    if not (sale.phase and sale.event_date and sale.event_date.day == sale.event_date.month):
        return payload
    row = find_active_icon(
        db,
        day=sale.event_date.day,
        month=sale.event_date.month,
        discount_percent=sale.discount_percent,
    )
    if not row or not row.image_url:
        return payload
    payload.update(
        {
            "icon_url": row.image_url,
            "is_sale": True,
            "kind": "sale",
            "campaign_key": row.campaign_key,
            "date_key": row.date_key,
            "discount_percent": float(row.discount_percent),
            "event_date": sale.event_date.isoformat(),
            "event_label": sale.event_label,
            "phase": sale.phase,
            "version": row.version,
        }
    )
    return payload


def matching_same_day_month_event(db: Session) -> Optional[tuple[int, int, float]]:
    for event in list_upcoming_events(db, limit=24):
        event_date = date.fromisoformat(str(event["event_date"])[:10])
        if event_date.day == event_date.month:
            return event_date.day, event_date.month, float(event["discount_percent"])
    return None


def ensure_daily_sale_icons(
    db: Session,
    *,
    day: Optional[int] = None,
    month: Optional[int] = None,
    discount_percent: Optional[float] = None,
    max_create: int = 1,
    notify_admin: bool = True,
) -> Dict[str, int]:
    stats = {"created": 0, "reused": 0, "failed": 0, "pending": 0, "skipped": 0}
    if day is None or month is None or discount_percent is None:
        match = matching_same_day_month_event(db)
        if not match:
            stats["skipped"] += 1
            return stats
        day, month, discount_percent = match
    pct = float(discount_percent)
    existing = find_active_icon(db, day=day, month=month, discount_percent=pct)
    if existing:
        stats["reused"] += 1
        return stats
    key = campaign_key("sale", day, month, pct)
    generating = _find_generating_asset(db, kind="sale", key=key)
    if generating and not _is_stale_generating(generating):
        stats["pending"] += 1
        return stats
    if generating:
        _mark_stale_generating(db, generating)
    if max_create <= 0:
        stats["pending"] += 1
        return stats
    try:
        row = generate_sale_icon(
            db,
            day=day,
            month=month,
            discount_percent=pct,
            notify_admin=notify_admin,
        )
        if getattr(row, "status", None) == "ready":
            stats["created"] += 1
        else:
            stats["pending"] += 1
    except Exception:
        stats["failed"] += 1
    return stats
