# backend/app/services/sepay.py — VietQR qua SePay + đối soát nội dung CK cọc đơn hàng
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qsl, urlencode

from fastapi import Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud import order as crud_order
from app.crud import payment as crud_payment
from app.models.order import DepositType, Order, OrderStatus, PaymentMethod, PaymentStatus

logger = logging.getLogger(__name__)

_ORDER_CODE_RE = re.compile(r"(DH\d+)", re.IGNORECASE)


def build_transfer_content_for_order(order: Order) -> str:
    """
    Nội dung CK (`des` trên qr.sepay.vn), trùng với đối soát webhook.

    Định dạng khớp SePay dashboard: ``{SEPAY_TRANSFER_PREFIX} {body}`` (mặc định ``SEVQR DH020``).

    - ``SEPAY_TRANSFER_BODY=order_code`` (mặc định): body = mã đơn (có thể + SĐT nếu LEGACY).
    - ``SEPAY_TRANSFER_BODY=dh_order_id``: body = ``DH{order.id}`` (ví dụ ``SEVQR DH6171174772``).

    Nếu ``SEPAY_TRANSFER_PREFIX`` rỗng, dùng ``SEPAY_CONTENT_PREFIX`` (tương thích cũ).
    """
    body_style = getattr(settings, "SEPAY_TRANSFER_BODY", "order_code") or "order_code"
    if body_style == "dh_order_id":
        body = f"DH{order.id}"
    else:
        code = (order.order_code or "").strip()
        if getattr(settings, "SEPAY_TRANSFER_CONTENT_LEGACY", False):
            phone_digits = "".join(c for c in (order.customer_phone or "") if c.isdigit())[-10:]
            body = f"{code}-{phone_digits}".rstrip("-") if phone_digits else code
        else:
            body = code

    label = (getattr(settings, "SEPAY_TRANSFER_PREFIX", None) or "").strip()
    if not label:
        label = (getattr(settings, "SEPAY_CONTENT_PREFIX", None) or "").strip()
    if label:
        return f"{label} {body}".strip()
    return body


def resolve_order_from_sepay_transfer_content(db: Session, content: str) -> Optional[Order]:
    """
    Tìm đơn từ nội dung CK: theo order_code (DH020), hoặc theo id (DH123) khi body là dh_order_id.
    """
    token = extract_order_code_from_content(content)
    if not token:
        return None
    order = crud_order.get_order_by_code(db, token)
    if order:
        return order
    order = db.query(Order).filter(func.lower(Order.order_code) == func.lower(token)).first()
    if order:
        return order
    m = re.match(r"^DH(\d+)$", token, re.IGNORECASE)
    if not m:
        return None
    oid = int(m.group(1))
    return crud_order.get_order(db, oid)


def resolve_order_from_sepay_payload(db: Session, data: Dict[str, Any], text_blob: str) -> Optional[Order]:
    """Ưu tiên trường `code` do SePay nhận diện (Công ty → Cấu hình chung), sau đó mới parse nội dung SMS."""
    raw_code = _pick(data, "code")
    if raw_code is not None and str(raw_code).strip():
        s = str(raw_code).strip()
        if re.match(r"^DH\d+$", s, re.IGNORECASE):
            tok = s.upper()
            o = crud_order.get_order_by_code(db, tok)
            if o:
                return o
            o = db.query(Order).filter(func.lower(Order.order_code) == s.lower()).first()
            if o:
                return o
            m = re.match(r"^DH(\d+)$", s, re.IGNORECASE)
            if m:
                return crud_order.get_order(db, int(m.group(1)))
    return resolve_order_from_sepay_transfer_content(db, text_blob)


def build_sepay_qr_image_url(*, account_number: str, bank_code: str, amount: Decimal, des: str) -> str:
    q = {
        "acc": account_number.strip(),
        "bank": bank_code.strip(),
        "amount": str(int(amount)),
        "des": des,
        "template": getattr(settings, "SEPAY_QR_TEMPLATE", "compact") or "compact",
    }
    return f"https://qr.sepay.vn/img?{urlencode(q)}"


def sepay_configured_for_qr() -> bool:
    acc = (getattr(settings, "SEPAY_QR_ACCOUNT_NUMBER", "") or "").strip()
    bank = (getattr(settings, "SEPAY_QR_BANK_CODE", "") or "").strip()
    return bool(acc and bank)


def _normalize_client_ip(s: str) -> str:
    t = (s or "").strip()
    if t.lower().startswith("::ffff:"):
        return t[7:]
    if "%" in t:
        t = t.split("%", 1)[0]
    return t


