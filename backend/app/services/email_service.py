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


def send_order_received_confirmed_email_task(order_id: int) -> None:
    """Email sau khi khách xác nhận đã nhận hàng — kèm lời nhắc đánh giá nhẹ nhàng."""
    from sqlalchemy.orm import joinedload

    from app.db.session import SessionLocal
    from app.models.order import Order

    db = SessionLocal()
    try:
        order = (
            db.query(Order)
            .options(joinedload(Order.user))
            .filter(Order.id == order_id)
            .first()
        )
        if not order:
            logger.warning("order_received_confirmed_email skip: order not found id=%s", order_id)
            return

        customer_to = (order.customer_email or "").strip()
        if not customer_to and order.user and (order.user.email or "").strip():
            customer_to = (order.user.email or "").strip()
        if not customer_to:
            logger.info("order_received_confirmed_email skip: no email order_id=%s", order_id)
            return

        name = (order.customer_name or "Quý khách").strip()
        code = order.order_code or f"#{order.id}"
        fe = (settings.FRONTEND_BASE_URL or "").strip().rstrip("/")
        review_url = f"{fe}/account/orders/{order.id}/review" if fe else ""
        detail_url = f"{fe}/account/orders/{order.id}" if fe else ""

        subject = f"Đã xác nhận nhận hàng {code} · 188.com.vn"
        if settings.EMAIL_SUBJECT_PREFIX:
            subject = f"{settings.EMAIL_SUBJECT_PREFIX} {subject}"

        review_hint = (
            "Nếu bạn hài lòng với sản phẩm và dịch vụ, rất mong bạn dành chút thời gian "
            "đánh giá đơn hàng — ý kiến của bạn giúp 188.com.vn cải thiện chất lượng "
            "sản phẩm và phục vụ khách hàng tốt hơn mỗi ngày."
        )

        text_lines = [
            f"Kính gửi {name},",
            "",
            "Cảm ơn bạn đã xác nhận nhận hàng.",
            f"Mã đơn hàng: {code}",
            "",
            review_hint,
            *(["", f"Đánh giá đơn hàng: {review_url}"] if review_url else []),
            "",
            "Nếu có vấn đề cần hỗ trợ, vui lòng liên hệ 188.com.vn.",
            *(["", f"Xem chi tiết đơn: {detail_url}"] if detail_url else []),
            "",
            "Trân trọng,",
            "188.com.vn",
        ]
        text_body = "\n".join(text_lines)

        review_html = (
            f'<p><a href="{review_url}">Đánh giá đơn hàng</a></p>' if review_url else ""
        )
        detail_html = (
            f'<p><a href="{detail_url}">Xem chi tiết đơn hàng</a></p>' if detail_url else ""
        )
        html_body = (
            f"<p>Kính gửi <strong>{name}</strong>,</p>"
            "<p>Cảm ơn bạn đã <strong>xác nhận nhận hàng</strong>.</p>"
            f"<p>Mã đơn: <strong>{code}</strong></p>"
            f"<p>{review_hint}</p>"
            f"{review_html}"
            "<p>Nếu có vấn đề cần hỗ trợ, vui lòng liên hệ <strong>188.com.vn</strong>.</p>"
            f"{detail_html}"
            "<p>Trân trọng,<br>188.com.vn</p>"
        )

        send_email(customer_to, subject, text_body, html_body)
        logger.info("order_received_confirmed_email sent order_id=%s to=%s", order_id, customer_to)
    except Exception:
        logger.exception("order_received_confirmed_email failed order_id=%s", order_id)
    finally:
        db.close()


