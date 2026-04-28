import logging
import smtplib
import ssl
from decimal import Decimal
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_from_header() -> Optional[str]:
    """Chuỗi From: ưu tiên SMTP_FROM (dạng nodemailer), sau đó SENDER_NAME + email."""
    s = (settings.SMTP_FROM or "").strip()
    if s:
        return s
    from_addr = (settings.SENDER_EMAIL or settings.EMAIL_FROM or "").strip()
    if not from_addr:
        return None
    if settings.SENDER_NAME:
        return formataddr((settings.SENDER_NAME, from_addr))
    return from_addr


def _connect_smtp() -> smtplib.SMTP:
    """
    Tương tự nodemailer: secure true hoặc port 465 => SMTP_SSL;
    ngược lại: SMTP rồi (tuỳ chọn) STARTTLS nếu EMAIL_USE_TLS.
    """
    ctx = ssl.create_default_context()
    host = settings.SMTP_HOST
    port = settings.SMTP_PORT

    if settings.SMTP_USE_IMPLICIT_SSL:
        return smtplib.SMTP_SSL(host, port, context=ctx, timeout=10)

    server = smtplib.SMTP(host, port, timeout=10)
    if settings.EMAIL_USE_TLS:
        try:
            server.ehlo()
        except smtplib.SMTPException:
            pass
        server.starttls(context=ctx)
        try:
            server.ehlo()
        except smtplib.SMTPException:
            pass
    return server


def send_email(to_email: str, subject: str, text_body: str, html_body: Optional[str] = None) -> None:
    if not to_email:
        return
    if not settings.is_smtp_configured():
        return

    from_header = _build_from_header()
    if not from_header:
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_header
    if settings.REPLY_TO:
        msg["Reply-To"] = settings.REPLY_TO
    msg["To"] = to_email
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    with _connect_smtp() as server:
        server.login(settings.SMTP_USER, settings.SMTP_PASS)
        server.send_message(msg)


def send_account_email(to_email: str, subject: str, message: str) -> None:
    text_body = message
    html_body = f"<p>{message}</p>"
    send_email(to_email, subject, text_body, html_body)


def send_order_email(to_email: str, subject: str, message: str) -> None:
    text_body = message
    html_body = f"<p>{message}</p>"
    send_email(to_email, subject, text_body, html_body)


def _format_vnd_plain(n) -> str:
    try:
        x = int(Decimal(str(n)))
        return f"{x:,}".replace(",", ".")
    except Exception:
        return str(n)


