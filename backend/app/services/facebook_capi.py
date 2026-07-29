"""
Meta Conversions API — server-side Purchase sau khi xác nhận cọc.

Khớp payload frontend (meta-pixel.ts): value, currency VND, content_ids, contents, order_id.
event_id cố định Purchase_{order_id} — dedupe với Pixel trình duyệt cùng event_id.
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud import site_embed_code as embed_crud
from app.db.session import SessionLocal
from app.models.order import Order, OrderItem, OrderStatus
from app.services.warehouse_stock import reload_order_with_items

logger = logging.getLogger(__name__)

META_PIXEL_CURRENCY = "VND"

POST_DEPOSIT_STATUSES = frozenset(
    {
        OrderStatus.DEPOSIT_PAID.value,
        OrderStatus.CONFIRMED.value,
        OrderStatus.PROCESSING.value,
        OrderStatus.SHIPPING.value,
        OrderStatus.DELIVERED.value,
        OrderStatus.COMPLETED.value,
    }
)


def meta_purchase_event_id(order_id: int) -> str:
    return f"Purchase_{int(order_id)}"


def _sha256_normalized(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def _normalize_phone_vn(phone: str) -> Optional[str]:
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return None
    if digits.startswith("0"):
        return "84" + digits[1:]
    if not digits.startswith("84"):
        return "84" + digits
    return digits


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _content_id_for_order_item(line: OrderItem) -> str:
    sheet_id = ""
    product = getattr(line, "product", None)
    if product is not None:
        raw = getattr(product, "product_id", None)
        if raw is not None:
            sheet_id = str(raw).strip()
    if sheet_id:
        return sheet_id
    return str(line.product_id)


def build_purchase_custom_data(order: Order) -> Dict[str, Any]:
    """Payload custom_data Purchase — mirror frontend cartMetaCustomData."""
    lines: List[OrderItem] = list(order.items or [])
    contents: List[Dict[str, Any]] = []
    content_ids: List[str] = []
    num_items = 0

    for line in lines:
        cid = _content_id_for_order_item(line)
        if cid and cid not in content_ids:
            content_ids.append(cid)
        unit = float(_dec(line.unit_price))
        qty = int(line.quantity or 0)
        num_items += qty
        primary_id = cid or str(line.product_id)
        contents.append({"id": primary_id, "quantity": qty, "item_price": unit})

    value = float(_dec(order.total_amount))
    if value <= 0:
        value = float(sum(_dec(line.total_price) for line in lines))

    payload: Dict[str, Any] = {
        "value": value,
        "currency": META_PIXEL_CURRENCY,
        "content_type": "product",
        "content_ids": content_ids,
        "contents": contents,
        "num_items": num_items,
        "order_id": str(order.id),
    }
    return payload


def build_purchase_user_data(order: Order) -> Dict[str, Any]:
    """user_data hashed — tăng khớp sự kiện Meta."""
    ud: Dict[str, Any] = {}
    email = (order.customer_email or "").strip()
    if email:
        ud["em"] = [_sha256_normalized(email)]
    phone = _normalize_phone_vn(order.customer_phone or "")
    if phone:
        ud["ph"] = [_sha256_normalized(phone)]
    return ud


def order_eligible_for_meta_purchase(order: Order) -> bool:
    """Đơn cọc đã ghi nhận — đủ điều kiện bắn Purchase."""
    if not order.requires_deposit:
        return False
    st = getattr(order.status, "value", order.status)
    if st not in POST_DEPOSIT_STATUSES:
        return False
    return _dec(order.deposit_paid) > 0


def purchase_event_source_url(order_id: int) -> str:
    fe = (
        (getattr(settings, "FRONTEND_BASE_URL", "") or "").strip()
        or (getattr(settings, "WEBSITE_URL", "") or "").strip()
        or "https://188.com.vn"
    ).rstrip("/")
    return f"{fe}/account/orders/{order_id}/deposit"


def post_facebook_capi_events(db: Session, events: List[Dict[str, Any]]) -> Tuple[bool, Any]:
    """Gửi batch sự kiện lên Meta Graph API."""
    pix, access_token = embed_crud.get_facebook_pixel_id_and_capi_access_token(db)
    if not pix or not access_token:
        return False, "capi_not_configured"

    ver = getattr(settings, "FACEBOOK_GRAPH_API_VERSION", "v21.0")
    url = f"https://graph.facebook.com/{ver}/{pix}/events"
    try:
        r = requests.post(
            url,
            params={"access_token": access_token},
            json={"data": events},
            timeout=30,
        )
    except requests.RequestException as exc:
        logger.exception("Facebook CAPI request failed")
        return False, f"request_error:{exc!s}"

    try:
        body = r.json()
    except Exception:
        body = {"raw": (r.text or "")[:2000]}

    if not r.ok:
        logger.warning("Facebook CAPI HTTP %s: %s", r.status_code, body)
        return False, body

    return True, body


def send_meta_purchase_for_order(db: Session, order: Order) -> Tuple[bool, str]:
    """Gửi Purchase CAPI cho một đơn (idempotent theo event_id)."""
    if not order_eligible_for_meta_purchase(order):
        return False, "not_eligible"

    lines = list(order.items or [])
    if not lines:
        return False, "no_items"

    custom_data = build_purchase_custom_data(order)
    if not custom_data.get("content_ids"):
        return False, "no_content_ids"

    user_data = build_purchase_user_data(order)
    evt: Dict[str, Any] = {
        "event_name": "Purchase",
        "event_time": int(time.time()),
        "event_id": meta_purchase_event_id(order.id),
        "action_source": "website",
        "event_source_url": purchase_event_source_url(order.id),
        "custom_data": custom_data,
    }
    if user_data:
        evt["user_data"] = user_data

    ok, detail = post_facebook_capi_events(db, [evt])
    if ok:
        logger.info(
            "Meta CAPI Purchase sent order_id=%s event_id=%s value=%s items=%s",
            order.id,
            evt["event_id"],
            custom_data.get("value"),
            custom_data.get("num_items"),
        )
        return True, "ok"
    return False, str(detail)


def send_meta_purchase_for_order_id(order_id: int) -> Tuple[bool, str]:
    db = SessionLocal()
    try:
        order = reload_order_with_items(db, order_id)
        if not order:
            return False, "order_not_found"
        return send_meta_purchase_for_order(db, order)
    finally:
        db.close()


def schedule_meta_purchase_capi_for_order(order_id: int) -> None:
    """
    Thread nền — chờ commit DB (SePay webhook / admin) rồi gửi Purchase CAPI.
    """

    def _run() -> None:
        time.sleep(1.5)
        try:
            ok, detail = send_meta_purchase_for_order_id(order_id)
            if not ok and detail not in ("not_eligible", "capi_not_configured"):
                logger.warning(
                    "Meta CAPI Purchase skipped/failed order_id=%s detail=%s",
                    order_id,
                    detail,
                )
        except Exception:
            logger.exception("Meta CAPI Purchase task failed order_id=%s", order_id)

    threading.Thread(
        target=_run,
        name=f"meta-purchase-capi-{order_id}",
        daemon=True,
    ).start()
