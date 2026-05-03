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
from typing import Any, Dict, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode

from fastapi import Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud import order as crud_order
from app.crud import payment as crud_payment
from app.models.order import DepositType, Order, OrderStatus, Payment, PaymentMethod, PaymentStatus

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
    """
    IP để đối chiếu allowlist SePay.

    - Peer loopback/private: tin X-Forwarded-For (toàn chuỗi) và X-Real-IP (Nginx hay chỉ set một trong hai).
    - SEPAY_WEBHOOK_TRUST_PROXY_HEADERS=true: cùng logic dù peer không được coi là private (chỉ khi app sau proxy độc quyền).
    """
    direct = ""
    if request.client and request.client.host:
        direct = _normalize_client_ip(request.client.host)

    xff_raw = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For") or ""
    parts = [_normalize_client_ip(p) for p in xff_raw.split(",") if p.strip()]
    real_raw = (request.headers.get("x-real-ip") or request.headers.get("X-Real-IP") or "").strip()
    real_norm = _normalize_client_ip(real_raw) if real_raw else ""

    trust_fwd = _peer_trust_x_forwarded_for(direct) or getattr(
        settings, "SEPAY_WEBHOOK_TRUST_PROXY_HEADERS", False
    )

    if trust_fwd:
        out: list[str] = []
        seen: set[str] = set()
        for p in parts:
            if p and p not in seen:
                seen.add(p)
                out.append(p)
        if real_norm and real_norm not in seen:
            out.append(real_norm)
        if out:
            return out
        return [direct] if direct else []

    if direct:
        return [direct]
    return parts[:1] if parts else ([real_norm] if real_norm else [])


def verify_webhook(request: Request, raw_body: bytes) -> bool:
    api_key = (getattr(settings, "SEPAY_WEBHOOK_API_KEY", "") or "").strip()
    secret = (getattr(settings, "SEPAY_SECRET_KEY", "") or "").strip()
    if api_key:
        auth_raw = (request.headers.get("authorization") or request.headers.get("Authorization") or "").strip()
        auth = " ".join(auth_raw.split())
        expected = " ".join(f"Apikey {api_key}".split())
        bearer_expected = " ".join(f"Bearer {api_key}".split())
        raw_header_key = (
            request.headers.get("x-api-key")
            or request.headers.get("X-Api-Key")
            or request.headers.get("x-sepay-api-key")
            or request.headers.get("X-Sepay-Api-Key")
            or ""
        ).strip()
        query_key = (
            request.query_params.get("token")
            or request.query_params.get("api_key")
            or request.query_params.get("apikey")
            or ""
        ).strip()
        if (
            hmac.compare_digest(auth, expected)
            or auth.lower() == expected.lower()
            or hmac.compare_digest(auth, bearer_expected)
            or auth.lower() == bearer_expected.lower()
            or hmac.compare_digest(auth, api_key)
            or hmac.compare_digest(raw_header_key, api_key)
            or hmac.compare_digest(query_key, api_key)
        ):
            return True
        logger.warning(
            "SePay webhook: API key không khớp (authorization=%s, x-api-key=%s, query_token=%s); sẽ thử phương án xác thực khác nếu bật",
            bool(auth),
            bool(raw_header_key),
            bool(query_key),
        )

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
        except json.JSONDecodeError as e:
            logger.warning("SePay webhook JSON parse failed: %s; body_prefix=%r", e, text[:300])
            return {}
    if "application/x-www-form-urlencoded" in ct:
        return dict(parse_qsl(text, keep_blank_values=True))
    try:
        return json.loads(text) if text.strip() else {}
    except json.JSONDecodeError as e:
        logger.warning("SePay webhook payload parse failed: %s; body_prefix=%r", e, text[:300])
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


def _compact_alnum_upper(s: str) -> str:
    """Chuẩn hoá để đối chiếu khi NH/SePay chèn dấu chấm, khoảng đặc biệt (QR vẫn đúng nhưng chuỗi raw khác)."""
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _dh_numeric_in_content_refers_order(norm_c: str, order_id: int) -> bool:
    """DH002 và DH2 là cùng id=2; trước đây chỉ so `DH{id}` nên DH002 không khớp."""
    try:
        oid = int(order_id)
    except (TypeError, ValueError):
        return False
    for m in re.finditer(r"DH(\d+)", norm_c, re.IGNORECASE):
        try:
            if int(m.group(1)) == oid:
                return True
        except ValueError:
            continue
    return False


