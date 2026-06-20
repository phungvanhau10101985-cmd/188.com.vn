import html
import logging
import smtplib
import ssl
import threading
import time
from decimal import Decimal
from email.message import EmailMessage
from email.utils import formataddr
from typing import List, Optional, TYPE_CHECKING, TypedDict

from app.core.config import settings

if TYPE_CHECKING:
    from app.models.cart import Cart

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


def _smtp_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if not getattr(settings, "SMTP_SSL_VERIFY", True):
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        logger.warning(
            "SMTP_SSL_VERIFY=false — bỏ qua xác minh chứng chỉ SSL (chỉ nên dùng dev/local)"
        )
    return ctx


def _connect_smtp() -> smtplib.SMTP:
    """
    Tương tự nodemailer: secure true hoặc port 465 => SMTP_SSL;
    ngược lại: SMTP rồi (tuỳ chọn) STARTTLS nếu EMAIL_USE_TLS.
    """
    ctx = _smtp_ssl_context()
    host = settings.SMTP_HOST
    port = settings.SMTP_PORT

    if settings.SMTP_USE_IMPLICIT_SSL:
        return smtplib.SMTP_SSL(host, port, context=ctx, timeout=25)

    server = smtplib.SMTP(host, port, timeout=25)
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


def send_email(
    to_email: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    *,
    extra_headers: Optional[dict[str, str]] = None,
    prevent_threading: bool = False,
) -> bool:
    """Trả True nếu đã gửi SMTP; False nếu bỏ qua (cấu hình thiếu / không có người nhận)."""
    from email.utils import make_msgid

    recipient = (to_email or "").strip()
    if not recipient:
        logger.warning("send_email skip: empty recipient")
        return False
    if not settings.is_smtp_configured():
        logger.warning(
            "send_email skip: SMTP not configured (need SMTP_HOST, SMTP_USER, SMTP_PASS, SMTP_FROM or SENDER_EMAIL)"
        )
        return False

    from_header = _build_from_header()
    if not from_header:
        logger.warning("send_email skip: no From address configured")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_header
    domain = "188.com.vn"
    if "@" in from_header:
        parsed = from_header.rsplit("@", 1)[-1].strip().strip(">")
        if parsed:
            domain = parsed
    msg["Message-ID"] = make_msgid(domain=domain)
    if prevent_threading:
        # Không set In-Reply-To / References — mỗi thông báo là email độc lập.
        msg["X-Entity-Ref-ID"] = make_msgid(domain=domain).strip("<>")
    if extra_headers:
        for key, value in extra_headers.items():
            if key and value:
                msg[key] = value
    if settings.REPLY_TO:
        msg["Reply-To"] = settings.REPLY_TO
    msg["To"] = recipient
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    with _connect_smtp() as server:
        server.login(settings.SMTP_USER, settings.SMTP_PASS)
        server.send_message(msg)
    return True


def send_account_email(to_email: str, subject: str, message: str) -> None:
    text_body = message
    html_body = f"<p>{message}</p>"
    send_email(to_email, subject, text_body, html_body)


def send_order_email(to_email: str, subject: str, message: str) -> None:
    text_body = message
    html_body = f"<p>{message}</p>"
    send_email(to_email, subject, text_body, html_body)


