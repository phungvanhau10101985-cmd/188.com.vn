"""Tra cứu vận chuyển cho đối tác: mã đơn web, SĐT (đơn gần nhất), mã EMS (đầy đủ hành trình)."""
from __future__ import annotations

import logging
import re
import secrets
from datetime import date, datetime
from typing import Any, Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud import order as order_crud
from app.models.order import Order
from app.models.order_shipment import EmsShippingRecord
from app.services import ems_tracking as ems_tracking_svc
from app.services import order_shipment_timeline as timeline_svc
from app.services.shipping_lookup_keys import issued_tokens
from app.services.shipping_operations import find_ems_record_by_token

logger = logging.getLogger(__name__)

_ORDER_CODE_RE = re.compile(r"^(DH|DC)\d{1,12}$", re.IGNORECASE)
_PHONE_DIGIT_RE = re.compile(r"\D+")

ORDER_STATUS_LABELS = {
    "pending": "Chờ xác nhận",
    "waiting_deposit": "Chờ đặt cọc",
    "deposit_paid": "Đã đặt cọc",
    "confirmed": "Đã xác nhận",
    "processing": "Đang xử lý",
    "shipping": "Đang giao hàng",
    "delivered": "Đã nhận hàng",
    "completed": "Đã đánh giá",
    "returned": "Đơn hoàn đã trả shop",
    "cancelled": "Đã hủy",
}

PAYMENT_STATUS_LABELS = {
    "pending": "Chờ thanh toán",
    "deposit_paid": "Đã đặt cọc",
    "partially_paid": "Thanh toán một phần",
    "paid": "Đã thanh toán đủ",
    "failed": "Thanh toán thất bại",
    "refunded": "Đã hoàn tiền",
}

EMS_PHASE_LABELS = {
    "posted": "Đã chấp nhận gửi",
    "in_transit": "Đang vận chuyển",
    "out_for_delivery": "Đang giao bưu tá",
    "delivered": "Phát thành công",
    "cod_collected": "Đã thu COD",
    "cod_settled": "Đã đối soát COD",
    "unknown": "Chưa xác định",
}


def configured_api_keys() -> list[str]:
    raw = (getattr(settings, "SHIPPING_LOOKUP_API_KEY", "") or "").strip()
    keys: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        key = part.strip()
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    for key in issued_tokens():
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def api_configured() -> bool:
    return bool(configured_api_keys())


def _token_matches(provided: str, expected: str) -> bool:
    a = (provided or "").encode("utf-8")
    b = (expected or "").encode("utf-8")
    if len(a) != len(b):
        secrets.compare_digest(a, a)
        return False
    return secrets.compare_digest(a, b)


def extract_request_api_key(request: Request) -> str:
    header_key = (
        request.headers.get("x-api-key")
        or request.headers.get("X-Api-Key")
        or ""
    ).strip()
    if header_key:
        return header_key
    auth = (request.headers.get("authorization") or request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def verify_shipping_lookup_auth(request: Request) -> None:
    keys = configured_api_keys()
    if not keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API tra cứu vận chuyển chưa được cấu hình (chưa cấp key).",
        )
    provided = extract_request_api_key(request)
    if not provided or not any(_token_matches(provided, key) for key in keys):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def phone_last9(phone: str) -> str:
    digits = _PHONE_DIGIT_RE.sub("", phone or "")
    if digits.startswith("84") and len(digits) >= 11:
        digits = "0" + digits[2:]
    return digits[-9:] if len(digits) >= 9 else digits


def looks_like_phone(value: str) -> bool:
    digits = _PHONE_DIGIT_RE.sub("", value or "")
    if len(digits) < 9 or len(digits) > 12:
        return False
    compact = re.sub(r"[\s.\-()]", "", (value or "").strip())
    if _ORDER_CODE_RE.match(compact):
        return False
    if ems_tracking_svc.looks_like_ems_tracking_code(compact):
        return False
    return bool(re.fullmatch(r"\+?[\d\s.\-()]{9,16}", (value or "").strip()))


def classify_query(raw: str) -> str:
    """order_code | phone | ems_code | unknown"""
    text = (raw or "").strip()
    if not text:
        return "unknown"
    compact = re.sub(r"[\s\-]", "", text)
    if ems_tracking_svc.looks_like_ems_tracking_code(compact):
        return "ems_code"
    if _ORDER_CODE_RE.match(compact):
        return "order_code"
    if looks_like_phone(text):
        return "phone"
    return "unknown"


def _enum_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(getattr(value, "value", value) or "").strip() or None