def _sepay_code_matches_resolved_order(data: Dict[str, Any], order: Order) -> bool:
    """Trường `code` từ SePay (cùng pipeline nhận diện với QR) khớp đơn đã resolve."""
    raw = _pick(data, "code")
    if raw is None or not str(raw).strip():
        return False
    s = str(raw).strip()
    oc = (order.order_code or "").strip()
    if oc and s.replace(" ", "").upper() == oc.replace(" ", "").upper():
        return True
    if oc and _compact_alnum_upper(s) == _compact_alnum_upper(oc):
        return True
    m = re.match(r"^DH(\d+)$", s, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1)) == order.id
        except ValueError:
            return False
    return False


def _transfer_content_matches_order(
    db: Session,
    data: Dict[str, Any],
    text_blob: str,
    order: Order,
) -> bool:
    """
    Đối chiếu nội dung CK/SMS với đơn. QR quét đúng vẫn có thể bị từ chối nếu chỉ so chuỗi quá hẹp
    (vd. DH2 không là substring của DH002; SePay gửi `code` khớp id nhưng SMS dài không chứa order_code ORD...).
    """
    expected_content = build_transfer_content_for_order(order)
    norm_c = text_blob.upper().replace(" ", "")
    norm_e = expected_content.upper().replace(" ", "")
    oc = (order.order_code or "").upper().replace(" ", "")
    id_ref = f"DH{order.id}".upper()

    if norm_e in norm_c or (oc and oc in norm_c) or (id_ref in norm_c):
        return True
    # So khớp lỏng: bỏ ký tự không phải A–Z/0–9 (vd. "SEVQR. ORD…", NBSP)
    blob_a = _compact_alnum_upper(text_blob)
    exp_a = _compact_alnum_upper(expected_content)
    if exp_a and exp_a in blob_a:
        return True
    if oc and _compact_alnum_upper(oc) in blob_a:
        return True
    if _dh_numeric_in_content_refers_order(norm_c, order.id):
        return True
    if _dh_numeric_in_content_refers_order(blob_a, order.id):
        return True
    if _sepay_code_matches_resolved_order(data, order):
        return True
    o_from_text = resolve_order_from_sepay_transfer_content(db, text_blob)
    return bool(o_from_text and o_from_text.id == order.id)


