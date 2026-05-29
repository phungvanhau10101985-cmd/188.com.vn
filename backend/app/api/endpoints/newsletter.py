import csv
import io
import logging
import re
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user_optional, require_module_permission
from app.crud import newsletter as crud_newsletter
from app.db.session import get_db
from app.models.admin import AdminUser
from app.models.user import User
from app.schemas.email_send_management import EmailSendManagementOut, EmailWarmupSettingsIn
from app.schemas.newsletter import (
    AdminNewsletterCampaignRequest,
    AdminNewsletterCampaignResponse,
    AdminNewsletterImportResponse,
    AdminNewsletterImportTextRequest,
    AdminNewsletterListResponse,
    AdminNewsletterSubscriberOut,
    NewsletterSubscribeRequest,
    NewsletterSubscribeResponse,
)
from app.services.newsletter_import import extract_emails_from_text, extract_emails_from_upload
from app.services.email_normalize import normalize_email_with_fix
logger = logging.getLogger(__name__)

router = APIRouter()

_SUBSCRIBE_COOLDOWN_SEC = 30
_last_subscribe_by_ip: Dict[str, float] = {}


def _client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@router.post("/subscribe", response_model=NewsletterSubscribeResponse)
def subscribe_newsletter(
    body: NewsletterSubscribeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Đăng ký nhận tin từ footer / landing — không cần đăng nhập."""
    ip = _client_ip(request)
    now = time.time()
    last = _last_subscribe_by_ip.get(ip, 0.0)
    if now - last < _SUBSCRIBE_COOLDOWN_SEC:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Vui lòng đợi vài giây trước khi gửi lại.",
        )
    _last_subscribe_by_ip[ip] = now

    email = str(body.email).strip().lower()
    user_id = current_user.id if current_user else None
    row, should_welcome = crud_newsletter.subscribe_email(
        db,
        email=email,
        user_id=user_id,
        source=(body.source or "footer").strip() or "footer",
    )

    if should_welcome:
        try:
            from app.services.email_service import send_newsletter_welcome_email

            if getattr(settings, "NEWSLETTER_WELCOME_EMAIL_ENABLED", True):
                send_newsletter_welcome_email(email)
        except Exception as exc:
            logger.warning("newsletter welcome email failed email=%s: %s", email, exc)

    if should_welcome:
        message = "Cảm ơn bạn! Chúng tôi đã ghi nhận email — hãy kiểm tra hộp thư để nhận tin từ 188.com.vn."
    else:
        message = "Email này đã đăng ký nhận tin. Bạn sẽ tiếp tục nhận ưu đãi từ 188.com.vn."

    logger.info("newsletter subscribe email=%s user_id=%s welcome=%s", email, user_id, should_welcome)
    return NewsletterSubscribeResponse(ok=True, message=message)


@router.get("/admin/subscribers", response_model=AdminNewsletterListResponse)
def admin_list_newsletter_subscribers(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    q: Optional[str] = Query(None, max_length=200),
    active_only: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(require_module_permission("newsletter")),
):
    rows, total, active_total = crud_newsletter.list_subscribers(
        db,
        skip=skip,
        limit=limit,
        q=q,
        active_only=active_only,
    )
    items = [AdminNewsletterSubscriberOut(**crud_newsletter.subscriber_to_admin_dict(r)) for r in rows]
    return AdminNewsletterListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        active_total=active_total,
    )


def _csv_export_rows(
    db: Session,
    *,
    q: Optional[str],
    active_only: Optional[bool],
):
    rows, _total, _active_total = crud_newsletter.list_subscribers(
        db,
        skip=0,
        limit=50_000,
        q=q,
        active_only=active_only,
    )
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "email",
            "user_id",
            "user_full_name",
            "subscriber_name",
            "gender",
            "birthday",
            "phone",
            "email_original",
            "source",
            "is_active",
            "subscribed_at",
            "unsubscribed_at",
            "created_at",
        ]
    )
    for row in rows:
        data = crud_newsletter.subscriber_to_admin_dict(row)
        writer.writerow(
            [
                data["id"],
                data["email"],
                data["user_id"] or "",
                data["user_full_name"] or "",
                data["subscriber_name"] or "",
                data["gender"] or "",
                data["birthday"] or "",
                data["phone"] or "",
                data["email_original"] or "",
                data["source"],
                "1" if data["is_active"] else "0",
                data["subscribed_at"] or "",
                data["unsubscribed_at"] or "",
                data["created_at"] or "",
            ]
        )
    buffer.seek(0)
    return buffer.getvalue()


@router.get("/admin/subscribers/export.csv")
def admin_export_newsletter_subscribers_csv(
    q: Optional[str] = Query(None, max_length=200),
    active_only: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(require_module_permission("newsletter")),
):
    csv_text = _csv_export_rows(db, q=q, active_only=active_only)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"newsletter_subscribers_{stamp}.csv"
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _import_parsed_emails(
    db: Session,
    emails: list[str],
    *,
    source: str,
    raw_line_count: int,
    corrections: list | None = None,
    invalid_rows: list | None = None,
    corrected_count: int = 0,
) -> AdminNewsletterImportResponse:
    result = crud_newsletter.import_emails_bulk(db, emails, source=source)
    parsed = len(emails)
    invalid = max(0, raw_line_count - parsed)
    return AdminNewsletterImportResponse(
        created=result["created"],
        reactivated=result["reactivated"],
        skipped_active=result["skipped_active"],
        invalid=invalid,
        corrected=corrected_count,
        total_input=raw_line_count,
        parsed=parsed,
        corrections=corrections or [],
        invalid_rows=invalid_rows or [],
    )


@router.post("/admin/import-text", response_model=AdminNewsletterImportResponse)
def admin_import_newsletter_text(
    body: AdminNewsletterImportTextRequest,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(require_module_permission("newsletter")),
):
    """Dán danh sách email (mỗi dòng hoặc phân tách bằng dấu phẩy). Tự sửa lỗi gõ nhầm phổ biến."""
    raw_lines = [ln for ln in body.emails_text.replace(",", "\n").splitlines() if ln.strip()]
    emails: list[str] = []
    corrections = []
    invalid_rows = []
    corrected_count = 0
    seen: set[str] = set()

    for i, line in enumerate(raw_lines, start=1):
        for token in re.split(r"\s+", line.strip()):
            fix = normalize_email_with_fix(token)
            if fix.email:
                if fix.email in seen:
                    invalid_rows.append({"row": i, "email": fix.original, "reason": "Email trùng trong danh sách"})
                    continue
                seen.add(fix.email)
                emails.append(fix.email)
                if fix.corrected:
                    corrected_count += 1
                    corrections.append(
                        {
                            "row": i,
                            "original": fix.original,
                            "fixed": fix.email,
                            "fixes": fix.fixes,
                        }
                    )
            elif token.strip():
                invalid_rows.append(
                    {"row": i, "email": fix.original or token.strip(), "reason": fix.invalid_reason or "Không hợp lệ"}
                )

    if not emails:
        raise HTTPException(status_code=400, detail="Không tìm thấy email hợp lệ trong nội dung dán.")
    return _import_parsed_emails(
        db,
        emails,
        source=(body.source or "import").strip() or "import",
        raw_line_count=len(raw_lines),
        corrections=corrections[:100],
        invalid_rows=invalid_rows[:100],
        corrected_count=corrected_count,
    )


@router.post("/admin/import-file", response_model=AdminNewsletterImportResponse)
async def admin_import_newsletter_file(
    file: UploadFile = File(...),
    source: str = Query("import", max_length=50),
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(require_module_permission("newsletter")),
):
    """Import CSV / Excel / TXT — chỉ cột email (marketing). Khách cũ đầy đủ cột → /admin/members."""
    filename = file.filename or ""
    if not filename.lower().endswith((".csv", ".xlsx", ".xls", ".txt")):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ .csv, .xlsx, .xls hoặc .txt")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File trống.")
    try:
        emails = extract_emails_from_upload(filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Không đọc được file: {exc}") from exc
    if not emails:
        raise HTTPException(status_code=400, detail="Không tìm thấy email hợp lệ trong file.")
    raw_line_count = len(emails) if filename.lower().endswith(".txt") else len(emails)
    return _import_parsed_emails(db, emails, source=source.strip() or "import", raw_line_count=raw_line_count)


@router.post("/admin/send-campaign", response_model=AdminNewsletterCampaignResponse)
def admin_send_newsletter_campaign(
    body: AdminNewsletterCampaignRequest,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(require_module_permission("newsletter")),
):
    """Gửi email marketing — test_email = chỉ gửi thử; không set = gửi nền tới mọi email đang active."""
    if not settings.is_smtp_configured():
        raise HTTPException(status_code=503, detail="SMTP chưa cấu hình — không gửi được email.")

    subject = body.subject.strip()
    message = body.message.strip()

    if body.test_email:
        test_to = str(body.test_email).strip().lower()
        try:
            from app.services.email_service import send_marketing_email

            send_marketing_email(test_to, subject=subject, message=message)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Gửi thử thất bại: {exc}") from exc
        return AdminNewsletterCampaignResponse(
            mode="test",
            recipient_count=1,
            sent=1,
            failed=0,
            message=f"Đã gửi email thử tới {test_to}.",
        )

    recipient_count = crud_newsletter.count_active_subscribers(db)
    if recipient_count <= 0:
        raise HTTPException(status_code=400, detail="Chưa có email đang nhận tin — import hoặc chờ khách đăng ký footer.")

    from app.services.newsletter_campaign import get_last_campaign_job, queue_newsletter_campaign

    last = get_last_campaign_job()
    if last and last.get("status") == "running":
        raise HTTPException(status_code=409, detail="Đang có chiến dịch gửi email — vui lòng đợi hoàn tất.")

    queue_newsletter_campaign(subject=subject, message=message)
    return AdminNewsletterCampaignResponse(
        mode="broadcast",
        recipient_count=recipient_count,
        sent=0,
        failed=0,
        message=f"Đã bắt đầu gửi tới {recipient_count} email đang active (chạy nền). Kiểm tra log backend.",
    )


@router.get("/admin/campaign-status")
def admin_newsletter_campaign_status(
    _admin: AdminUser = Depends(require_module_permission("newsletter")),
):
    from app.services.newsletter_campaign import get_last_campaign_job

    job = get_last_campaign_job()
    return job or {"status": "idle"}


@router.get("/admin/email-management", response_model=EmailSendManagementOut)
def admin_email_management_overview(
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(require_module_permission("newsletter")),
):
    """Thống kê gửi mail CMSN + warm-up quota hôm nay."""
    from app.services.email_warmup import management_payload

    return management_payload(db)


@router.put("/admin/warmup-settings", response_model=EmailSendManagementOut)
def admin_update_warmup_settings(
    body: EmailWarmupSettingsIn,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(require_module_permission("newsletter")),
):
    """Cài đặt warm-up: bắt đầu 5 email/ngày, tăng thêm 5 mỗi ngày."""
    from app.services.email_warmup import get_or_create_management, management_payload

    row = get_or_create_management(db)
    row.warmup_enabled = bool(body.warmup_enabled)
    row.start_limit = int(body.start_limit)
    row.daily_increment = int(body.daily_increment)
    row.max_limit = int(body.max_limit) if body.max_limit else None
    row.birthday_cron_enabled = bool(body.birthday_cron_enabled)
    db.commit()
    return management_payload(db)


@router.post("/admin/run-birthday-batch")
def admin_run_birthday_batch(
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(require_module_permission("newsletter")),
):
    """Chạy batch CMSN thủ công (vẫn tôn trọng warm-up quota)."""
    if not settings.is_smtp_configured():
        raise HTTPException(status_code=503, detail="SMTP chưa cấu hình — không gửi được email.")
    from app.services.birthday_promo_jobs import run_birthday_promo_email_batch

    result = run_birthday_promo_email_batch(db, force=True)
    msg_parts = [f"gửi OK {result.get('sent', 0)}"]
    if result.get("skipped"):
        msg_parts.append(f"bỏ qua đã gửi {result['skipped']}")
    if result.get("failed"):
        msg_parts.append(f"lỗi {result['failed']}")
    if result.get("deferred_quota"):
        msg_parts.append(f"chờ quota ngày mai {result['deferred_quota']}")
    return {"ok": result.get("ok", True), "message": " · ".join(msg_parts), **result}