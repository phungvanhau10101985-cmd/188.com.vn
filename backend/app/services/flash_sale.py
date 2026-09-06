"""
Flash sale cá nhân hóa:
- Nhóm = SP cùng shop Trung Quốc VÀ cùng danh mục cấp 3 của 8 SP khách xem gần nhất.
- Mỗi lượt quay tối đa 12 SP trong nhóm đó (trộn đều các cặp shop+cấp 3).
- Không lấy SP cùng shop nhưng khác danh mục cấp 3.
% giảm 8–12 (ổn định trong lượt ~10 phút). Hết lượt mất giảm. Không áp dụng hàng kho thanh lý.
"""
from __future__ import annotations

import hashlib
import math
import random
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.product import Product
from app.utils.ttl_cache import cache as ttl_cache

_VN_TZ = timezone(timedelta(hours=7))

FLASH_SALE_EVENT_LABEL = "Flash sale"
FLASH_SALE_KIND = "flash"
FLASH_SALE_RECENT_VIEWS = 8
FLASH_SALE_MAX_COUNT = 12
FLASH_SALE_MIN_PERCENT = 8
FLASH_SALE_MAX_PERCENT = 12
FLASH_SALE_SLOT_MINUTES = 10
FLASH_SALE_CANDIDATE_LIMIT = 240
FLASH_SALE_MIN_SHOW = 4

_identity_ctx: ContextVar[Tuple[Optional[int], Optional[str]]] = ContextVar(
    "flash_sale_identity", default=(None, None)
)


def set_flash_sale_identity(
    user_id: Optional[int], guest_session_id: Optional[str]
) -> None:
    sid = (guest_session_id or "").strip() or None
    _identity_ctx.set((user_id, sid))


def current_flash_sale_identity() -> Tuple[Optional[int], Optional[str]]:
    return _identity_ctx.get()


@dataclass(frozen=True)
class FlashSaleSlot:
    key: str
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True)
class FlashSaleAssignment:
    product_ids: List[int]
    percent_by_id: Dict[int, int]
    slot: FlashSaleSlot

    def percent_for(self, product_id: Optional[int]) -> Optional[int]:
        if product_id is None:
            return None
        return self.percent_by_id.get(int(product_id))


def now_vn(now: Optional[datetime] = None) -> datetime:
    if now is None:
        return datetime.now(_VN_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=_VN_TZ)
    return now.astimezone(_VN_TZ)


def resolve_flash_slot(now: Optional[datetime] = None) -> FlashSaleSlot:
    current = now_vn(now)
    midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = int((current - midnight).total_seconds())
    slot_seconds = FLASH_SALE_SLOT_MINUTES * 60
    index = elapsed // slot_seconds
    start = midnight + timedelta(seconds=index * slot_seconds)
    end = start + timedelta(seconds=slot_seconds)
    day_end = midnight + timedelta(days=1)
    if end > day_end:
        end = day_end
    key = f"{start.date().isoformat()}:{index}"
    return FlashSaleSlot(key=key, start_at=start, end_at=end)


def _identity_key(user_id: Optional[int], guest_session_id: Optional[str]) -> Optional[str]:
    if user_id is not None:
        return f"user:{int(user_id)}"
    sid = (guest_session_id or "").strip()
    if sid:
        return f"guest:{sid}"
    return None


def _stable_seed(*parts: Any) -> int:
    raw = "|".join(str(p) for p in parts)
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def flash_percent_for_product(product_id: int, slot_key: str) -> int:
    span = FLASH_SALE_MAX_PERCENT - FLASH_SALE_MIN_PERCENT + 1
    return FLASH_SALE_MIN_PERCENT + (_stable_seed(slot_key, int(product_id)) % span)