def send_deposit_confirmed_email_task(order_id: int) -> None:
    """
    BackgroundTasks: email khách (đơn + tài khoản), email cảnh báo shop, thông báo in-app.
    """
    from sqlalchemy.orm import joinedload

    from app.crud import notification as crud_notification
    from app.db.session import SessionLocal
    from app.models.order import Order, OrderStatus
    from app.schemas.notification import NotificationCreate

    db = SessionLocal()
    try:
        order = (
            db.query(Order)
            .options(joinedload(Order.user))
            .filter(Order.id == order_id)
            .first()
        )
        if not order:
            logger.warning("deposit_notification skip: order not found id=%s", order_id)
            return
        st = getattr(order.status, "value", order.status)
        if st not in (OrderStatus.DEPOSIT_PAID.value, OrderStatus.CONFIRMED.value):
            logger.info("deposit_notification skip: wrong status order_id=%s status=%s", order_id, st)
            return

        name = (order.customer_name or "Quý khách").strip()
        code = order.order_code
        amt = order.deposit_paid or order.deposit_amount or 0
        vnd = _format_vnd_plain(amt)
        fe = (settings.FRONTEND_BASE_URL or "").strip().rstrip("/")
        detail_url = f"{fe}/account/orders/{order.id}" if fe else ""
        phone = (order.customer_phone or "").strip()

        if st == OrderStatus.CONFIRMED.value:
            status_msg = (
                "Đơn hàng đã được xác nhận (cọc 100%). Chúng tôi sẽ xử lý và giao hàng "
                "theo thông tin bạn đã cung cấp."
            )
            status_short = "Đã xác nhận (cọc 100%)"
        else:
            status_msg = (
                "Hệ thống đã ghi nhận khoản đặt cọc. Đơn chuyển sang trạng thái «Đã đặt cọc». "
                "Chúng tôi sẽ liên hệ khi chuẩn bị gửi hàng. Phần còn lại thanh toán khi nhận hàng."
            )
            status_short = "Đã đặt cọc"

        customer_to = (order.customer_email or "").strip()
        if not customer_to and order.user and (order.user.email or "").strip():
            customer_to = (order.user.email or "").strip()
            logger.info("deposit_confirmed_email using account email order_id=%s", order_id)

        subject = f"Đã nhận cọc đơn {code} — Cảm ơn quý khách · 188.com.vn"
        if settings.EMAIL_SUBJECT_PREFIX:
            subject = f"{settings.EMAIL_SUBJECT_PREFIX} {subject}"

        text_body = "\n".join(
            [
                f"Kính gửi {name},",
                "",
                "Cảm ơn quý khách đã thanh toán đặt cọc.",
                f"Mã đơn hàng: {code}",
                f"Số tiền cọc đã nhận: {vnd} VND",
                "",
                status_msg,
                *(["", f"Xem chi tiết đơn hàng: {detail_url}"] if detail_url else []),
                "",
                "Trân trọng,",
                "188.com.vn",
            ]
        )
        link_html = (
            f'<p><a href="{detail_url}">Xem chi tiết đơn hàng</a></p>' if detail_url else ""
        )
        html_body = (
            f"<p>Kính gửi <strong>{name}</strong>,</p>"
            "<p>Cảm ơn quý khách đã <strong>thanh toán đặt cọc</strong>.</p>"
            f"<p>Mã đơn: <strong>{code}</strong><br>"
            f"Số tiền cọc: <strong>{vnd} VND</strong></p>"
            f"<p>{status_msg}</p>"
            f"{link_html}"
            "<p>Trân trọng,<br>188.com.vn</p>"
        )

        if customer_to:
            try:
                send_email(customer_to, subject, text_body, html_body)
                logger.info("deposit_confirmed_email sent order_id=%s to=%s", order_id, customer_to)
            except Exception:
                logger.exception("deposit_confirmed_email failed order_id=%s to=%s", order_id, customer_to)
        else:
            logger.info(
                "deposit_confirmed_email skip: no customer_email or user.email order_id=%s",
                order_id,
            )

        alert_emails = list(getattr(settings, "ORDER_DEPOSIT_ALERT_EMAILS", []) or [])
        if alert_emails and settings.is_smtp_configured():
            shop_subj = f"[Shop] Đã nhận cọc đơn {code} — {vnd} VND"
            if settings.EMAIL_SUBJECT_PREFIX:
                shop_subj = f"{settings.EMAIL_SUBJECT_PREFIX} {shop_subj}"
            shop_text = "\n".join(
                [
                    "Hệ thống vừa ghi nhận đặt cọc thành công.",
                    f"Mã đơn: {code}",
                    f"Khách: {name}" + (f" — SĐT: {phone}" if phone else ""),
                    f"Số tiền cọc: {vnd} VND",
                    f"Trạng thái đơn: {status_short}",
                    *(["", f"Chi tiết: {detail_url}"] if detail_url else ["", f"Đơn ID: {order.id}"]),
                ]
            )
            shop_html = (
                f"<p><strong>Đã nhận cọc</strong> — đơn <strong>{code}</strong></p>"
                f"<p>Khách: {name}" + (f" — {phone}</p>" if phone else "</p>")
                + f"<p>Số tiền: <strong>{vnd} VND</strong><br>Trạng thái: {status_short}</p>"
                + (f'<p><a href="{detail_url}">Mở đơn (khách)</a></p>' if detail_url else "")
            )
            for addr in alert_emails:
                try:
                    send_email(addr.strip(), shop_subj, shop_text, shop_html)
                    logger.info("deposit_shop_alert sent order_id=%s to=%s", order_id, addr)
                except Exception:
                    logger.exception("deposit_shop_alert failed order_id=%s to=%s", order_id, addr)

        if order.user_id:
            try:
                crud_notification.create_notification(
                    db,
                    NotificationCreate(
                        user_id=order.user_id,
                        title="Đã nhận đặt cọc",
                        content=f"Đơn {code}: xác nhận thanh toán cọc {vnd} VND. {status_short}.",
                        type="order",
                    ),
                )
                logger.info(
                    "deposit_inapp_notification created order_id=%s user_id=%s",
                    order_id,
                    order.user_id,
                )
            except Exception:
                logger.exception(
                    "deposit_inapp_notification failed order_id=%s user_id=%s",
                    order_id,
                    order.user_id,
                )
    except Exception:
        logger.exception("send_deposit_confirmed_email_task failed order_id=%s", order_id)
    finally:
        db.close()


def send_login_otp_email(to_email: str, code: str, expire_minutes: int) -> None:
    subject = "Mã đăng nhập 188.com.vn"
    if settings.EMAIL_SUBJECT_PREFIX:
        subject = f"{settings.EMAIL_SUBJECT_PREFIX} {subject}"
    text_body = f"Mã đăng nhập của bạn: {code}. Có hiệu lực {expire_minutes} phút. Không chia sẻ mã cho người khác."
    html_body = (
        f"<p>Mã đăng nhập: <strong style=\"font-size:18px;letter-spacing:2px;\">{code}</strong></p>"
        f"<p>Hiệu lực {expire_minutes} phút. Nếu bạn không yêu cầu mã, hãy bỏ qua email này.</p>"
    )
    send_email(to_email, subject, text_body, html_body)


def send_login_magic_link_email(to_email: str, magic_url: str, expire_minutes: int) -> None:
    subject = "Đăng nhập 188.com.vn (liên kết nhanh)"
    if settings.EMAIL_SUBJECT_PREFIX:
        subject = f"{settings.EMAIL_SUBJECT_PREFIX} {subject}"
    text_body = (
        f"Bấm liên kết sau để đăng nhập (hiệu lực {expire_minutes} phút):\n{magic_url}\n\n"
        "Nếu bạn không yêu cầu, hãy bỏ qua email này."
    )
    html_body = (
        f"<p>Đăng nhập một chạm (hiệu lực {expire_minutes} phút):</p>"
        f"<p><a href=\"{magic_url}\">Đăng nhập 188.com.vn</a></p>"
        "<p>Nếu bạn không yêu cầu, hãy bỏ qua email này.</p>"
    )
    send_email(to_email, subject, text_body, html_body)