def _money(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _opt_money(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def get_latest_order_by_phone(db: Session, phone: str) -> Optional[Order]:
    last9 = phone_last9(phone)
    if len(last9) < 9:
        return None
    digits_expr = func.regexp_replace(Order.customer_phone, r"[^0-9]", "", "g")
    last9_expr = func.right(digits_expr, 9)
    # 84xxxxxxxxx → last 9 digits trùng 0xxxxxxxxx
    return (
        db.query(Order)
        .filter(last9_expr == last9)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .first()
    )


def _order_by_tracking(db: Session, tracking: str) -> Optional[Order]:
    code = (tracking or "").strip()
    if not code:
        return None
    return db.query(Order).filter(Order.tracking_number.ilike(code)).first()


def _ems_records_for_order(db: Session, order: Order) -> list[EmsShippingRecord]:
    rows = (
        db.query(EmsShippingRecord)
        .filter(EmsShippingRecord.order_id == order.id)
        .order_by(EmsShippingRecord.updated_at.desc(), EmsShippingRecord.id.desc())
        .all()
    )
    if rows:
        return rows
    if order.order_code:
        return (
            db.query(EmsShippingRecord)
            .filter(EmsShippingRecord.order_code.ilike(order.order_code))
            .order_by(EmsShippingRecord.updated_at.desc(), EmsShippingRecord.id.desc())
            .all()
        )
    return []


def _serialize_item(item: Any) -> dict[str, Any]:
    return {
        "product_id": int(getattr(item, "product_id", 0) or 0),
        "product_name": getattr(item, "product_name", None) or "",
        "product_image": getattr(item, "product_image", None),
        "product_slug": getattr(item, "product_slug", None),
        "product_code": getattr(item, "product_code", None),
        "product_sku": getattr(item, "product_sku", None),
        "unit_price": _money(getattr(item, "unit_price", None)),
        "quantity": int(getattr(item, "quantity", 0) or 0),
        "total_price": _money(getattr(item, "total_price", None)),
        "selected_size": getattr(item, "selected_size", None),
        "selected_color": getattr(item, "selected_color", None),
        "selected_color_name": getattr(item, "selected_color_name", None),
    }


def serialize_order(order: Order) -> dict[str, Any]:
    status_val = _enum_str(order.status) or ""
    pay_status = _enum_str(order.payment_status)
    return {
        "id": order.id,
        "order_code": order.order_code,
        "status": status_val,
        "status_label": ORDER_STATUS_LABELS.get(status_val, status_val),
        "payment_method": _enum_str(order.payment_method),
        "payment_status": pay_status,
        "payment_status_label": PAYMENT_STATUS_LABELS.get(pay_status or "", pay_status),
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "customer_email": order.customer_email,
        "customer_address": order.customer_address or order.shipping_address,
        "customer_note": order.customer_note,
        "shipping_method": order.shipping_method,
        "shipping_provider": order.shipping_provider,
        "tracking_number": (order.tracking_number or "").strip() or None,
        "subtotal": _money(order.subtotal),
        "shipping_fee": _money(order.shipping_fee),
        "discount_amount": _money(order.discount_amount),
        "wallet_amount_used": _money(order.wallet_amount_used),
        "total_amount": _money(order.total_amount),
        "requires_deposit": bool(order.requires_deposit),
        "deposit_amount": _money(order.deposit_amount),
        "deposit_paid": _money(order.deposit_paid),
        "remaining_amount": _money(order.remaining_amount),
        "estimated_delivery": order.estimated_delivery,
        "actual_delivery": order.actual_delivery,
        "created_at": order.created_at,
        "deposit_paid_at": order.deposit_paid_at,
        "confirmed_at": order.confirmed_at,
        "shipped_at": order.shipped_at,
        "delivered_at": order.delivered_at,
        "completed_at": order.completed_at,
        "cancelled_at": order.cancelled_at,
        "returned_at": getattr(order, "returned_at", None),
        "items": [_serialize_item(item) for item in (order.items or [])],
    }


def serialize_ems_record(record: Optional[EmsShippingRecord]) -> Optional[dict[str, Any]]:
    if record is None:
        return None
    phase = (record.ems_phase or "").strip() or None
    return {
        "reference_code": (record.reference_code or "").strip() or None,
        "ems_tracking_code": (record.ems_tracking_code or "").strip() or None,
        "ems_reference_code": (record.ems_reference_code or "").strip() or None,
        "ems_status": (record.ems_status or "").strip() or None,
        "ems_phase": phase,
        "ems_phase_label": EMS_PHASE_LABELS.get(phase or "", phase),
        "sync_status": (record.sync_status or "").strip() or None,
        "sync_message": (record.sync_message or "").strip() or None,
        "product_code": (record.product_code or "").strip() or None,
        "recipient_label": (record.recipient_label or "").strip() or None,
        "cod_amount": _opt_money(record.cod_amount),
        "cod_paid_amount": _opt_money(record.cod_paid_amount),
        "cod_paid_date": _date_str(record.cod_paid_date),
        "cod_settlement_status": (record.cod_settlement_status or "").strip() or None,
        "freight_amount": _opt_money(record.freight_amount),
        "freight_settlement_status": (record.freight_settlement_status or "").strip() or None,
        "shop_return_received_at": record.shop_return_received_at,
        "updated_at": record.updated_at,
    }


def serialize_ems_tracking(payload: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not payload:
        return None
    events = []
    for row in payload.get("events") or []:
        if not isinstance(row, dict):
            continue
        desc = (row.get("description") or "").strip()
        if not desc:
            continue
        events.append(
            {
                "status_code": row.get("status_code"),
                "description": desc,
                "address": (row.get("address") or None),
                "traced_at": row.get("traced_at"),
            }
        )
    return {
        "available": bool(payload.get("available")),
        "tracking_code": payload.get("tracking_code"),
        "reference_code": payload.get("reference_code"),
        "customer_code": payload.get("customer_code"),
        "weight_grams": payload.get("weight_grams"),
        "receiver_address": payload.get("receiver_address"),
        "current_status": payload.get("current_status"),
        "current_status_description": payload.get("current_status_description"),
        "events": events,
        "error": payload.get("error"),
    }


def _shop_timeline_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "current_step_key": payload.get("current_step_key"),
        "footer_note": payload.get("footer_note"),
        "waiting_admin_at_customs": bool(payload.get("waiting_admin_at_customs")),
        "waiting_admin_domestic_delivery": bool(payload.get("waiting_admin_domestic_delivery")),
        "events": list(payload.get("events") or []),
    }


def _live_ems_payload(
    *,
    tracking_number: Optional[str],
    shipping_provider: Optional[str],
    force: bool = False,
) -> Optional[dict[str, Any]]:
    code = (tracking_number or "").strip()
    if not code:
        return None
    if force or ems_tracking_svc.should_fetch_ems_tracking(
        tracking_number=code,
        shipping_provider=shipping_provider,
    ):
        return ems_tracking_svc.fetch_ems_tracking(code)
    return None


def _resolve_tracking(
    order: Optional[Order],
    record: Optional[EmsShippingRecord],
    fallback_ems_code: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    tracking = None
    provider = None
    if order is not None:
        tracking = (order.tracking_number or "").strip() or None
        provider = (order.shipping_provider or "").strip() or None
    if record is not None:
        if not tracking:
            tracking = (record.ems_tracking_code or record.tracking_number_saved or "").strip() or None
        if not provider and tracking:
            provider = "EMS"
    if not tracking and fallback_ems_code:
        tracking = fallback_ems_code.strip() or None
        provider = provider or "EMS"
    return tracking, provider


def _build_payload(
    db: Session,
    *,
    query: str,
    query_type: str,
    matched_by: Optional[str],
    order: Optional[Order],
    record: Optional[EmsShippingRecord],
    is_latest_order: bool = False,
    force_ems: bool = False,
    fallback_ems_code: Optional[str] = None,
) -> dict[str, Any]:
    tracking, provider = _resolve_tracking(order, record, fallback_ems_code)
    shop_timeline = None
    live_ems = None
    if order is not None:
        timeline = timeline_svc.get_timeline_payload(db, order)
        shop_timeline = _shop_timeline_from_payload(timeline)
        if not tracking:
            tracking = (timeline.get("tracking_number") or "").strip() or tracking
        if not provider:
            provider = (timeline.get("shipping_provider") or "").strip() or provider
        live_raw = timeline.get("ems_tracking")
        if isinstance(live_raw, dict):
            live_ems = serialize_ems_tracking(live_raw)
    if live_ems is None or force_ems:
        fetched = _live_ems_payload(
            tracking_number=tracking or fallback_ems_code,
            shipping_provider=provider or ("EMS" if force_ems else None),
            force=force_ems,
        )
        if fetched:
            live_ems = serialize_ems_tracking(fetched)
            if not tracking:
                tracking = (fetched.get("tracking_code") or "").strip() or tracking
            if not provider and tracking:
                provider = "EMS"

    payload = {
        "ok": True,
        "query": query,
        "query_type": query_type,
        "matched_by": matched_by,
        "is_latest_order": is_latest_order,
        "tracking_number": tracking,
        "shipping_provider": provider,
        "order": serialize_order(order) if order is not None else None,
        "shop_timeline": shop_timeline,
        "ems_record": serialize_ems_record(record),
        "ems_tracking": live_ems,
    }
    logger.info(
        "shipping lookup type=%s matched_by=%s order=%s tracking=%s",
        query_type,
        matched_by,
        getattr(order, "order_code", None),
        tracking,
    )
    return payload


def _not_found(message: str) -> None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def lookup_by_order_code(db: Session, order_code: str, *, query: Optional[str] = None) -> dict[str, Any]:
    code = (order_code or "").strip()
    order = order_crud.get_order_by_code(db, code)
    if not order:
        _not_found(f"Không tìm thấy đơn hàng {code}.")
    records = _ems_records_for_order(db, order)
    record = records[0] if records else None
    return _build_payload(
        db,
        query=query or code,
        query_type="order_code",
        matched_by="order_code",
        order=order,
        record=record,
    )


def lookup_by_phone(db: Session, phone: str, *, query: Optional[str] = None) -> dict[str, Any]:
    order = get_latest_order_by_phone(db, phone)
    if not order:
        _not_found("Không tìm thấy đơn hàng với số điện thoại này.")
    records = _ems_records_for_order(db, order)
    record = records[0] if records else None
    return _build_payload(
        db,
        query=query or phone.strip(),
        query_type="phone",
        matched_by="phone",
        order=order,
        record=record,
        is_latest_order=True,
    )


def lookup_by_ems_code(db: Session, ems_code: str, *, query: Optional[str] = None) -> dict[str, Any]:
    token = (ems_code or "").strip()
    record = find_ems_record_by_token(db, token)
    order: Optional[Order] = None
    matched_by = "ems_tracking_code"
    if record:
        if record.ems_tracking_code and record.ems_tracking_code.strip().upper() == token.upper():
            matched_by = "ems_tracking_code"
        elif record.reference_code and record.reference_code.strip().upper() == token.upper():
            matched_by = "ems_reference_code"
        elif record.ems_reference_code and record.ems_reference_code.strip().upper() == token.upper():
            matched_by = "ems_reference_code"
        elif record.order_code and record.order_code.strip().upper() == token.upper():
            matched_by = "order_code"
        if record.order_id:
            order = db.query(Order).filter(Order.id == record.order_id).first()
        if order is None and record.order_code:
            order = order_crud.get_order_by_code(db, record.order_code)
    if order is None:
        order = _order_by_tracking(db, token)
        if order is not None:
            matched_by = "order_tracking_number"
            if record is None:
                records = _ems_records_for_order(db, order)
                record = records[0] if records else None

    tracking_for_live = token
    if record and (record.ems_tracking_code or "").strip():
        tracking_for_live = record.ems_tracking_code.strip()

    payload = _build_payload(
        db,
        query=query or token,
        query_type="ems_code",
        matched_by=matched_by if (order or record) else "ems_live",
        order=order,
        record=record,
        force_ems=True,
        fallback_ems_code=tracking_for_live,
    )
    live = payload.get("ems_tracking") or {}
    has_events = bool(live.get("events"))
    has_status = bool(live.get("current_status_description"))
    if order is None and record is None and not has_events and not has_status:
        _not_found(f"Không tìm thấy vận đơn EMS {token}.")
    return payload


def lookup_shipping(
    db: Session,
    *,
    q: Optional[str] = None,
    order_code: Optional[str] = None,
    phone: Optional[str] = None,
    ems_code: Optional[str] = None,
) -> dict[str, Any]:
    explicit_ems = (ems_code or "").strip()
    explicit_order = (order_code or "").strip()
    explicit_phone = (phone or "").strip()
    raw = (q or "").strip()

    if explicit_ems:
        return lookup_by_ems_code(db, explicit_ems, query=explicit_ems)
    if explicit_order:
        return lookup_by_order_code(db, explicit_order, query=explicit_order)
    if explicit_phone:
        return lookup_by_phone(db, explicit_phone, query=explicit_phone)

    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Thiếu đầu vào. Gửi q (mã đơn / SĐT / mã EMS) hoặc order_code / phone / ems_code.",
        )

    kind = classify_query(raw)
    if kind == "ems_code":
        return lookup_by_ems_code(db, raw, query=raw)
    if kind == "order_code":
        return lookup_by_order_code(db, raw, query=raw)
    if kind == "phone":
        return lookup_by_phone(db, raw, query=raw)

    record = find_ems_record_by_token(db, raw)
    if record:
        return lookup_by_ems_code(db, raw, query=raw)
    order = order_crud.get_order_by_code(db, raw)
    if order:
        return lookup_by_order_code(db, raw, query=raw)
    if len(phone_last9(raw)) >= 9:
        return lookup_by_phone(db, raw, query=raw)
    _not_found(f"Không nhận diện được mã tra cứu: {raw}")