def pick_even_shop_products(
    shop_queues: Dict[str, List[Any]],
    shop_order: Sequence[str],
    *,
    target: int,
    seed: int,
) -> List[Any]:
    """
    Round-robin đều giữa các shop — không tua hết shop A rồi mới tới shop B.
    Mỗi shop tối đa ceil(target / số shop) món; shop hết hàng thì shop khác bù cho đủ target.
    """
    target = max(0, int(target))
    if target <= 0 or not shop_order:
        return []

    rng = random.Random(int(seed) & 0xFFFFFFFF)
    queues: Dict[str, List[Any]] = {}
    order: List[str] = []
    for shop in shop_order:
        key = (shop or "").strip().lower()
        if not key or key in queues:
            continue
        items = list(shop_queues.get(shop) or shop_queues.get(key) or [])
        rng.shuffle(items)
        if items:
            queues[key] = items
            order.append(key)
    if not queues:
        return []

    cap = max(1, math.ceil(target / len(order)))
    counts = {shop: 0 for shop in order}
    picked: List[Any] = []
    seen_ids: set[int] = set()

    def _take(shop: str) -> bool:
        queue = queues.get(shop)
        if not queue:
            return False
        while queue:
            item = queue.pop(0)
            pid = getattr(item, "id", None)
            if pid is not None:
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)
            picked.append(item)
            counts[shop] += 1
            return True
        return False

    while len(picked) < target:
        progressed = False
        for shop in order:
            if len(picked) >= target:
                break
            if counts[shop] >= cap:
                continue
            if _take(shop):
                progressed = True
        if progressed:
            continue
        leftover = [shop for shop in order if queues.get(shop)]
        if not leftover:
            break
        for shop in leftover:
            if len(picked) >= target:
                break
            _take(shop)
    return picked[:target]


def apply_flash_percent_to_price(
    list_price: float,
    percent: int,
    *,
    countdown_to: Optional[datetime] = None,
) -> Dict[str, Any]:
    base = max(0.0, float(list_price or 0))
    pct = max(FLASH_SALE_MIN_PERCENT, min(FLASH_SALE_MAX_PERCENT, int(percent)))
    savings = round(base * pct / 100.0)
    sale_price = max(0.0, round(base - savings))
    countdown = countdown_to.isoformat() if countdown_to is not None else None
    return {
        "kind": FLASH_SALE_KIND,
        "list_price": base,
        "display_price": float(sale_price),
        "savings_amount": float(savings),
        "percent": float(pct),
        "phase": "active",
        "event_label": FLASH_SALE_EVENT_LABEL,
        "event_date": None,
        "countdown_to": countdown,
    }


def _same_shop_key(product: Any) -> str:
    return (getattr(product, "shop_name_chinese", None) or "").strip().lower()


def _level3_key(product: Any) -> str:
    return (getattr(product, "sub_subcategory", None) or "").strip().lower()


def _shop_l3_pair(product: Any) -> Optional[Tuple[str, str]]:
    shop = _same_shop_key(product)
    level3 = _level3_key(product)
    if not shop or not level3:
        return None
    return shop, level3


def _group_queue_key(shop: str, level3: str) -> str:
    return f"{shop}||{level3}"