def send_order_delivered_email_task(order_id: int, *, source: str = "customer_confirm") -> None:
    """
    Một email duy nhất: thông báo giao hàng + mời đánh giá.
    source: customer_confirm (khách bấm xác nhận) | ems_auto (EMS báo giao thành công)
    """
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
            logger.warning("order_delivered_email skip: order not found id=%s", order_id)
            return

        customer_to = (order.customer_email or "").strip()
        if not customer_to and order.user and (order.user.email or "").strip():
            customer_to = (order.user.email or "").strip()
        if not customer_to:
            logger.info("order_delivered_email skip: no email order_id=%s", order_id)
            return

        name = (order.customer_name or "Quý khách").strip()
        code = order.order_code or f"#{order.id}"
        tracking = (order.tracking_number or "").strip()
        provider = (order.shipping_provider or "").strip()
        fe = (settings.FRONTEND_BASE_URL or "").strip().rstrip("/")
        review_url = f"{fe}/account/orders/{order.id}/review" if fe else ""
        detail_url = f"{fe}/account/orders/{order.id}" if fe else ""
        tracking_url = f"{fe}/account/orders/{order.id}/tracking" if fe else ""

        if source == "ems_auto":
            intro = "Đơn hàng của bạn đã được EMS giao thành công."
            subject = f"Đã giao hàng thành công {code} · 188.com.vn"
        else:
            intro = "Cảm ơn bạn đã xác nhận nhận hàng."
            subject = f"Đã giao hàng {code} · 188.com.vn"

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
            intro,
            f"Mã đơn hàng: {code}",
        ]
        if tracking:
            ship_line = f"Mã vận đơn: {tracking}"
            if provider:
                ship_line += f" ({provider})"
            text_lines.append(ship_line)
        text_lines.extend(
            [
                "",
                review_hint,
                *(["", f"Đánh giá đơn hàng: {review_url}"] if review_url else []),
                "",
                "Nếu có vấn đề cần hỗ trợ, vui lòng liên hệ 188.com.vn.",
                *(["", f"Xem chi tiết đơn: {detail_url}"] if detail_url else []),
                *(
                    ["", f"Theo dõi vận chuyển: {tracking_url}"]
                    if tracking_url and tracking
                    else []
                ),
                "",
                "Trân trọng,",
                "188.com.vn",
            ]
        )
        text_body = "\n".join(text_lines)

        tracking_html = ""
        if tracking:
            tracking_html = f"<p>Mã vận đơn: <strong>{tracking}</strong>"
            if provider:
                tracking_html += f" ({provider})"
            tracking_html += "</p>"

        review_html = (
            f'<p><a href="{review_url}">Đánh giá đơn hàng</a></p>' if review_url else ""
        )
        detail_html = (
            f'<p><a href="{detail_url}">Xem chi tiết đơn hàng</a></p>' if detail_url else ""
        )
        track_link_html = (
            f'<p><a href="{tracking_url}">Theo dõi vận chuyển</a></p>'
            if tracking_url and tracking
            else ""
        )
        html_body = (
            f"<p>Kính gửi <strong>{name}</strong>,</p>"
            f"<p>{intro}</p>"
            f"<p>Mã đơn: <strong>{code}</strong></p>"
            f"{tracking_html}"
            f"<p>{review_hint}</p>"
            f"{review_html}"
            "<p>Nếu có vấn đề cần hỗ trợ, vui lòng liên hệ <strong>188.com.vn</strong>.</p>"
            f"{detail_html}"
            f"{track_link_html}"
            "<p>Trân trọng,<br>188.com.vn</p>"
        )

        send_email(customer_to, subject, text_body, html_body)
        logger.info(
            "order_delivered_email sent order_id=%s to=%s source=%s",
            order_id,
            customer_to,
            source,
        )
    except Exception:
        logger.exception("order_delivered_email failed order_id=%s source=%s", order_id, source)
    finally:
        db.close()


def send_order_received_confirmed_email_task(order_id: int) -> None:
    """Alias — gửi email giao hàng + nhắc đánh giá sau khi khách xác nhận nhận hàng."""
    send_order_delivered_email_task(order_id, source="customer_confirm")


