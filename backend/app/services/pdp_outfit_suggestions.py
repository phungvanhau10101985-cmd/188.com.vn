"""Gợi ý món phối cho PDP — cửa họ phối cat3 + vector ảnh trong từng slot."""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app import crud
from app.services.pdp_outfit_pair_families import (
    family_pair_reason,
    infer_pair_family_from_row,
    listing_queries_for_family,
    pair_family_compatible,
)
from app.services.pdp_outfit_roles import (
    OutfitGender,
    OutfitRole,
    ROLE_LABELS,
    SLOT_LABELS,
    classify_anchor,
    infer_outfit_role,
    row_matches_slot_keywords,
    slots_for_anchor,
    target_cat1_names,
)
from app.services.pdp_outfit_visual import (
    OutfitVisualContext,
    build_visual_context,
    nano_boost,
    schedule_outfit_visual_warm,
    visual_rank_score,
)

logger = logging.getLogger(__name__)

PRICE_BAND_VND = 300_000
SLOT_FETCH_LIMIT = 60
NANO_FILL_THRESHOLD = 4
CACHE_TTL_SEC = 12 * 60
PICKS_TTL_SEC = 7 * 24 * 3600
STORED_LIMIT = 6
MIN_RELATED_SCORE = 2

_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_CACHE_VER = "v8"
_PICKS_TABLE_READY = False


def invalidate_outfit_cache_for_product(product_id: int) -> None:
    prefix = f"{_CACHE_VER}:{int(product_id or 0)}"
    for key in list(_CACHE):
        if key == prefix or key.startswith(prefix + ":"):
            _CACHE.pop(key, None)


def persisted_outfit_is_fresh(algo_version: Optional[str], computed_at: Optional[datetime]) -> bool:
    if (algo_version or "") != _CACHE_VER or computed_at is None:
        return False
    if computed_at.tzinfo is None:
        computed_at = computed_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - computed_at
    return 0 <= age.total_seconds() < PICKS_TTL_SEC


def filter_stored_outfit_payload(
    payload: Dict[str, Any],
    *,
    only_slot: Optional[str] = None,
    limit: int = STORED_LIMIT,
) -> Dict[str, Any]:
    if not payload.get("applicable"):
        return payload
    slots = list(payload.get("slots") or [])
    if only_slot:
        slots = [s for s in slots if s.get("id") == only_slot]
    cap = max(1, int(limit or STORED_LIMIT))
    trimmed = []
    for slot in slots:
        items = list(slot.get("items") or [])[:cap]
        if not items:
            continue
        trimmed.append({**slot, "items": items})
    out = dict(payload)
    out["slots"] = trimmed
    if not trimmed:
        return {
            "applicable": False,
            "reason": payload.get("reason") or "no_slots",
            "anchor": None,
            "slots": [],
        }
    return out


def _own_session():
    from app.db.session import SessionLocal

    return SessionLocal()


def _ensure_picks_table() -> None:
    global _PICKS_TABLE_READY
    if _PICKS_TABLE_READY:
        return
    try:
        from app.db.session import engine
        from app.models.product_outfit_pick import ProductOutfitPick

        ProductOutfitPick.__table__.create(engine, checkfirst=True)
        _PICKS_TABLE_READY = True
    except Exception:
        logger.debug("outfit picks table ensure failed", exc_info=True)


def load_persisted_outfit_picks(product_id: int) -> Optional[Dict[str, Any]]:
    pid = int(product_id or 0)
    if not pid:
        return None
    sess = None
    try:
        from app.models.product_outfit_pick import ProductOutfitPick

        _ensure_picks_table()
        sess = _own_session()
        row = sess.query(ProductOutfitPick).filter(ProductOutfitPick.product_id == pid).first()
        if row is None or not persisted_outfit_is_fresh(row.algo_version, row.computed_at):
            return None
        payload = row.payload if isinstance(row.payload, dict) else None
        return dict(payload) if payload else None
    except Exception:
        if sess is not None:
            try:
                sess.rollback()
            except Exception:
                pass
        logger.debug("outfit picks read failed id=%s", pid, exc_info=True)
        return None
    finally:
        if sess is not None:
            sess.close()