def viewed_shop_l3_pairs(products_in_view_order: Iterable[Any]) -> List[Tuple[str, str]]:
    """Cặp (shop TQ, danh mục cấp 3) từ 8 SP vừa xem — giữ thứ tự xem, bỏ trùng."""
    pairs: List[Tuple[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for product in products_in_view_order:
        if product is None or _is_warehouse_row(product):
            continue
        pair = _shop_l3_pair(product)
        if pair is None or pair in seen:
            continue
        seen.add(pair)
        pairs.append(pair)
    return pairs


def _is_warehouse_row(product: Any) -> bool:
    return bool(getattr(product, "is_warehouse_clearance", False))


def _fetch_recent_view_ids(
    db: Session,
    *,
    user_id: Optional[int],
    guest_session_id: Optional[str],
) -> List[int]:
    from app.crud.user import get_recent_view_product_ids

    return get_recent_view_product_ids(
        db,
        user_id=user_id,
        guest_session_id=guest_session_id,
        limit=FLASH_SALE_RECENT_VIEWS,
    )


def _load_products_by_ids(db: Session, product_ids: Sequence[int]) -> Dict[int, Product]:
    ids = [int(pid) for pid in product_ids if pid is not None]
    if not ids:
        return {}
    rows = db.query(Product).filter(Product.id.in_(ids)).all()
    return {int(p.id): p for p in rows}


def _candidate_products_for_shop_l3_pairs(
    db: Session, pairs: Sequence[Tuple[str, str]]
) -> List[Product]:
    clean = [(shop, level3) for shop, level3 in pairs if shop and level3]
    if not clean:
        return []
    from app.services.warehouse_clearance import apply_catalog_visibility_filter

    shop_cn_norm = func.lower(func.trim(Product.shop_name_chinese))
    l3_norm = func.lower(func.trim(Product.sub_subcategory))
    pair_filters = [
        and_(shop_cn_norm == shop, l3_norm == level3) for shop, level3 in clean
    ]
    query = apply_catalog_visibility_filter(
        db.query(Product).filter(
            or_(*pair_filters),
            Product.is_active == True,  # noqa: E712
        )
    )
    return query.order_by(Product.purchases.desc(), Product.id.desc()).limit(
        FLASH_SALE_CANDIDATE_LIMIT
    ).all()


def _build_assignment(
    db: Session,
    *,
    user_id: Optional[int],
    guest_session_id: Optional[str],
    slot: FlashSaleSlot,
) -> FlashSaleAssignment:
    viewed_ids = _fetch_recent_view_ids(
        db, user_id=user_id, guest_session_id=guest_session_id
    )
    if not viewed_ids:
        return FlashSaleAssignment(product_ids=[], percent_by_id={}, slot=slot)

    viewed = _load_products_by_ids(db, viewed_ids)
    pairs = viewed_shop_l3_pairs(viewed.get(pid) for pid in viewed_ids)
    if not pairs:
        return FlashSaleAssignment(product_ids=[], percent_by_id={}, slot=slot)

    group_order = [_group_queue_key(shop, level3) for shop, level3 in pairs]
    group_queues: Dict[str, List[Product]] = {key: [] for key in group_order}
    allowed = set(pairs)
    candidates = _candidate_products_for_shop_l3_pairs(db, pairs)
    for product in candidates:
        if _is_warehouse_row(product):
            continue
        pair = _shop_l3_pair(product)
        if pair is None or pair not in allowed:
            continue
        group_queues[_group_queue_key(*pair)].append(product)

    identity = _identity_key(user_id, guest_session_id) or "anon"
    seed = _stable_seed(identity, slot.key)
    available = sum(len(q) for q in group_queues.values())
    target = min(FLASH_SALE_MAX_COUNT, available)
    picked = pick_even_shop_products(group_queues, group_order, target=target, seed=seed)
    product_ids = [int(p.id) for p in picked if getattr(p, "id", None) is not None]
    percent_by_id = {pid: flash_percent_for_product(pid, slot.key) for pid in product_ids}
    return FlashSaleAssignment(
        product_ids=product_ids,
        percent_by_id=percent_by_id,
        slot=slot,
    )


def _cache_key(identity: str, slot_key: str) -> str:
    return f"flash-sale:{identity}:{slot_key}"


def get_flash_sale_assignment(
    db: Session,
    *,
    user_id: Optional[int] = None,
    guest_session_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> FlashSaleAssignment:
    uid, sid = user_id, guest_session_id
    if uid is None and not (sid or "").strip():
        ctx_uid, ctx_sid = current_flash_sale_identity()
        uid, sid = ctx_uid, ctx_sid

    identity = _identity_key(uid, sid)
    slot = resolve_flash_slot(now)
    if identity is None:
        return FlashSaleAssignment(product_ids=[], percent_by_id={}, slot=slot)

    ttl = max(5.0, (slot.end_at - now_vn(now)).total_seconds())

    def _fetch() -> Dict[str, Any]:
        built = _build_assignment(db, user_id=uid, guest_session_id=sid, slot=slot)
        return {
            "product_ids": built.product_ids,
            "percent_by_id": {str(k): v for k, v in built.percent_by_id.items()},
            "slot_key": built.slot.key,
            "slot_start": built.slot.start_at.isoformat(),
            "slot_end": built.slot.end_at.isoformat(),
        }

    cached = ttl_cache.get_or_fetch(_cache_key(identity, slot.key), ttl, _fetch)
    product_ids = [int(pid) for pid in (cached.get("product_ids") or [])]
    if not product_ids:
        # Chưa đủ lượt xem → không khóa lượt rỗng, lần sau (đã xem SP) sẽ dựng lại.
        ttl_cache.invalidate(_cache_key(identity, slot.key))
        return FlashSaleAssignment(product_ids=[], percent_by_id={}, slot=slot)
    percents = {
        int(pid): int(pct)
        for pid, pct in (cached.get("percent_by_id") or {}).items()
    }
    return FlashSaleAssignment(
        product_ids=product_ids,
        percent_by_id=percents,
        slot=slot,
    )


def apply_flash_sale_to_payload(
    payload: Dict[str, Any],
    assignment: Optional[FlashSaleAssignment],
    *,
    product: Any = None,
    product_id: Optional[int] = None,
) -> None:
    """Gắn flash lên dict SP. Hàng kho: không đổi. Flash thay sale lịch trên đúng mã đó."""
    if assignment is None or not assignment.product_ids:
        return
    if _is_warehouse_row(product) or payload.get("is_warehouse_clearance"):
        return
    pid = product_id
    if pid is None:
        pid = getattr(product, "id", None)
    if pid is None:
        try:
            pid = int(payload.get("id"))
        except (TypeError, ValueError):
            return
    percent = assignment.percent_for(int(pid) if pid is not None else None)
    if not percent:
        return

    base = float(
        payload.get("original_price")
        or (payload.get("site_sale") or {}).get("list_price")
        or payload.get("price")
        or 0
    )
    if base <= 0:
        return
    pricing = apply_flash_percent_to_price(
        base, percent, countdown_to=assignment.slot.end_at
    )
    payload["flash_sale"] = pricing
    payload["site_sale"] = pricing
    payload["original_price"] = base
    payload["price"] = pricing["display_price"]


def enrich_product_payloads_with_flash_sale(
    db: Session,
    rows: Iterable[Tuple[Any, Dict[str, Any]]],
    *,
    user: Any = None,
    guest_session_id: Optional[str] = None,
) -> None:
    uid = getattr(user, "id", None) if user is not None else None
    assignment = get_flash_sale_assignment(
        db, user_id=uid, guest_session_id=guest_session_id
    )
    if not assignment.percent_by_id:
        return
    for product, payload in rows:
        if not isinstance(payload, dict):
            continue
        apply_flash_sale_to_payload(payload, assignment, product=product)


def list_flash_sale_products(
    db: Session,
    *,
    user_id: Optional[int],
    guest_session_id: Optional[str],
    serialize_products,
    user: Any = None,
) -> Dict[str, Any]:
    assignment = get_flash_sale_assignment(
        db, user_id=user_id, guest_session_id=guest_session_id
    )
    slot = assignment.slot
    empty = {
        "products": [],
        "countdown_to": slot.end_at.isoformat(),
        "slot_start_at": slot.start_at.isoformat(),
        "slot_end_at": slot.end_at.isoformat(),
        "slot_key": slot.key,
    }
    if len(assignment.product_ids) < FLASH_SALE_MIN_SHOW:
        return empty

    by_id = _load_products_by_ids(db, assignment.product_ids)
    ordered = [by_id[pid] for pid in assignment.product_ids if pid in by_id]
    sellable = [p for p in ordered if not _is_warehouse_row(p) and getattr(p, "is_active", True)]
    if len(sellable) < FLASH_SALE_MIN_SHOW:
        return empty

    serialized = serialize_products(db, sellable, user)
    return {
        "products": serialized,
        "countdown_to": slot.end_at.isoformat(),
        "slot_start_at": slot.start_at.isoformat(),
        "slot_end_at": slot.end_at.isoformat(),
        "slot_key": slot.key,
    }