def send_order_shipper_confirmed_email_task(order_id: int) -> None:
    """Email khi shop đóng hàng & gửi shipper — kèm link đơn và nhắc đánh giá sau khi nhận."""
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
            logger.warning("order_shipper_confirmed_email skip: order not found id=%s", order_id)
            return

        customer_to = (order.customer_email or "").strip()
        if not customer_to and order.user and (order.user.email or "").strip():
            customer_to = (order.user.email or "").strip()
        if not customer_to:
            logger.info("order_shipper_confirmed_email skip: no email order_id=%s", order_id)
            return

        name = (order.customer_name or "Quý khách").strip()
        code = order.order_code or f"#{order.id}"
        tracking = (order.tracking_number or "").strip()
        provider = (order.shipping_provider or "").strip()
        fe = (settings.FRONTEND_BASE_URL or "").strip().rstrip("/")
        detail_url = f"{fe}/account/orders/{order.id}" if fe else ""
        tracking_url = f"{fe}/account/orders/{order.id}/tracking" if fe else ""

        subject = f"Đơn {code} đã gửi shipper · 188.com.vn"
        if settings.EMAIL_SUBJECT_PREFIX:
            subject = f"{settings.EMAIL_SUBJECT_PREFIX} {subject}"

        review_hint = (
            "Khi nhận đủ hàng, vui lòng bấm «Đã nhận hàng» trên trang đơn. "
            "Nếu bạn hài lòng với sản phẩm và dịch vụ, rất mong bạn dành chút thời gian "
            "đánh giá — ý kiến của bạn giúp 188.com.vn nâng cao chất lượng và phục vụ khách hàng tốt hơn."
        )

        text_lines = [
            f"Kính gửi {name},",
            "",
            "188.com.vn đã đóng hàng và gửi cho shipper giao đến bạn.",
            f"Mã đơn hàng: {code}",
        ]
        if tracking:
            ship_line = f"Mã vận đơn: {tracking}"
            if provider:
                ship_line += f" ({provider})"
            text_lines.append(ship_line)
        text_lines.extend(
            [
                "",
                review_hint,
                *(["", f"Xem đơn hàng: {detail_url}"] if detail_url else []),
                *(["", f"Theo dõi vận chuyển: {tracking_url}"] if tracking_url and tracking else []),
                "",
                "Trân trọng,",
                "188.com.vn",
            ]
        )
        text_body = "\n".join(text_lines)

        tracking_html = ""
        if tracking:
            tracking_html = f"<p>Mã vận đơn: <strong>{tracking}</strong>"
            if provider:
                tracking_html += f" ({provider})"
            tracking_html += "</p>"

        detail_html = (
            f'<p><a href="{detail_url}">Xem chi tiết đơn hàng</a></p>' if detail_url else ""
        )
        track_link_html = (
            f'<p><a href="{tracking_url}">Theo dõi vận chuyển</a></p>'
            if tracking_url and tracking
            else ""
        )
        html_body = (
            f"<p>Kính gửi <strong>{name}</strong>,</p>"
            "<p>188.com.vn đã <strong>đóng hàng và gửi shipper</strong> giao đến bạn.</p>"
            f"<p>Mã đơn: <strong>{code}</strong></p>"
            f"{tracking_html}"
            f"<p>{review_hint}</p>"
            f"{detail_html}"
            f"{track_link_html}"
            "<p>Trân trọng,<br>188.com.vn</p>"
        )

        send_email(customer_to, subject, text_body, html_body)
        logger.info("order_shipper_confirmed_email sent order_id=%s to=%s", order_id, customer_to)
    except Exception:
        logger.exception("order_shipper_confirmed_email failed order_id=%s", order_id)
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


def _frontend_origin() -> str:
    fe = (settings.FRONTEND_BASE_URL or settings.WEBSITE_URL or "").strip().rstrip("/")
    return fe or "https://188.com.vn"


def _cart_item_summary_lines(cart: "Cart", *, max_items: int = 5) -> List[str]:
    lines: List[str] = []
    items = list(cart.items or [])
    for item in items[:max_items]:
        name = (getattr(item, "product_name", None) or "").strip()
        if not name:
            pdata = getattr(item, "product_data", None) or {}
            if isinstance(pdata, dict):
                name = (
                    str(pdata.get("name") or pdata.get("product_name") or pdata.get("title") or "")
                ).strip()
        if not name:
            name = "Sản phẩm"
        qty = int(getattr(item, "quantity", None) or 1)
        lines.append(f"{name} × {qty}")
    extra = len(items) - max_items
    if extra > 0:
        lines.append(f"... và {extra} sản phẩm khác")
    return lines