def _amount_equal(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= Decimal("1")


def ledger_transfer_content_key(raw: Optional[str]) -> str:
    """
    Khóa đối chiếu nội dung CK (luồng B): ưu tiên cụm SEVQR + mã trong SMS dài.
    """
    if not raw:
        return ""
    t = " ".join(str(raw).split()).strip().upper()
    m = re.search(r"SEVQR\s+[A-Z0-9][A-Z0-9\-]*", t, re.IGNORECASE)
    if m:
        return " ".join(m.group(0).split()).upper()
    return t


def _webhook_transfer_content_keys(text_blob: str) -> Set[str]:
    out: Set[str] = set()
    k = ledger_transfer_content_key(text_blob)
    if k:
        out.add(k)
    full = " ".join(text_blob.split()).strip().upper()
    if full:
        out.add(full)
        fk = ledger_transfer_content_key(full)
        if fk:
            out.add(fk)
    return {x for x in out if x}


def _find_matching_pending_sepay_deposit(
    db: Session,
    text_blob: str,
    amount: Decimal,
    data: Dict[str, Any],
) -> Optional[Payment]:
    """
    Tìm Payment deposit_sepay đang PENDING (đã tạo khi GET sepay-deposit-info) khớp số tiền + nội dung.
    Fallback: trường ``code`` của SePay (DHxxx) + order_id + amount — tránh lệch do chuẩn hóa SMS dài.
    """
    keys_w = _webhook_transfer_content_keys(text_blob)
    blob_compact = _compact_alnum_upper(text_blob)

    rows = (
        db.query(Payment)
        .filter(
            Payment.payment_type == "deposit_sepay",
            Payment.payment_status == PaymentStatus.PENDING,
        )
        .order_by(Payment.id.desc())
        .all()
    )
    for p in rows:
        if (p.transaction_code or "").strip():
            continue
        if not _amount_equal(Decimal(str(p.amount)), amount):
            continue
        order = crud_order.get_order(db, p.order_id)
        if not order:
            continue
        st = getattr(order.status, "value", order.status)
        if st != OrderStatus.WAITING_DEPOSIT.value or not order.requires_deposit:
            continue

        pk = ledger_transfer_content_key(p.transfer_content)
        if pk:
            if keys_w and pk in keys_w:
                return p
        p_comp = _compact_alnum_upper(p.transfer_content or "")
        if p_comp and len(p_comp) >= 6 and p_comp in blob_compact:
            return p

    # SePay: code DH{n} → cùng order id; pending đã tạo từ sepay-deposit-info + đúng amount
    raw_code = _pick(data, "code")
    if raw_code is not None and str(raw_code).strip():
        m = re.match(r"^DH(\d+)$", str(raw_code).strip(), re.IGNORECASE)
        if m:
            try:
                oid = int(m.group(1))
            except ValueError:
                oid = 0
            if oid > 0:
                p2 = (
                    db.query(Payment)
                    .filter(
                        Payment.order_id == oid,
                        Payment.payment_type == "deposit_sepay",
                        Payment.payment_status == PaymentStatus.PENDING,
                    )
                    .order_by(Payment.id.desc())
                    .first()
                )
                if p2 and not (p2.transaction_code or "").strip():
                    if _amount_equal(Decimal(str(p2.amount)), amount):
                        order2 = crud_order.get_order(db, oid)
                        if (
                            order2
                            and getattr(order2.status, "value", order2.status) == OrderStatus.WAITING_DEPOSIT.value
                            and order2.requires_deposit
                        ):
                            logger.info(
                                "SePay pending matched by webhook code order_id=%s payment_id=%s",
                                oid,
                                p2.id,
                            )
                            return p2
    return None


def _finalize_sepay_deposit_success(
    db: Session,
    order: Order,
    amount: Decimal,
    sepay_id_str: str,
    reference: str,
    data: Dict[str, Any],
    pending_payment: Optional[Payment],
) -> None:
    if pending_payment:
        pending_payment.payment_status = PaymentStatus.PAID
        pending_payment.transaction_code = sepay_id_str
        pending_payment.transfer_date = datetime.now()
        pending_payment.payment_gateway_data = {
            "source": "sepay",
            "reference": reference,
            "payload": data,
        }
        pending_payment.confirmed_at = datetime.now()
    else:
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

    db.commit()


def _latest_pending_sepay_deposit_for_order(db: Session, order_id: int) -> Optional[Payment]:
    return (
        db.query(Payment)
        .filter(
            Payment.order_id == order_id,
            Payment.payment_type == "deposit_sepay",
            Payment.payment_status == PaymentStatus.PENDING,
            or_(Payment.transaction_code.is_(None), Payment.transaction_code == ""),
        )
        .order_by(Payment.id.desc())
        .first()
    )


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

    # Fast path: SePay đã gửi code/content rõ ràng (vd. DH008) và số tiền đúng cọc của đơn.
    # Không bắt buộc đã có pending, để tránh fail khi khách chuyển ngay sau khi tạo đơn hoặc pending bị lệch.
    direct_order = resolve_order_from_sepay_payload(db, data, text_blob)
    if direct_order:
        direct_status = getattr(direct_order.status, "value", direct_order.status)
        if direct_status == OrderStatus.WAITING_DEPOSIT.value and direct_order.requires_deposit:
            dep = Decimal(str(direct_order.deposit_amount))
            if _amount_equal(amount, dep) and _transfer_content_matches_order(db, data, text_blob, direct_order):
                direct_pending = _latest_pending_sepay_deposit_for_order(db, direct_order.id)
                if direct_pending and not _amount_equal(amount, Decimal(str(direct_pending.amount))):
                    direct_pending = None
                logger.info(
                    "SePay direct match order_id=%s order_code=%s amount=%s pending_id=%s",
                    direct_order.id,
                    direct_order.order_code,
                    amount,
                    getattr(direct_pending, "id", None),
                )
                _finalize_sepay_deposit_success(
                    db,
                    direct_order,
                    amount,
                    sepay_id_str,
                    reference,
                    data,
                    direct_pending,
                )
                return True, "ok", direct_order.id

    # --- Luồng B: khớp bản ghi Payment PENDING đã tạo khi GET sepay-deposit-info (ổn định hơn parse SMS) ---
    pending = _find_matching_pending_sepay_deposit(db, text_blob, amount, data)
    if pending:
        order = crud_order.get_order(db, pending.order_id)
        if not order:
            return False, "order_not_found", None
        status_val = getattr(order.status, "value", order.status)
        if status_val != OrderStatus.WAITING_DEPOSIT.value:
            return False, "order_not_waiting_deposit", None
        if not order.requires_deposit:
            return False, "no_deposit_required", None
        # Đã khớp pending ↔ transferAmount ở _find_matching; QR/DB payment lúc GET sepay-deposit-info
        # là “hợp đồng” với khách. Nếu orders.deposit_amount đổi sau đó, vẫn chấp nhận và log cảnh báo.
        dep = Decimal(str(order.deposit_amount))
        if not _amount_equal(amount, dep):
            logger.warning(
                "SePay: webhook amount %s matches pending payment_id=%s but order.deposit_amount=%s (order_id=%s); accepting per pending QR",
                amount,
                pending.id,
                dep,
                order.id,
            )
        _finalize_sepay_deposit_success(db, order, amount, sepay_id_str, reference, data, pending)
        return True, "ok", order.id

    # --- Legacy: không có pending (khách chưa mở API cọc sau khi deploy / QR cũ) ---
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
        logger.warning(
            "SePay order_not_found code=%r amount=%s content_prefix=%r desc_prefix=%r keys=%s",
            sepay_code,
            amount,
            raw_content[:180],
            raw_desc[:180],
            sorted(str(k) for k in data.keys())[:20],
        )
        return False, "order_not_found", None

    status_val = getattr(order.status, "value", order.status)
    if status_val != OrderStatus.WAITING_DEPOSIT.value:
        return False, "order_not_waiting_deposit", None

    if not order.requires_deposit:
        return False, "no_deposit_required", None

    if not _transfer_content_matches_order(db, data, text_blob, order):
        exp_c = build_transfer_content_for_order(order)
        logger.warning(
            "SePay content_mismatch order_id=%s order_code=%s expected=%r compact_expected=%s compact_blob=%s",
            order.id,
            order.order_code,
            exp_c,
            _compact_alnum_upper(exp_c),
            _compact_alnum_upper(text_blob)[:200],
        )
        return False, "content_mismatch", None

    dep = Decimal(str(order.deposit_amount))
    if _amount_equal(amount, dep):
        _finalize_sepay_deposit_success(db, order, amount, sepay_id_str, reference, data, None)
        return True, "ok", order.id

    # Legacy: đơn + nội dung OK nhưng orders.deposit_amount lệch số tiền thực chuyển — thường do sửa đơn sau khi
    # đã GET sepay-deposit-info / QR. Nếu vẫn có dòng PENDING cùng đơn khớp transferAmount, ghi nhận theo pending.
    loose_pending = _latest_pending_sepay_deposit_for_order(db, order.id)
    if loose_pending and _amount_equal(amount, Decimal(str(loose_pending.amount))):
        if not _amount_equal(amount, dep):
            logger.warning(
                "SePay legacy: amount matches pending payment_id=%s, order.deposit_amount=%s differs (order_id=%s)",
                loose_pending.id,
                dep,
                order.id,
            )
        _finalize_sepay_deposit_success(db, order, amount, sepay_id_str, reference, data, loose_pending)
        return True, "ok", order.id

    return False, "amount_mismatch", None