def _peer_trust_x_forwarded_for(host: str) -> bool:
    """Chỉ đọc X-Forwarded-For khi kết nối trực tiếp từ proxy nội bộ (Next, ngrok → app)."""
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(_normalize_client_ip(host))
    except ValueError:
        return False
    return bool(ip.is_loopback or ip.is_private)


def _webhook_ip_candidates(request: Request) -> list[str]:
    """IP để đối chiếu allowlist: peer trực tiếp hoặc toàn bộ chuỗi XFF khi peer là localhost/private."""
    direct = ""
    if request.client and request.client.host:
        direct = _normalize_client_ip(request.client.host)
    xff_raw = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For") or ""
    parts = [_normalize_client_ip(p) for p in xff_raw.split(",") if p.strip()]
    if _peer_trust_x_forwarded_for(direct):
        return [p for p in parts if p]
    if direct:
        return [direct]
    return parts[:1] if parts else []


def verify_webhook(request: Request, raw_body: bytes) -> bool:
    api_key = (getattr(settings, "SEPAY_WEBHOOK_API_KEY", "") or "").strip()
    secret = (getattr(settings, "SEPAY_SECRET_KEY", "") or "").strip()
    if api_key:
        auth_raw = (request.headers.get("authorization") or request.headers.get("Authorization") or "").strip()
        auth = " ".join(auth_raw.split())
        expected = " ".join(f"Apikey {api_key}".split())
        if hmac.compare_digest(auth, expected) or auth.lower() == expected.lower():
            return True
        logger.warning(
            "SePay webhook: Authorization không khớp SEPAY_WEBHOOK_API_KEY (có header=%s)",
            bool(auth),
        )
        return False

    sig = request.headers.get("x-sepay-signature") or request.headers.get("X-Sepay-Signature")
    if secret and sig and raw_body:
        mac = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        hex_d = mac.hex()
        b64_d = base64.b64encode(mac).decode("ascii")
        if hmac.compare_digest(sig, hex_d) or hmac.compare_digest(sig, b64_d):
            return True
    elif secret and not sig:
        logger.debug(
            "SePay webhook: có SEPAY_SECRET_KEY nhưng request không có x-sepay-signature "
            "(webhook my.sepay.vn thường dùng Apikey hoặc Không chứng thực, không ký body bằng secret này)"
        )

    if getattr(settings, "SEPAY_ALLOW_INSECURE_DEV", False):
        logger.warning("SePay webhook: bỏ qua xác thực (SEPAY_ALLOW_INSECURE_DEV) — chỉ dùng khi test")
        return True
    # TRUST_NO_AUTH_IP trước REQUIRE_SIGNATURE: webhook "Không chứng thực" vẫn chấp nhận theo IP SePay.
    if getattr(settings, "SEPAY_WEBHOOK_TRUST_NO_AUTH_IP", False):
        allow = getattr(settings, "SEPAY_WEBHOOK_IP_ALLOWLIST", frozenset())
        candidates = _webhook_ip_candidates(request)
        for ip in candidates:
            if ip in allow:
                logger.info("SePay webhook: chấp nhận theo IP allowlist (TRUST_NO_AUTH_IP), ip=%s", ip)
                return True
        logger.warning(
            "SePay webhook: TRUST_NO_AUTH_IP bật nhưng không có IP khớp allowlist trong %s",
            candidates or ["(không xác định)"],
        )
    if getattr(settings, "SEPAY_REQUIRE_SIGNATURE", False):
        logger.warning("SePay webhook: thiếu chữ ký / API key nhưng SEPAY_REQUIRE_SIGNATURE=true")
        return False
    if not getattr(settings, "SEPAY_WEBHOOK_TRUST_NO_AUTH_IP", False):
        logger.warning(
            "SePay webhook: không có SEPAY_WEBHOOK_API_KEY / chữ ký hợp lệ — "
            "đặt key trùng SePay (Authorization: Apikey …), hoặc SEPAY_WEBHOOK_TRUST_NO_AUTH_IP=true nếu webhook là Không chứng thực"
        )
    return False


def parse_webhook_payload(raw_body: bytes, content_type: str) -> Dict[str, Any]:
    ct = (content_type or "").lower()
    text = raw_body.decode("utf-8", errors="replace") if raw_body else ""
    if "application/json" in ct or text.strip().startswith("{"):
        try:
            return json.loads(text) if text.strip() else {}
        except json.JSONDecodeError:
            return {}
    if "application/x-www-form-urlencoded" in ct:
        return dict(parse_qsl(text, keep_blank_values=True))
    try:
        return json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        return {}