def send_cart_abandon_email(
    to_email: str,
    *,
    customer_name: str,
    cart: "Cart",
    promo_code: str,
    discount_percent: int,
    max_discount_amount: int,
    valid_days: int,
) -> None:
    """Email nhắc giỏ bỏ dở — CTA mở /cart nhanh + mã ưu đãi trong ví."""
    if not to_email or not settings.is_smtp_configured():
        return
    if not getattr(settings, "CART_ABANDON_EMAIL_ENABLED", True):
        return

    origin = _frontend_origin()
    cart_url = f"{origin}/cart"
    wallet_url = f"{origin}/account/khuyen-mai"
    display_name = (customer_name or "Quý khách").strip() or "Quý khách"
    item_lines = _cart_item_summary_lines(cart)
    max_discount_label = _format_vnd_plain(max_discount_amount) if max_discount_amount else "0"

    subject = "Bạn còn sản phẩm trong giỏ — hoàn tất đơn tại 188.com.vn"
    items_text = "\n".join(f"  • {line}" for line in item_lines) if item_lines else "  • (xem chi tiết trên giỏ hàng)"
    text_body = (
        f"Xin chào {display_name},\n\n"
        "Bạn còn sản phẩm trong giỏ hàng nhưng chưa hoàn tất đặt hàng.\n\n"
        f"{items_text}\n\n"
        f"Shop tặng thêm mã {promo_code} — giảm {discount_percent}% "
        f"(tối đa {max_discount_label}đ, hết hạn sau {valid_days} ngày). "
        f"Mã đã có trong ví khuyến mãi của bạn.\n\n"
        f"Xem giỏ hàng và đặt hàng ngay: {cart_url}\n"
        f"Ví mã ưu đãi: {wallet_url}\n\n"
        "Trân trọng,\n188.com.vn\n"
        f"--\nTin nhắn tự động từ 188.com.vn · {origin}"
    )

    items_html = ""
    if item_lines:
        lis = "".join(f"<li style=\"margin:4px 0;\">{html.escape(line)}</li>" for line in item_lines)
        items_html = f'<ul style="margin:12px 0;padding-left:20px;color:#374151;">{lis}</ul>'

    html_body = f"""
<div style="font-family:system-ui,-apple-system,'Segoe UI',sans-serif;font-size:15px;line-height:1.55;color:#111827;max-width:560px;">
  <p>Xin chào <strong>{html.escape(display_name)}</strong>,</p>
  <p>Bạn còn sản phẩm trong giỏ hàng nhưng chưa hoàn tất đặt hàng.</p>
  {items_html}
  <p>Shop gửi thêm mã <strong>{html.escape(promo_code)}</strong> — giảm <strong>{discount_percent}%</strong>
     (tối đa <strong>{html.escape(max_discount_label)}đ</strong>, hết hạn sau <strong>{valid_days}</strong> ngày).
     Mã đã nằm trong <a href="{html.escape(wallet_url)}">ví khuyến mãi</a> của bạn.</p>
  <p style="margin:20px 0 12px;">
    <a href="{html.escape(cart_url)}" style="display:inline-block;padding:12px 22px;background:#ea580c;color:#ffffff !important;text-decoration:none;border-radius:10px;font-weight:600;">
      Xem giỏ hàng &amp; đặt hàng
    </a>
  </p>
  <p style="font-size:12px;color:#6b7280;word-break:break-all;">Hoặc sao chép liên kết giỏ hàng: <a href="{html.escape(cart_url)}">{html.escape(cart_url)}</a></p>
  <p style="margin-top:24px;">Trân trọng,<br/>188.com.vn</p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;" />
  <p style="font-size:12px;color:#9ca3af;">Tin nhắn tự động từ 188.com.vn</p>
</div>
"""
    send_email(to_email, subject, text_body, html_body)
    logger.info("cart_abandon_email sent to=%s promo=%s", to_email, promo_code)


