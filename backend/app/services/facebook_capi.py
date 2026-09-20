"""
Meta Conversions API — server-side Purchase sau khi xác nhận cọc.

Khớp payload frontend (meta-pixel.ts): value, currency VND, content_ids, contents, order_id.
event_id cố định Purchase_{order_id} — dedupe với Pixel trình duyệt cùng event_id.
"""
from __future__ import annotations

import hashlib
import ipaddress
import logging
import re
import threading
import time
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.crud import site_embed_code as embed_crud
from app.db.session import SessionLocal
from app.models.order import Order, OrderItem, OrderStatus

logger = logging.getLogger(__name__)

META_PIXEL_CURRENCY = "VND"
META_CLICK_ID_MAX_AGE_MS = 90 * 24 * 60 * 60 * 1000
META_CLOCK_SKEW_MS = 5 * 60 * 1000
_SHA256_HEX_RE = re.compile(r"^[a-f0-9]{64}$")
_FBP_RE = re.compile(r"^fb\.\d+\.(\d{13})\.\d+$")
_FBC_RE = re.compile(r"^fb\.\d+\.(\d{13})\.[A-Za-z0-9_-]+$")

# Không hash — Meta yêu cầu plaintext.
_PLAIN_USER_DATA_KEYS = frozenset(
    {
        "client_ip_address",
        "client_user_agent",
        "fbc",
        "fbp",
        "subscription_id",
        "fb_login_id",
        "lead_id",
        "anon_id",
        "madid",
    }
)

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

_VN_PROVINCE_FOLDED = frozenset(
    {
        "an giang",
        "ba ria vung tau",
        "bac lieu",
        "bac giang",
        "bac kan",
        "bac ninh",
        "ben tre",
        "binh dinh",
        "binh duong",
        "binh phuoc",
        "binh thuan",
        "ca mau",
        "cao bang",
        "dak lak",
        "dak nong",
        "dien bien",
        "dong nai",
        "dong thap",
        "gia lai",
        "ha giang",
        "ha nam",
        "ha tinh",
        "hai duong",
        "hai phong",
        "hau giang",
        "hoa binh",
        "hung yen",
        "khanh hoa",
        "kien giang",
        "kon tum",
        "lai chau",
        "lam dong",
        "lang son",
        "lao cai",
        "long an",
        "nam dinh",
        "nghe an",
        "ninh binh",
        "ninh thuan",
        "phu tho",
        "quang binh",
        "quang nam",
        "quang ngai",
        "quang ninh",
        "quang tri",
        "soc trang",
        "son la",
        "tay ninh",
        "thai binh",
        "thai nguyen",
        "thanh hoa",
        "thua thien hue",
        "tien giang",
        "tra vinh",
        "tuyen quang",
        "vinh long",
        "vinh phuc",
        "yen bai",
        "phu yen",
        "can tho",
        "da nang",
        "ha noi",
        "ho chi minh",
        "tp ho chi minh",
        "tphcm",
        "sai gon",
    }
)


def meta_purchase_event_id(order_id: int) -> str:
    return f"Purchase_{int(order_id)}"