def _pick(d: Dict[str, Any], *keys: str) -> Any:
    lower_map = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        if k in d:
            return d[k]
        lk = k.lower()
        if lk in lower_map:
            return lower_map[lk]
    return None


def extract_order_code_from_content(content: str) -> Optional[str]:
    if not content:
        return None
    m = _ORDER_CODE_RE.search(content.replace(" ", ""))
    if m:
        return m.group(1).upper()
    return None


def _amount_equal(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= Decimal("1")


def apply_sepay_incoming_transfer(db: Session, data: Dict[str, Any]) -> Tuple[bool, str, Optional[int]]:
    """
    Xử lý payload webhook SePay (tiền vào).
    Trả (True, message, order_id) — order_id chỉ có khi vừa xác nhận cọc thành công (để gửi email).
    """
    transfer_type = str(_pick(data, "transferType", "transfer_type") or "").lower()
    if transfer_type and transfer_type != "in":
        return True, "ignored_out", None

    amount_raw = _pick(data, "transferAmount", "transfer_amount", "amount")
    if amount_raw is None:
        return False, "missing_amount", None
    try:
        amount = Decimal(str(amount_raw))
    except Exception:
        return False, "invalid_amount", None

    raw_content = str(_pick(data, "content", "transaction_content") or "")
    raw_desc = str(_pick(data, "description") or "")
    text_blob = f"{raw_content} {raw_desc}".strip()
    sepay_id = _pick(data, "id", "transaction_id")
    if sepay_id is None:
        return False, "missing_id", None
    sepay_id_str = str(sepay_id)

    if crud_payment.find_payment_by_sepay_id(db, sepay_id_str):
        return True, "duplicate", None

    reference = str(_pick(data, "referenceCode", "reference_code") or "")
    acc_in = str(_pick(data, "accountNumber", "account_number") or "").replace(" ", "")
    expected_acc = (getattr(settings, "SEPAY_QR_ACCOUNT_NUMBER", "") or "").replace(" ", "")
    if expected_acc and acc_in and acc_in != expected_acc:
        logger.info("SePay webhook account mismatch: %s vs %s", acc_in, expected_acc)
        return False, "account_mismatch", None

    sepay_code = _pick(data, "code")
    code_looks_order = bool(
        sepay_code is not None
        and str(sepay_code).strip()
        and re.match(r"^DH\d+$", str(sepay_code).strip(), re.IGNORECASE)
    )
    if not code_looks_order and not extract_order_code_from_content(text_blob):
        return False, "no_order_code_in_content", None

    order = resolve_order_from_sepay_payload(db, data, text_blob)
    if not order:
        return False, "order_not_found", None

    status_val = getattr(order.status, "value", order.status)
    if status_val != OrderStatus.WAITING_DEPOSIT.value:
        return False, "order_not_waiting_deposit", None

    if not order.requires_deposit:
        return False, "no_deposit_required", None

    expected_content = build_transfer_content_for_order(order)
    norm_c = text_blob.upper().replace(" ", "")
    norm_e = expected_content.upper().replace(" ", "")
    oc = order.order_code.upper().replace(" ", "")
    id_ref = f"DH{order.id}".upper()
    if (
        norm_e not in norm_c
        and oc not in norm_c
        and id_ref not in norm_c
    ):
        return False, "content_mismatch", None

    dep = Decimal(str(order.deposit_amount))
    if not _amount_equal(amount, dep):
        return False, "amount_mismatch", None

    crud_payment.create_payment(
        db=db,
        order_id=order.id,
        amount=amount,
        payment_method=PaymentMethod.BANK_TRANSFER.value,
        payment_type="deposit_sepay",
        transaction_code=sepay_id_str,
        payment_status=PaymentStatus.PAID,
        payment_gateway_data={
            "source": "sepay",
            "reference": reference,
            "payload": data,
        },
    )

    order.deposit_paid = amount
    order.deposit_paid_at = datetime.now()
    order.remaining_amount = Decimal(str(order.total_amount)) - amount

    dt = order.deposit_type
    dt_val = dt.value if hasattr(dt, "value") else dt
    if dt_val == DepositType.PERCENT_100.value:
        order.payment_status = PaymentStatus.PAID
        order.status = OrderStatus.CONFIRMED
        order.confirmed_at = datetime.now()
    else:
        order.payment_status = PaymentStatus.DEPOSIT_PAID
        order.status = OrderStatus.DEPOSIT_PAID

    oid = order.id
    db.commit()
    return True, "ok", oid