def send_newsletter_welcome_email(to_email: str) -> None:
    """Email chào mừng sau khi đăng ký nhận tin footer."""
    if not to_email or not settings.is_smtp_configured():
        return
    if not getattr(settings, "NEWSLETTER_WELCOME_EMAIL_ENABLED", True):
        return

    origin = _frontend_origin()
    shop_url = origin
    subject = "188.com.vn — Bạn đã đăng ký nhận tin thành công"
    text_body = (
        "Xin chào,\n\n"
        "Cảm ơn bạn đã đăng ký nhận tin từ 188.com.vn. "
        "Shop sẽ gửi ưu đãi, sale và gợi ý sản phẩm mới qua email này.\n\n"
        f"Mua sắm ngay: {shop_url}\n\n"
        "Trân trọng,\n188.com.vn\n"
        f"--\nTin nhắn tự động từ 188.com.vn · {origin}"
    )
    html_body = f"""
<div style="font-family:system-ui,-apple-system,'Segoe UI',sans-serif;font-size:15px;line-height:1.55;color:#111827;max-width:560px;">
  <p>Xin chào,</p>
  <p>Cảm ơn bạn đã <strong>đăng ký nhận tin</strong> từ 188.com.vn. Shop sẽ gửi ưu đãi, sale và gợi ý sản phẩm mới qua email này.</p>
  <p style="margin:20px 0 12px;">
    <a href="{html.escape(shop_url)}" style="display:inline-block;padding:12px 22px;background:#ea580c;color:#ffffff !important;text-decoration:none;border-radius:10px;font-weight:600;">
      Khám phá 188.com.vn
    </a>
  </p>
  <p style="font-size:12px;color:#6b7280;word-break:break-all;">Hoặc mở: <a href="{html.escape(shop_url)}">{html.escape(shop_url)}</a></p>
  <p style="margin-top:24px;">Trân trọng,<br/>188.com.vn</p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;" />
  <p style="font-size:12px;color:#9ca3af;">Tin nhắn tự động từ 188.com.vn</p>
</div>
"""
    send_email(to_email, subject, text_body, html_body)
    logger.info("newsletter_welcome_email sent to=%s", to_email)


def send_marketing_email(to_email: str, *, subject: str, message: str) -> None:
    """Email marketing / broadcast — nội dung do admin nhập."""
    if not to_email or not settings.is_smtp_configured():
        return

    origin = _frontend_origin()
    shop_url = origin
    safe_subject = (subject or "188.com.vn").strip()
    body_text = (message or "").strip()
    text_body = (
        f"{body_text}\n\n"
        f"Mua sắm tại: {shop_url}\n\n"
        "Trân trọng,\n188.com.vn\n"
        f"--\nTin nhắn từ 188.com.vn · {origin}"
    )
    html_message = html.escape(body_text).replace("\n", "<br/>")
    html_body = f"""
<div style="font-family:system-ui,-apple-system,'Segoe UI',sans-serif;font-size:15px;line-height:1.55;color:#111827;max-width:560px;">
  <p style="white-space:pre-wrap;">{html_message}</p>
  <p style="margin:20px 0 12px;">
    <a href="{html.escape(shop_url)}" style="display:inline-block;padding:12px 22px;background:#ea580c;color:#ffffff !important;text-decoration:none;border-radius:10px;font-weight:600;">
      Xem 188.com.vn
    </a>
  </p>
  <p style="font-size:12px;color:#6b7280;word-break:break-all;">{html.escape(shop_url)}</p>
  <p style="margin-top:24px;">Trân trọng,<br/>188.com.vn</p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;" />
  <p style="font-size:12px;color:#9ca3af;">Bạn nhận email vì đã đăng ký nhận tin từ 188.com.vn</p>
</div>
"""
    send_email(to_email, safe_subject, text_body, html_body)


def _format_vnd_plain(n) -> str:
    try:
        x = int(Decimal(str(n)))
        return f"{x:,}".replace(",", ".")
    except Exception:
        return str(n)


def _order_deposit_paid_positive(order) -> bool:
    try:
        return Decimal(str(order.deposit_paid or 0)) > 0
    except Exception:
        return False


def _order_eligible_for_deposit_confirmed_email(order, status_value: str) -> bool:
    """
    Sau xác nhận cọc, timeline vận chuyển có thể đẩy đơn sang processing ngay —
    vẫn gửi email nếu đã ghi nhận deposit_paid.
    """
    st = (status_value or "").strip()
    if st == "cancelled":
        return False
    if not getattr(order, "requires_deposit", False):
        return st in ("deposit_paid", "confirmed")
    if not _order_deposit_paid_positive(order):
        return False
    return st not in ("waiting_deposit", "pending")