def _sha256_normalized(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def _already_hashed(value: str) -> bool:
    return bool(_SHA256_HEX_RE.match((value or "").strip().lower()))


def _normalize_phone_vn(phone: str) -> Optional[str]:
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return None
    if digits.startswith("0"):
        return "84" + digits[1:]
    if not digits.startswith("84"):
        return "84" + digits
    return digits


def fold_meta_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_vn_name(full_name: str) -> Tuple[str, str]:
    """Trả (fn, ln) — họ VN đứng trước."""
    parts = fold_meta_text(full_name).split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return " ".join(parts[1:]), parts[0]


def gender_to_meta(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    value = getattr(raw, "value", raw)
    s = fold_meta_text(str(value)).replace(" ", "")
    if s in {"male", "m", "nam"}:
        return "m"
    if s in {"female", "f", "nu"}:
        return "f"
    return None


def dob_to_meta(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        raw = raw.date()
    if isinstance(raw, date):
        return raw.strftime("%Y%m%d")
    s = str(raw).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    digits = re.sub(r"\D", "", s)
    return digits if len(digits) == 8 else None


def _has_valid_meta_creation_time(value: str, pattern: re.Pattern[str]) -> bool:
    match = pattern.match((value or "").strip())
    if not match:
        return False
    creation_time_ms = int(match.group(1))
    now_ms = int(time.time() * 1000)
    return (
        now_ms - META_CLICK_ID_MAX_AGE_MS
        <= creation_time_ms
        <= now_ms + META_CLOCK_SKEW_MS
    )


def is_valid_meta_fbp(value: str) -> bool:
    return _has_valid_meta_creation_time(value, _FBP_RE)


def is_valid_meta_fbc(value: str) -> bool:
    v = (value or "").strip()
    return len(v) <= 512 and _has_valid_meta_creation_time(v, _FBC_RE)


def _valid_ip(value: str) -> Optional[str]:
    t = (value or "").strip()
    if t.lower().startswith("::ffff:"):
        t = t[7:]
    try:
        ip = ipaddress.ip_address(t)
    except ValueError:
        return None
    if ip.is_unspecified or ip.is_loopback:
        return None
    return t


def _hash_pii_value(key: str, raw: str) -> Optional[str]:
    value = (raw or "").strip()
    if not value:
        return None
    if _already_hashed(value):
        return value.lower()
    if key == "em":
        value = value.lower()
        if "@" not in value:
            return None
        return _sha256_normalized(value)
    if key == "ph":
        phone = _normalize_phone_vn(value)
        if not phone:
            return None
        return _sha256_normalized(phone)
    if key in {"fn", "ln", "ct", "st"}:
        folded = fold_meta_text(value)
        if not folded:
            return None
        return _sha256_normalized(folded)
    if key == "country":
        country = fold_meta_text(value).replace(" ", "")
        if len(country) != 2:
            country = "vn"
        return _sha256_normalized(country)
    if key == "ge":
        ge = gender_to_meta(value)
        if not ge:
            return None
        return _sha256_normalized(ge)
    if key == "db":
        db = dob_to_meta(value)
        if not db:
            return None
        return _sha256_normalized(db)
    if key == "zp":
        zp = re.sub(r"\s+", "", value.lower())
        if not zp:
            return None
        return _sha256_normalized(zp)
    if key == "external_id":
        return _sha256_normalized(value)
    return _sha256_normalized(value)


def _iter_user_data_values(raw: Any) -> Iterable[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if x is not None and str(x).strip()]
    s = str(raw).strip()
    return [s] if s else []


def normalize_capi_user_data(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Chuẩn hoá + hash PII trước khi gửi Graph API. Idempotent nếu đã hash."""
    if not raw or not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    for key, val in raw.items():
        k = str(key).strip()
        if not k:
            continue
        values = list(_iter_user_data_values(val))
        if not values:
            continue
        if k in _PLAIN_USER_DATA_KEYS:
            if k == "fbp":
                hit = next((v for v in values if is_valid_meta_fbp(v)), None)
                if hit:
                    out["fbp"] = hit.strip()
            elif k == "fbc":
                hit = next((v for v in values if is_valid_meta_fbc(v)), None)
                if hit:
                    out["fbc"] = hit.strip()
            elif k == "client_ip_address":
                hit = next((ip for v in values if (ip := _valid_ip(v))), None)
                if hit:
                    out["client_ip_address"] = hit
            elif k == "client_user_agent":
                ua = values[0][:512]
                if ua:
                    out["client_user_agent"] = ua
            else:
                out[k] = values[0][:256]
            continue
        hashed = []
        for item in values:
            h = _hash_pii_value(k, item)
            if h and h not in hashed:
                hashed.append(h)
        if hashed:
            out[k] = hashed
    return out


def geo_from_address(address: str) -> Tuple[Optional[str], Optional[str]]:
    """Suy st (tỉnh) / ct (quận) từ chuỗi địa chỉ checkout."""
    parts = [fold_meta_text(p) for p in re.split(r"[,|\n]", address or "") if fold_meta_text(p)]
    st = None
    st_idx = -1
    for i, part in enumerate(parts):
        key = part
        if key.startswith("thanh pho "):
            key = key[10:]
        elif key.startswith("tp "):
            key = key[3:]
        if key in _VN_PROVINCE_FOLDED:
            st = "ho chi minh" if key in {"tphcm", "sai gon"} else key
            st_idx = i
    ct = parts[st_idx - 1] if st_idx > 0 else None
    if ct and ct == st:
        ct = None
    return ct, st


def client_ip_from_request(request: Any) -> Optional[str]:
    if request is None:
        return None
    headers = getattr(request, "headers", None) or {}
    for key in ("cf-connecting-ip", "x-real-ip"):
        raw = headers.get(key) if hasattr(headers, "get") else None
        ip = _valid_ip(str(raw or ""))
        if ip:
            return ip
    xff = headers.get("x-forwarded-for") if hasattr(headers, "get") else None
    if xff:
        first = str(xff).split(",")[0].strip()
        ip = _valid_ip(first)
        if ip:
            return ip
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client is not None else None
    return _valid_ip(str(host or ""))


def build_meta_ads_context(
    *,
    fbp: Optional[str] = None,
    fbc: Optional[str] = None,
    province: Optional[str] = None,
    district: Optional[str] = None,
    address: Optional[str] = None,
    request: Any = None,
    user_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    ctx: Dict[str, Any] = {"country": "vn"}
    fbp_s = (fbp or "").strip()
    fbc_s = (fbc or "").strip()
    if is_valid_meta_fbp(fbp_s):
        ctx["fbp"] = fbp_s
    if is_valid_meta_fbc(fbc_s):
        ctx["fbc"] = fbc_s
    st = fold_meta_text(province or "")
    ct = fold_meta_text(district or "")
    if not st or not ct:
        parsed_ct, parsed_st = geo_from_address(address or "")
        st = st or (parsed_st or "")
        ct = ct or (parsed_ct or "")
    if st:
        ctx["st"] = st
    if ct:
        ctx["ct"] = ct
    ip = client_ip_from_request(request)
    if ip:
        ctx["client_ip_address"] = ip
    ua = ""
    headers = getattr(request, "headers", None) if request is not None else None
    if headers is not None and hasattr(headers, "get"):
        ua = (headers.get("user-agent") or "").strip()[:512]
    if ua:
        ctx["client_user_agent"] = ua
    if user_id:
        ctx["external_id"] = str(int(user_id))
    return ctx if len(ctx) > 1 else ctx


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
    """user_data hashed — email/SĐT/tên/geo + fbp/fbc/IP lưu lúc checkout."""
    ud: Dict[str, Any] = {"country": "vn"}
    email = (getattr(order, "customer_email", None) or "").strip()
    if email:
        ud["em"] = email
    phone = (getattr(order, "customer_phone", None) or "").strip()
    if phone:
        ud["ph"] = phone
    fn, ln = split_vn_name(getattr(order, "customer_name", None) or "")
    if fn:
        ud["fn"] = fn
    if ln:
        ud["ln"] = ln

    ctx = getattr(order, "meta_ads_context", None) or {}
    if not isinstance(ctx, dict):
        ctx = {}
    for key in ("fbp", "fbc", "client_ip_address", "client_user_agent", "ct", "st", "external_id"):
        val = ctx.get(key)
        if val:
            ud[key] = val

    if not ud.get("ct") or not ud.get("st"):
        parsed_ct, parsed_st = geo_from_address(getattr(order, "customer_address", None) or "")
        if parsed_ct and not ud.get("ct"):
            ud["ct"] = parsed_ct
        if parsed_st and not ud.get("st"):
            ud["st"] = parsed_st

    user = getattr(order, "user", None)
    ge = gender_to_meta(getattr(user, "gender", None)) if user is not None else None
    if ge:
        ud["ge"] = ge
    db = dob_to_meta(getattr(user, "date_of_birth", None)) if user is not None else None
    if db:
        ud["db"] = db
    if not ud.get("external_id") and getattr(order, "user_id", None):
        ud["external_id"] = str(order.user_id)

    return normalize_capi_user_data(ud)


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

    normalized: List[Dict[str, Any]] = []
    for evt in events:
        row = dict(evt)
        if row.get("user_data"):
            hashed = normalize_capi_user_data(row.get("user_data") if isinstance(row.get("user_data"), dict) else {})
            if hashed:
                row["user_data"] = hashed
            else:
                row.pop("user_data", None)
        normalized.append(row)

    ver = getattr(settings, "FACEBOOK_GRAPH_API_VERSION", "v21.0")
    url = f"https://graph.facebook.com/{ver}/{pix}/events"
    try:
        r = requests.post(
            url,
            params={"access_token": access_token},
            json={"data": normalized},
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
            "Meta CAPI Purchase sent order_id=%s event_id=%s value=%s items=%s fbc=%s",
            order.id,
            evt["event_id"],
            custom_data.get("value"),
            custom_data.get("num_items"),
            "yes" if user_data.get("fbc") else "no",
        )
        return True, "ok"
    return False, str(detail)


def send_meta_purchase_for_order_id(order_id: int) -> Tuple[bool, str]:
    db = SessionLocal()
    try:
        order = (
            db.query(Order)
            .options(
                selectinload(Order.items).selectinload(OrderItem.product),
                selectinload(Order.user),
            )
            .filter(Order.id == order_id)
            .first()
        )
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
