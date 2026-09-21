"""Admin alert for a customer-submitted manual transfer claim/proof."""

from __future__ import annotations

import logging

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.order import Order, Payment
from app.services.email_service import send_order_email

logger = logging.getLogger(__name__)


def notify_admin_manual_transfer(payment_id: int) -> None:
    db = SessionLocal()
    try:
        payment = db.query(Payment).filter(Payment.id == payment_id).first()
        if not payment:
            return
        order = db.query(Order).filter(Order.id == payment.order_id).first()
        if not order:
            return
        code = (order.order_code or "").strip() or f"#{order.id}"
        amount = f"{int(payment.amount or 0):,}".replace(",", ".")
        transaction = (payment.transaction_code or "").strip() or "không có mã"
        subject = f"[Cần duyệt] Chứng từ chuyển khoản đơn {code}"
        body = (
            f"Khách đã gửi thông tin chuyển khoản cọc cho đơn {code}.\n"
            f"Số tiền khai báo: {amount} đ\nMã giao dịch: {transaction}\n"
            "Vui lòng mở quản trị đơn hàng để đối chiếu và xác nhận."
        )
        for recipient in settings.ORDER_DEPOSIT_ALERT_EMAILS:
            send_order_email(recipient, subject, body)
    except Exception:
        logger.exception("manual transfer admin alert failed payment_id=%s", payment_id)
    finally:
        db.close()