def _google_customer_reviews_email_extras(
    db,
    *,
    detail_url: str,
    deposit_url: str,
) -> tuple[list[str], str]:
    """
    Đoạn email khách sau cọc — nhắc tham gia Đánh giá khách hàng qua Google (khi admin bật).
    Trả (dòng text thêm, HTML thêm); rỗng nếu tắt.
    """
    from app.crud import site_embed_code as embed_crud

    merchant_id = embed_crud.get_google_customer_reviews_merchant_id(db)
    if not merchant_id:
        return [], ""

    participate_url = deposit_url or detail_url
    if not participate_url:
        return [], ""

    text_lines = [
        "",
        "Đánh giá khách hàng qua Google (tùy chọn):",
        "188.com.vn tham gia chương trình Đánh giá khách hàng qua Google. "
        "Mở liên kết đơn hàng bên dưới — tại cuối trang chọn tham gia trên thanh của Google. "
        "Sau khi nhận hàng, Google có thể gửi email khảo sát trải nghiệm mua sắm.",
        f"Mở đơn và tham gia: {participate_url}",
    ]
    html_block = f"""
<div style="margin:20px 0;padding:14px 16px;background:#f0f9ff;border:1px solid #bae6fd;border-radius:10px;font-size:14px;line-height:1.5;color:#0c4a6e;">
  <p style="margin:0 0 8px;font-weight:600;color:#0369a1;">Đánh giá khách hàng qua Google (tùy chọn)</p>
  <p style="margin:0 0 12px;">188.com.vn tham gia chương trình của Google. Mở đơn hàng — chọn <strong>tham gia</strong> trên thanh hiện ở cuối trang. Sau khi nhận hàng, Google có thể gửi email khảo sát.</p>
  <p style="margin:0;text-align:center;">
    <a href="{html.escape(participate_url)}" style="display:inline-block;padding:10px 18px;background:#0369a1;color:#ffffff !important;text-decoration:none;border-radius:8px;font-weight:600;">
      Mở đơn · tham gia đánh giá
    </a>
  </p>
</div>
"""
    return text_lines, html_block


class DepositEmailDeliveryResult(TypedDict):
    sent: bool
    to: Optional[str]
    detail: str


def schedule_deposit_confirmed_email(order_id: int) -> None:
    """
    Email «đã nhận cọc» trong thread nền — chờ commit DB (SePay webhook).
    """

    def _run() -> None:
        time.sleep(1.5)
        send_deposit_confirmed_email_task(order_id)

    threading.Thread(
        target=_run,
        name=f"deposit-confirmed-email-{order_id}",
        daemon=True,
    ).start()


def deliver_deposit_confirmed_email(order_id: int) -> DepositEmailDeliveryResult:
    """
    Gửi email «đã nhận cọc» đồng bộ — dùng khi admin xác nhận để biết ngay kết quả.
    """
    result: DepositEmailDeliveryResult = {"sent": False, "to": None, "detail": ""}
    try:
        outcome = send_deposit_confirmed_email_task(order_id)
        if isinstance(outcome, dict):
            return outcome
        return result
    except Exception as exc:
        logger.exception("deliver_deposit_confirmed_email failed order_id=%s", order_id)
        result["detail"] = f"Lỗi gửi mail: {exc!s}"
        return result