def save_persisted_outfit_picks(
    product_id: int,
    payload: Dict[str, Any],
    *,
    visual_ready: bool = False,
) -> None:
    pid = int(product_id or 0)
    if not pid or not isinstance(payload, dict):
        return
    sess = None
    try:
        from app.models.product_outfit_pick import ProductOutfitPick

        _ensure_picks_table()
        sess = _own_session()
        row = sess.query(ProductOutfitPick).filter(ProductOutfitPick.product_id == pid).first()
        now = datetime.now(timezone.utc)
        if row is None:
            row = ProductOutfitPick(product_id=pid)
            sess.add(row)
        row.algo_version = _CACHE_VER
        row.payload = dict(payload)
        row.visual_ready = bool(visual_ready)
        row.computed_at = now
        sess.commit()
    except Exception:
        if sess is not None:
            try:
                sess.rollback()
            except Exception:
                pass
        logger.debug("outfit picks write failed id=%s", pid, exc_info=True)
    finally:
        if sess is not None:
            sess.close()


def persist_outfit_picks_for_product(product_id: int) -> None:
    """Tính lại bộ phối (NanoAI đã cache nếu có) rồi ghi DB."""
    from app.models.product import Product as ProductModel
    from app.services.pdp_outfit_visual import _nano_cache_ready

    pid = int(product_id or 0)
    if not pid:
        return
    sess = None
    try:
        sess = _own_session()
        row = sess.get(ProductModel, pid) if hasattr(sess, "get") else sess.query(ProductModel).get(pid)
        if row is None:
            return
        payload = _compute_outfit_slot_picks(sess, row, limit=STORED_LIMIT)
        save_persisted_outfit_picks(pid, payload, visual_ready=_nano_cache_ready(pid))
        invalidate_outfit_cache_for_product(pid)
        _CACHE[f"{_CACHE_VER}:{pid}"] = (time.time() + CACHE_TTL_SEC, payload)
    except Exception:
        logger.exception("persist outfit picks failed id=%s", pid)
    finally:
        if sess is not None:
            sess.close()

_COLOR_ALIASES: Tuple[Tuple[str, str], ...] = (
    ("đen tuyền", "black"),
    ("đen", "black"),
    ("black", "black"),
    ("trắng", "white"),
    ("white", "white"),
    ("kem", "beige"),
    ("be ", "beige"),
    ("beige", "beige"),
    ("nâu", "brown"),
    ("brown", "brown"),
    ("da bò", "brown"),
    ("xanh navy", "blue"),
    ("navy", "blue"),
    ("xanh dương", "blue"),
    ("blue", "blue"),
    ("xanh lá", "green"),
    ("green", "green"),
    ("đỏ", "red"),
    ("red", "red"),
    ("hồng", "pink"),
    ("pink", "pink"),
    ("xám", "gray"),
    ("grey", "gray"),
    ("gray", "gray"),
    ("vàng gold", "gold"),
    ("gold", "gold"),
    ("bạc", "silver"),
    ("silver", "silver"),
    ("cam", "orange"),
    ("orange", "orange"),
    ("tím", "purple"),
    ("purple", "purple"),
    ("vàng", "yellow"),
)