def send_order_created_email_task(order_id: int) -> None:
    """Email xác nhận đơn mới — kèm QR + nhắc đặt cọc nếu đơn chờ cọc."""
    from sqlalchemy.orm import joinedload

    from app.db.session import SessionLocal
    from app.models.order import Order, OrderStatus
    from app.services import sepay as sepay_svc

    db = SessionLocal()
    try:
        order = (
            db.query(Order)
            .options(joinedload(Order.user))
            .filter(Order.id == order_id)
            .first()
        )
        if not order:
            logger.warning("order_created_email skip: order not found id=%s", order_id)
            return

        customer_to = (order.customer_email or "").strip()
        if not customer_to and order.user and (order.user.email or "").strip():
            customer_to = (order.user.email or "").strip()
        if not customer_to:
            logger.info("order_created_email skip: no email order_id=%s", order_id)
            return

        name = (order.customer_name or "Quý khách").strip()
        code = order.order_code or f"#{order.id}"
        fe = (settings.FRONTEND_BASE_URL or "").strip().rstrip("/")
        detail_url = f"{fe}/account/orders/{order.id}" if fe else ""
        deposit_url = f"{fe}/account/orders/{order.id}/deposit" if fe else ""

        status_val = getattr(order.status, "value", order.status)
        waiting_deposit = bool(order.requires_deposit and status_val == OrderStatus.WAITING_DEPOSIT.value)

        if waiting_deposit:
            deposit_vnd = _format_vnd_plain(order.deposit_amount)
            remaining_vnd = _format_vnd_plain(order.remaining_amount)
            transfer_content = sepay_svc.build_transfer_content_for_order(order)
            qr_url = sepay_svc.resolve_deposit_qr_image_url(db, order)

            subject = f"Đặt cọc đơn {code} để giao hàng sớm · 188.com.vn"
            if settings.EMAIL_SUBJECT_PREFIX:
                subject = f"{settings.EMAIL_SUBJECT_PREFIX} {subject}"

            gentle = (
                "Đơn của bạn đã được tạo thành công. "
                "Để shop xử lý và giao hàng sớm nhất, bạn vui lòng chuyển khoản đặt cọc trong thời gian sớm nhất nhé."
            )

            text_lines = [
                f"Kính gửi {name},",
                "",
                gentle,
                "",
                f"Mã đơn hàng: {code}",
                f"Số tiền cọc: {deposit_vnd} VND",
                f"Còn lại khi nhận hàng: {remaining_vnd} VND",
                f"Nội dung chuyển khoản: {transfer_content}",
                "",
                "Quét mã QR trong email hoặc mở trang đặt cọc để thanh toán.",
            ]
            if deposit_url:
                text_lines.extend(["", f"Đặt cọc ngay: {deposit_url}"])
            if detail_url:
                text_lines.extend(["", f"Chi tiết đơn: {detail_url}"])
            text_lines.extend(["", "Trân trọng,", "188.com.vn"])
            text_body = "\n".join(text_lines)

            qr_html = (
                f'<p style="text-align:center;margin:16px 0;">'
                f'<img src="{qr_url}" alt="Mã QR chuyển khoản" width="240" height="240" '
                f'style="max-width:240px;height:auto;border:1px solid #e5e7eb;border-radius:12px;" />'
                f"</p>"
                if qr_url
                else ""
            )
            cta_html = ""
            if deposit_url:
                cta_html = (
                    f'<p style="margin:20px 0 12px;text-align:center;">'
                    f'<a href="{deposit_url}" style="display:inline-block;padding:12px 22px;'
                    f'background:#ea580c;color:#ffffff !important;text-decoration:none;border-radius:10px;font-weight:600;">'
                    f"Đặt cọc ngay</a></p>"
                )
            link_html = (
                f'<p style="font-size:13px;color:#6b7280;text-align:center;">'
                f'<a href="{detail_url}">Xem chi tiết đơn hàng</a></p>'
                if detail_url
                else ""
            )

            html_body = f"""
<div style="font-family:system-ui,-apple-system,'Segoe UI',sans-serif;font-size:15px;line-height:1.55;color:#111827;max-width:560px;">
  <p>Kính gửi <strong>{name}</strong>,</p>
  <p>{gentle}</p>
  <p>Mã đơn: <strong>{code}</strong><br/>
  Số tiền cọc: <strong>{deposit_vnd} VND</strong><br/>
  Còn lại khi nhận hàng: <strong>{remaining_vnd} VND</strong></p>
  <p style="background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;padding:12px 14px;font-size:14px;">
    <strong>Nội dung CK:</strong> <span style="font-family:monospace;">{transfer_content}</span><br/>
    <span style="color:#9a3412;font-size:13px;">Ghi đúng nội dung để hệ thống xác nhận tự động.</span>
  </p>
  {qr_html}
  {cta_html}
  {link_html}
  <p style="margin-top:24px;">Trân trọng,<br/>188.com.vn</p>
</div>
"""
        else:
            subject = f"Xác nhận đơn hàng {code} · 188.com.vn"
            if settings.EMAIL_SUBJECT_PREFIX:
                subject = f"{settings.EMAIL_SUBJECT_PREFIX} {subject}"
            text_body = "\n".join(
                [
                    f"Kính gửi {name},",
                    "",
                    "Đơn hàng của bạn đã được tạo thành công. Cảm ơn bạn đã mua sắm tại 188.com.vn.",
                    *(["", f"Chi tiết đơn: {detail_url}"] if detail_url else []),
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
                "<p>Đơn hàng của bạn đã được tạo thành công. Cảm ơn bạn đã mua sắm tại 188.com.vn.</p>"
                f"{link_html}"
                "<p>Trân trọng,<br>188.com.vn</p>"
            )

        send_email(customer_to, subject, text_body, html_body)
        logger.info("order_created_email sent order_id=%s to=%s waiting_deposit=%s", order_id, customer_to, waiting_deposit)
    except Exception:
        logger.exception("order_created_email failed order_id=%s", order_id)
    finally:
        db.close()


def send_birthday_promo_email(
    to_email: str,
    customer_name: str,
    percent: int,
    next_birthday_label: str,
    website_url: str,
) -> None:
    display_name = (customer_name or "bạn").strip() or "bạn"
    origin = website_url.rstrip("/")
    subject = f"188.com.vn - Ưu đãi sinh nhật {percent}% dành cho {display_name}"
    text_body = (
        f"Xin chào {display_name},\n\n"
        f"Tuần lễ sinh nhật của bạn đã bắt đầu. 188.com.vn gửi tặng ưu đãi {percent}% "
        "tự động trên giá sản phẩm khi bạn đăng nhập và mua hàng trên web, không cần mã.\n"
        f"Sinh nhật sắp tới: {next_birthday_label}.\n\n"
        f"Mua sắm ngay: {origin}\n\n"
        "Trân trọng,\n188.com.vn\n"
        f"--\nTin nhắn tự động từ 188.com.vn · {origin}"
    )
    html_body = f"""
<div style="font-family:system-ui,-apple-system,'Segoe UI',sans-serif;font-size:15px;line-height:1.55;color:#111827;max-width:560px;">
  <p>Xin chào <strong>{display_name}</strong>,</p>
  <p>Tuần lễ sinh nhật của bạn đã bắt đầu. 188.com.vn gửi tặng ưu đãi <strong>{percent}%</strong> tự động trên giá sản phẩm khi bạn đăng nhập và mua hàng trên web, không cần mã.</p>
  <p style="color:#4b5563;font-size:14px;">Sinh nhật sắp tới: {next_birthday_label}.</p>
  <p style="margin:20px 0 12px;"><a href="{origin}" style="display:inline-block;padding:12px 22px;background:#ea580c;color:#ffffff !important;text-decoration:none;border-radius:10px;font-weight:600;">Vào web xem giá ưu đãi</a></p>
  <p style="font-size:12px;color:#6b7280;word-break:break-all;">Hoặc sao chép liên kết: <a href="{origin}">{origin}</a></p>
  <p style="margin-top:24px;">Trân trọng,<br/>188.com.vn</p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;" />
  <p style="font-size:12px;color:#9ca3af;">Tin nhắn tự động từ 188.com.vn</p>
</div>
"""
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


def send_bank_account_otp_email(to_email: str, code: str, expire_minutes: int) -> None:
    subject = "Mã xác minh tài khoản ngân hàng 188.com.vn"
    if settings.EMAIL_SUBJECT_PREFIX:
        subject = f"{settings.EMAIL_SUBJECT_PREFIX} {subject}"
    text_body = (
        "Bạn đang thêm hoặc thay đổi tài khoản ngân hàng nhận tiền affiliate.\n\n"
        f"Mã xác minh của bạn: {code}\n"
        f"Mã có hiệu lực {expire_minutes} phút.\n\n"
        "Nếu bạn không thực hiện thao tác này, vui lòng bỏ qua email và liên hệ shop."
    )
    html_body = (
        "<p>Bạn đang thêm hoặc thay đổi <strong>tài khoản ngân hàng nhận tiền affiliate</strong>.</p>"
        f"<p>Mã xác minh: <strong style=\"font-size:22px;letter-spacing:4px;\">{code}</strong></p>"
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