def send_deposit_confirmed_email_task(order_id: int) -> DepositEmailDeliveryResult:
    """
    Email khách (đơn + tài khoản), email cảnh báo shop, thông báo in-app.
    Trả trạng thái gửi mail khách để admin hiển thị.
    """
    from sqlalchemy.orm import joinedload

    from app.crud import notification as crud_notification
    from app.db.session import SessionLocal
    from app.models.order import Order, OrderStatus
    from app.schemas.notification import NotificationCreate

    customer_result: DepositEmailDeliveryResult = {
        "sent": False,
        "to": None,
        "detail": "",
    }
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
            customer_result["detail"] = "Không tìm thấy đơn hàng"
            return customer_result
        st = getattr(order.status, "value", order.status)
        if not _order_eligible_for_deposit_confirmed_email(order, str(st)):
            logger.info(
                "deposit_notification skip: not eligible order_id=%s status=%s deposit_paid=%s",
                order_id,
                st,
                order.deposit_paid,
            )
            customer_result["detail"] = (
                f"Chưa đủ điều kiện gửi mail cọc (trạng thái: {st}, "
                f"cọc đã nhận: {order.deposit_paid or 0})"
            )
            return customer_result

        name = (order.customer_name or "Quý khách").strip()
        code = order.order_code
        amt = order.deposit_paid or order.deposit_amount or 0
        vnd = _format_vnd_plain(amt)
        fe = (settings.FRONTEND_BASE_URL or "").strip().rstrip("/")
        detail_url = f"{fe}/account/orders/{order.id}" if fe else ""
        deposit_url = f"{fe}/account/orders/{order.id}/deposit" if fe else ""
        phone = (order.customer_phone or "").strip()
        gcr_text_lines: list[str] = []
        gcr_html_block = ""
        try:
            gcr_text_lines, gcr_html_block = _google_customer_reviews_email_extras(
                db,
                detail_url=detail_url,
                deposit_url=deposit_url,
            )
        except Exception:
            logger.exception("deposit_confirmed_email: GCR block failed order_id=%s", order_id)

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
                *gcr_text_lines,
                "",
                "Trân trọng,",
                "188.com.vn",
            ]
        )
        link_html = ""
        if detail_url:
            link_html = (
                f'<p style="margin:16px 0 8px;text-align:center;">'
                f'<a href="{html.escape(detail_url)}" style="display:inline-block;padding:10px 18px;'
                f'background:#ea580c;color:#ffffff !important;text-decoration:none;border-radius:8px;font-weight:600;">'
                f"Xem chi tiết đơn hàng</a></p>"
            )
        html_body = (
            f"<div style=\"font-family:system-ui,-apple-system,'Segoe UI',sans-serif;font-size:15px;"
            f"line-height:1.55;color:#111827;max-width:560px;\">"
            f"<p>Kính gửi <strong>{html.escape(name)}</strong>,</p>"
            "<p>Cảm ơn quý khách đã <strong>thanh toán đặt cọc</strong>.</p>"
            f"<p>Mã đơn: <strong>{html.escape(str(code))}</strong><br>"
            f"Số tiền cọc: <strong>{vnd} VND</strong></p>"
            f"<p>{html.escape(status_msg)}</p>"
            f"{link_html}"
            f"{gcr_html_block}"
            "<p style=\"margin-top:24px;\">Trân trọng,<br>188.com.vn</p>"
            "</div>"
        )

        customer_result["to"] = customer_to or None
        if customer_to:
            if not settings.is_smtp_configured():
                customer_result["detail"] = (
                    "SMTP chưa cấu hình trên server (SMTP_HOST, SMTP_USER, SMTP_PASS, SMTP_FROM)"
                )
                logger.warning("deposit_confirmed_email skip: SMTP not configured order_id=%s", order_id)
            else:
                try:
                    sent = send_email(customer_to, subject, text_body, html_body)
                    customer_result["sent"] = sent
                    if sent:
                        customer_result["detail"] = "Đã gửi email xác nhận cọc"
                        logger.info("deposit_confirmed_email sent order_id=%s to=%s", order_id, customer_to)
                    else:
                        customer_result["detail"] = "Không gửi được (thiếu địa chỉ From hoặc cấu hình SMTP)"
                        logger.warning(
                            "deposit_confirmed_email not sent (SMTP/from) order_id=%s to=%s",
                            order_id,
                            customer_to,
                        )
                except Exception as exc:
                    customer_result["detail"] = f"Lỗi SMTP: {exc!s}"
                    logger.exception("deposit_confirmed_email failed order_id=%s to=%s", order_id, customer_to)
        else:
            customer_result["detail"] = "Đơn không có email khách (customer_email / tài khoản)"
            logger.warning(
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
        return customer_result
    except Exception as exc:
        logger.exception("send_deposit_confirmed_email_task failed order_id=%s", order_id)
        customer_result["detail"] = f"Lỗi hệ thống: {exc!s}"
        return customer_result
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