def _cell(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    return s


def _norm_key(value: Any) -> Optional[str]:
    text = _cell(value)
    if not text:
        return None
    return " ".join(text.lower().split())


def color_families_from_product(row: Any) -> set[str]:
    chunks: List[str] = []
    for field in (getattr(row, "name", None), getattr(row, "color", None)):
        t = _cell(field)
        if t:
            chunks.append(t)
    raw_colors = getattr(row, "colors", None)
    if isinstance(raw_colors, list):
        for item in raw_colors:
            if isinstance(item, dict):
                n = item.get("name") or item.get("value")
                if n:
                    chunks.append(str(n))
            elif isinstance(item, str):
                chunks.append(item)
    blob = " ".join(chunks).lower()
    found: set[str] = set()
    for needle, fam in _COLOR_ALIASES:
        if needle.strip() and needle in blob:
            found.add(fam)
    return found


_VIBE_KEYS: Dict[str, Tuple[str, ...]] = {
    "formal": (
        "công sở",
        "cong so",
        "đi làm",
        "di lam",
        "giày tây",
        "giay tay",
        "oxford",
        "loafer",
        "derby",
        "quần âu",
        "quan au",
        "sơ mi",
        "so mi",
        "vest",
        "blazer",
        "dự tiệc",
        "du tiec",
        "thắt lưng da",
        "that lung da",
        "da bóng",
        "formal",
        "office",
    ),
    "sport": (
        "thể thao",
        "the thao",
        "sneaker",
        "chạy bộ",
        "chay bo",
        "gym",
        "training",
        "sport",
        "giày chạy",
        "giay chay",
    ),
    "party": (
        "dự tiệc",
        "du tiec",
        "cao gót",
        "cao got",
        "đính đá",
        "dinh da",
        "kim sa",
        "party",
        "cocktail",
    ),
    "casual": (
        "casual",
        "dạo phố",
        "dao pho",
        "hằng ngày",
        "hang ngay",
        "áo thun",
        "ao thun",
        "hoodie",
        "jean",
        "jeans",
        "short",
        "canvas",
        "tote",
    ),
}

_VIBE_CONFLICT = {("formal", "sport"), ("sport", "formal"), ("party", "sport"), ("sport", "party")}

_STOP_TOKENS = {
    "nam",
    "nữ",
    "nu",
    "màu",
    "mau",
    "size",
    "cm",
    "new",
    "hot",
    "sale",
    "cao",
    "cấp",
    "cap",
    "hàng",
    "hang",
    "loại",
    "loai",
}

_SLOT_Q: Dict[str, Dict[str, str]] = {
    "top": {"formal": "sơ mi vest blazer áo công sở", "sport": "áo thể thao", "casual": "áo thun hoodie", "party": "áo dự tiệc"},
    "bottom": {"formal": "quần âu", "sport": "quần thể thao", "casual": "quần jean short", "party": "quần âu"},
    "dress": {"formal": "đầm công sở", "sport": "đầm", "casual": "váy liền", "party": "đầm dự tiệc"},
    "shoes": {"formal": "giày tây loafer oxford", "sport": "giày sneaker thể thao", "casual": "giày sneaker", "party": "giày cao gót"},
    "bag": {"formal": "túi da công sở", "sport": "túi", "casual": "túi tote", "party": "túi dự tiệc"},
    "accessory": {"formal": "thắt lưng da", "sport": "mũ", "casual": "mũ khăn", "party": "trang sức"},
}


def _product_blob(row: Any) -> str:
    bits: List[str] = []
    for field in (
        "name",
        "style",
        "occasion",
        "material",
        "color",
        "category",
        "subcategory",
        "sub_subcategory",
    ):
        t = _cell(getattr(row, field, None))
        if t:
            bits.append(t)
    return " ".join(bits).lower()


def infer_vibes(row: Any) -> set[str]:
    blob = _product_blob(row)
    found: set[str] = set()
    for vibe, keys in _VIBE_KEYS.items():
        if any(k in blob for k in keys):
            found.add(vibe)
    return found


def infer_materials(row: Any) -> set[str]:
    blob = _product_blob(row)
    found: set[str] = set()
    if any(k in blob for k in ("da bò", "da that", "da thật", "da ", "leather")):
        found.add("leather")
    if "canvas" in blob:
        found.add("canvas")
    if any(k in blob for k in ("vải", "vai ")):
        found.add("fabric")
    if any(k in blob for k in ("nhựa", "nhua", "cao su")):
        found.add("synthetic")
    if any(k in blob for k in ("lụa", "lua ")):
        found.add("silk")
    return found


def name_tokens(row: Any) -> set[str]:
    raw = _norm_key(getattr(row, "name", None)) or ""
    toks = set()
    for part in re.split(r"[^\wàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]+", raw, flags=re.I):
        t = part.strip().lower()
        if len(t) >= 3 and t not in _STOP_TOKENS:
            toks.add(t)
    return toks


def _floor_price(value: Any) -> Optional[int]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not v or v <= 0:
        return None
    return int(v)


def score_outfit_candidate(
    anchor: Any,
    candidate: Any,
    slot: Optional[OutfitRole] = None,
) -> Tuple[int, float, List[str]]:
    """Trả (điểm nguyên, purchases, reasons). Điểm 0 = không đủ liên quan."""
    a_fam = infer_pair_family_from_row(anchor)
    c_fam = infer_pair_family_from_row(candidate)
    family_locked = bool(slot and a_fam and c_fam)
    if family_locked and not pair_family_compatible(a_fam, c_fam, slot):
        return 0, 0.0, []

    a_vibes = infer_vibes(anchor)
    c_vibes = infer_vibes(candidate)
    if a_vibes and c_vibes:
        if any((a, b) in _VIBE_CONFLICT for a in a_vibes for b in c_vibes) and not (a_vibes & c_vibes):
            return 0, 0.0, []

    score = 0
    reasons: List[str] = []
    related = False
    if family_locked:
        score += 3
        related = True
        fam_reason = family_pair_reason(a_fam, slot) if slot else None
        if fam_reason:
            reasons.append(fam_reason)

    a_style = _norm_key(getattr(anchor, "style", None))
    c_style = _norm_key(getattr(candidate, "style", None))
    if a_style and c_style and a_style == c_style:
        score += 3
        related = True
        reasons.append(f"Cùng phong cách {_cell(getattr(anchor, 'style', None))}")

    a_occ = _norm_key(getattr(anchor, "occasion", None))
    c_occ = _norm_key(getattr(candidate, "occasion", None))
    if a_occ and c_occ and a_occ == c_occ:
        score += 3
        related = True
        reasons.append(f"Cùng dịp {_cell(getattr(anchor, 'occasion', None))}")

    shared_vibe = a_vibes & c_vibes
    if shared_vibe:
        score += 3
        related = True
        label = {
            "formal": "Cùng phong cách công sở / lịch sự",
            "sport": "Cùng phong cách thể thao",
            "party": "Cùng dịp dự tiệc",
            "casual": "Cùng phong cách dạo phố",
        }
        for v in ("formal", "party", "sport", "casual"):
            if v in shared_vibe:
                reasons.append(label[v])
                break

    a_colors = color_families_from_product(anchor)
    c_colors = color_families_from_product(candidate)
    color_hit = bool(a_colors and c_colors and a_colors & c_colors)
    if color_hit:
        score += 1
        reasons.append("Gần màu")

    mats = infer_materials(anchor) & infer_materials(candidate)
    if mats:
        score += 1
        if color_hit:
            related = True
        reasons.append("Cùng chất liệu")

    tokens = name_tokens(anchor) & name_tokens(candidate)
    if len(tokens) >= 2:
        score += 1
        related = True

    a_price = _floor_price(getattr(anchor, "price", None))
    c_price = _floor_price(getattr(candidate, "price", None))
    if a_price is not None and c_price is not None and abs(a_price - c_price) <= PRICE_BAND_VND:
        score += 1
        reasons.append("Cùng tầm giá")

    if not related and color_hit and score >= MIN_RELATED_SCORE:
        related = True
    if family_locked:
        related = True
        if score < MIN_RELATED_SCORE:
            score = MIN_RELATED_SCORE
    if not related or score < MIN_RELATED_SCORE:
        return 0, 0.0, []

    purchases = 0.0
    try:
        purchases = float(getattr(candidate, "purchases", 0) or 0)
    except (TypeError, ValueError):
        purchases = 0.0
    return score, purchases, reasons[:2]


def _slot_query_text(slot: OutfitRole, gender: OutfitGender, anchor: Any) -> str:
    parts: List[str] = []
    family_qs = listing_queries_for_family(infer_pair_family_from_row(anchor), slot)
    if family_qs:
        parts.append(family_qs[0])
    vibes = infer_vibes(anchor)
    slot_q = _SLOT_Q.get(slot) or {}
    if not family_qs:
        for v in ("formal", "party", "sport", "casual"):
            if v in vibes and slot_q.get(v):
                parts.append(slot_q[v])
                break
    if not parts:
        parts.append(SLOT_LABELS.get(slot, slot))
    if gender in ("Nam", "Nữ"):
        parts.append(gender.lower())
    style = _cell(getattr(anchor, "style", None))
    if style:
        parts.append(style)
    colors = color_families_from_product(anchor)
    color_vi = {
        "black": "đen",
        "white": "trắng",
        "brown": "nâu",
        "beige": "kem",
        "blue": "xanh",
        "red": "đỏ",
        "pink": "hồng",
        "gray": "xám",
        "gold": "vàng",
        "silver": "bạc",
    }
    for fam, word in color_vi.items():
        if fam in colors:
            parts.append(word)
            break
    occ = _cell(getattr(anchor, "occasion", None))
    if occ:
        parts.append(occ)
    return " ".join(parts)


def _listing_rows(
    db: Session,
    category: str,
    exclude_id: int,
    *,
    style: Optional[str] = None,
    q: Optional[str] = None,
    filter_style_tag: Optional[str] = None,
    limit: int = SLOT_FETCH_LIMIT,
) -> List[Any]:
    try:
        result = crud.product.get_products(
            db,
            skip=0,
            limit=limit,
            category=category,
            style=style,
            q=q,
            filter_style_tag=filter_style_tag,
            is_active=True,
            skip_total=True,
            sort="purchases_desc",
        )
    except Exception:
        logger.exception("outfit listing failed category=%s q=%s", category, q)
        try:
            db.rollback()
        except Exception:
            pass
        return []
    products = result.get("products") if isinstance(result, dict) else None
    rows = list(products or [])
    return [r for r in rows if int(getattr(r, "id", 0) or 0) != exclude_id]


def _collect_slot_rows(
    db: Session,
    slot: OutfitRole,
    gender: OutfitGender,
    anchor: Any,
    exclude_id: int,
) -> List[Any]:
    collected: List[Any] = []
    style = _cell(getattr(anchor, "style", None))
    family_qs = listing_queries_for_family(infer_pair_family_from_row(anchor), slot)
    queries = list(family_qs) if family_qs else [_slot_query_text(slot, gender, anchor)]
    if slot == "dress":
        for extra in ("đầm", "váy liền", "chân váy"):
            if extra not in queries:
                queries.append(extra)
    style_tag = "Váy" if slot == "dress" else None
    for cat1 in target_cat1_names(slot, gender):
        if style_tag:
            collected.extend(_listing_rows(db, cat1, exclude_id, filter_style_tag=style_tag, limit=40))
        if style:
            collected.extend(_listing_rows(db, cat1, exclude_id, style=style, limit=40))
        for q in queries:
            if q:
                collected.extend(_listing_rows(db, cat1, exclude_id, q=q, limit=24))
    collected = [r for r in _dedupe_rows(collected) if _candidate_passes_slot(slot, r, anchor)]
    if len(collected) < 8:
        for cat1 in target_cat1_names(slot, gender):
            if slot == "dress":
                collected.extend(_listing_rows(db, cat1, exclude_id, q="váy", limit=SLOT_FETCH_LIMIT))
                collected.extend(_listing_rows(db, cat1, exclude_id, filter_style_tag="Váy", limit=SLOT_FETCH_LIMIT))
            else:
                collected.extend(_listing_rows(db, cat1, exclude_id, limit=SLOT_FETCH_LIMIT))
        collected = [r for r in _dedupe_rows(collected) if _candidate_passes_slot(slot, r, anchor)]
    return collected


def _candidate_passes_slot(slot: OutfitRole, row: Any, anchor: Optional[Any] = None) -> bool:
    if not row_matches_slot_keywords(
        slot,
        getattr(row, "category", None),
        getattr(row, "subcategory", None),
        getattr(row, "sub_subcategory", None),
        getattr(row, "name", None),
    ):
        return False
    if anchor is None:
        return True
    return pair_family_compatible(
        infer_pair_family_from_row(anchor),
        infer_pair_family_from_row(row),
        slot,
    )


def _soft_match_count(anchor: Any, rows: Sequence[Any], slot: Optional[OutfitRole] = None) -> int:
    a_style = _norm_key(getattr(anchor, "style", None))
    a_occ = _norm_key(getattr(anchor, "occasion", None))
    a_fam = infer_pair_family_from_row(anchor)
    n = 0
    for row in rows:
        if a_style and _norm_key(getattr(row, "style", None)) == a_style:
            n += 1
            continue
        if a_occ and _norm_key(getattr(row, "occasion", None)) == a_occ:
            n += 1
            continue
        if slot and a_fam and pair_family_compatible(a_fam, infer_pair_family_from_row(row), slot):
            if infer_pair_family_from_row(row):
                n += 1
    return n


def _lookup_nano_rows(db: Session, products: List[Any], exclude_id: int) -> List[Any]:
    ids: List[str] = []
    codes: List[str] = []
    for p in products:
        if not isinstance(p, dict):
            continue
        inv = str(p.get("inventory_id") or "").strip()
        sku = str(p.get("sku") or "").strip()
        if inv:
            ids.append(inv)
        if sku:
            codes.append(sku)
    if not ids and not codes:
        return []
    from sqlalchemy import func, or_

    from app.models.product import Product as ProductModel

    conds = []
    if ids:
        conds.append(ProductModel.product_id.in_(ids))
    if codes:
        lowers = list({c.lower() for c in codes})
        conds.append(func.lower(ProductModel.code).in_(lowers))
    if not conds:
        return []
    rows = db.query(ProductModel).filter(or_(*conds), ProductModel.is_active.is_(True)).all()
    return [r for r in rows if int(getattr(r, "id", 0) or 0) != exclude_id]


def _maybe_nano_fill(
    db: Session,
    *,
    slot: OutfitRole,
    gender: OutfitGender,
    anchor: Any,
    local_rows: List[Any],
) -> List[Any]:
    if _soft_match_count(anchor, local_rows, slot) >= NANO_FILL_THRESHOLD:
        return []
    try:
        from app.services import nanoai_partner_search as nanoai

        if not nanoai.is_configured():
            return []
        q = _slot_query_text(slot, gender, anchor)
        if len(q) < 2:
            return []
        status, body = nanoai.post_text_search(q, 12, timeout=3)
        if status != 200 or not isinstance(body, dict):
            return []
        hits = body.get("products")
        if not isinstance(hits, list):
            return []
        extra = _lookup_nano_rows(db, hits, int(getattr(anchor, "id", 0) or 0))
        extra = [r for r in extra if _candidate_passes_slot(slot, r, anchor)]
        extra = [r for r in extra if infer_outfit_role(
            getattr(r, "category", None),
            getattr(r, "subcategory", None),
            getattr(r, "sub_subcategory", None),
            getattr(r, "name", None),
        ) in (slot, None) or slot in ("shoes", "bag", "accessory")]
        return extra
    except Exception:
        logger.exception("NanoAI outfit fill failed slot=%s", slot)
        return []


def _dedupe_rows(rows: Sequence[Any]) -> List[Any]:
    seen: set[int] = set()
    out: List[Any] = []
    for row in rows:
        pk = int(getattr(row, "id", 0) or 0)
        if not pk or pk in seen:
            continue
        seen.add(pk)
        out.append(row)
    return out


def _rank_slot(
    anchor: Any,
    rows: Sequence[Any],
    limit: int,
    *,
    slot: OutfitRole,
    visual_ctx: Optional[OutfitVisualContext] = None,
) -> List[Dict[str, Any]]:
    ranked: List[Tuple[int, float, float, float, List[str], Any]] = []
    for row in rows:
        sc, purchases, reasons = score_outfit_candidate(anchor, row, slot=slot)
        vis = visual_rank_score(anchor, row, visual_ctx)
        nano = nano_boost(row, visual_ctx)
        ranked.append((sc, nano, vis, purchases, reasons, row))
    ranked.sort(key=lambda t: (t[0], t[1], t[2], t[3]), reverse=True)
    scored = [t for t in ranked if t[0] > 0]
    pool = scored if len(scored) >= min(3, limit) else ranked
    items: List[Dict[str, Any]] = []
    for sc, _nano, vis, _purchases, reasons, row in pool[:limit]:
        shown = list(reasons[:1])
        if not shown and vis >= 0.7:
            shown = ["Cùng tông / hòa màu"]
        items.append(
            {
                "id": int(row.id),
                "match_score": sc,
                "reasons": shown,
            }
        )
    return items


def _compute_outfit_slot_picks(
    db: Session,
    anchor: Any,
    *,
    limit: int = STORED_LIMIT,
) -> Dict[str, Any]:
    cat = getattr(anchor, "category", None)
    role, gender, reason = classify_anchor(
        cat,
        getattr(anchor, "subcategory", None),
        getattr(anchor, "sub_subcategory", None),
        getattr(anchor, "name", None),
    )
    if role is None:
        return {
            "applicable": False,
            "reason": reason or "not_fashion",
            "anchor": None,
            "slots": [],
        }

    wanted = slots_for_anchor(role, gender)
    exclude_id = int(getattr(anchor, "id", 0) or 0)
    try:
        visual_ctx = build_visual_context(db, anchor, allow_network=False)
    except Exception:
        logger.exception("Outfit visual context failed id=%s", exclude_id)
        visual_ctx = None
    slot_picks: List[Dict[str, Any]] = []
    for slot in wanted:
        collected = _collect_slot_rows(db, slot, gender, anchor, exclude_id)
        collected = [r for r in _dedupe_rows(collected) if _candidate_passes_slot(slot, r, anchor)]
        picks = _rank_slot(anchor, collected, limit, slot=slot, visual_ctx=visual_ctx)
        if picks:
            listing_params: Dict[str, str] = {}
            names = target_cat1_names(slot, gender)
            if names:
                listing_params["category"] = names[0]
            style = _cell(getattr(anchor, "style", None))
            if style:
                listing_params["style"] = style
            family_qs = listing_queries_for_family(infer_pair_family_from_row(anchor), slot)
            if family_qs:
                listing_params["q"] = family_qs[0]
            slot_picks.append(
                {
                    "id": slot,
                    "label": SLOT_LABELS[slot],
                    "listing_params": listing_params,
                    "items": picks,
                }
            )
    if not slot_picks:
        return {
            "applicable": False,
            "reason": "no_slots",
            "anchor": None,
            "slots": [],
        }
    return {
        "applicable": True,
        "reason": None,
        "anchor": {
            "id": exclude_id,
            "role": role,
            "role_label": ROLE_LABELS[role],
            "gender": gender,
            "title": f"Phối với {ROLE_LABELS[role]} này",
        },
        "slots": slot_picks,
    }


def build_outfit_slot_picks(
    db: Session,
    anchor: Any,
    *,
    limit: int = 6,
    only_slot: Optional[str] = None,
) -> Dict[str, Any]:
    exclude_id = int(getattr(anchor, "id", 0) or 0)
    cache_key = f"{_CACHE_VER}:{exclude_id}"
    now = time.time()
    cached = _CACHE.get(cache_key)
    payload: Optional[Dict[str, Any]] = cached[1] if cached and cached[0] > now else None
    if payload is None:
        payload = load_persisted_outfit_picks(exclude_id)
        if payload is not None:
            _CACHE[cache_key] = (now + CACHE_TTL_SEC, payload)
    if payload is None:
        payload = _compute_outfit_slot_picks(db, anchor, limit=STORED_LIMIT)
        from app.services.pdp_outfit_visual import _nano_cache_ready

        save_persisted_outfit_picks(
            exclude_id,
            payload,
            visual_ready=_nano_cache_ready(exclude_id),
        )
        _CACHE[cache_key] = (now + CACHE_TTL_SEC, payload)
        if len(_CACHE) > 400:
            expired = [k for k, (exp, _) in _CACHE.items() if exp <= now]
            for k in expired:
                _CACHE.pop(k, None)

    schedule_outfit_visual_warm(exclude_id)
    return filter_stored_outfit_payload(payload, only_slot=only_slot, limit=limit)


def assemble_outfit_response(
    db: Session,
    slot_payload: Dict[str, Any],
    *,
    serialize_rows,
) -> Dict[str, Any]:
    """Gắn object product storefront vào từng item (không cache — giá theo user)."""
    if not slot_payload.get("applicable"):
        return {
            "applicable": False,
            "reason": slot_payload.get("reason") or "not_fashion",
            "anchor": None,
            "slots": [],
        }
    ids: List[int] = []
    for slot in slot_payload.get("slots") or []:
        for item in slot.get("items") or []:
            try:
                ids.append(int(item["id"]))
            except (KeyError, TypeError, ValueError):
                continue
    rows = crud.product.get_storefront_products_by_ids(db, ids, is_active=True) if ids else []
    by_id = {int(r.id): r for r in rows}
    ordered = [by_id[i] for i in ids if i in by_id]
    serialized = serialize_rows(ordered)
    ser_by_id = {}
    for row, payload in zip(ordered, serialized):
        if isinstance(payload, dict):
            ser_by_id[int(row.id)] = payload

    slots = []
    for slot in slot_payload.get("slots") or []:
        items = []
        for item in slot.get("items") or []:
            pk = int(item.get("id") or 0)
            product = ser_by_id.get(pk)
            if not product:
                continue
            items.append(
                {
                    "product": product,
                    "match_score": item.get("match_score") or 0,
                    "reasons": list(item.get("reasons") or [])[:1],
                }
            )
        if items:
            slots.append(
                {
                    "id": slot["id"],
                    "label": slot["label"],
                    "listing_params": slot.get("listing_params") or {},
                    "items": items,
                }
            )
    if not slots:
        return {
            "applicable": False,
            "reason": "no_slots",
            "anchor": None,
            "slots": [],
        }
    return {
        "applicable": True,
        "reason": None,
        "anchor": slot_payload.get("anchor"),
        "slots": slots,
    }
