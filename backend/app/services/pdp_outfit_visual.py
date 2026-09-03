"""Lớp 2: vector ảnh nhẹ (màu từ ảnh/metadata) + NanoAI image-search trong cửa đã lọc."""
from __future__ import annotations

import io
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urljoin

import requests
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)


def _color_families_from_product(row: Any) -> set[str]:
    from app.services.pdp_outfit_suggestions import color_families_from_product as _fn

    return _fn(row)


VISUAL_VERSION = "v1"
VECTOR_DIM = 8
IMAGE_FETCH_TIMEOUT = 1.6
IMAGE_MAX_BYTES = 1_200_000
NANO_IMAGE_TIMEOUT = 2.5
NANO_IMAGE_LIMIT = 20
NANO_CACHE_TTL_SEC = 12 * 60

_NEUTRALS = frozenset({"black", "white", "gray", "beige", "brown", "silver", "gold"})
_COMPLEMENT = frozenset(
    {
        frozenset({"black", "white"}),
        frozenset({"black", "beige"}),
        frozenset({"black", "brown"}),
        frozenset({"blue", "brown"}),
        frozenset({"blue", "white"}),
        frozenset({"blue", "beige"}),
        frozenset({"red", "beige"}),
        frozenset({"red", "black"}),
        frozenset({"pink", "gray"}),
        frozenset({"pink", "white"}),
        frozenset({"green", "beige"}),
        frozenset({"green", "brown"}),
        frozenset({"navy", "beige"}),
    }
)

# r, g, b, luma, sat, warmth, dark, chroma — cùng không gian với vector ảnh.
_COLOR_PROTOS: Dict[str, List[float]] = {
    "black": [0.08, 0.08, 0.08, 0.08, 0.04, 0.50, 0.94, 0.04],
    "white": [0.94, 0.94, 0.93, 0.94, 0.04, 0.50, 0.06, 0.04],
    "beige": [0.86, 0.78, 0.64, 0.78, 0.22, 0.72, 0.22, 0.20],
    "brown": [0.45, 0.28, 0.16, 0.32, 0.48, 0.82, 0.68, 0.30],
    "blue": [0.18, 0.28, 0.52, 0.30, 0.50, 0.22, 0.62, 0.34],
    "green": [0.22, 0.42, 0.28, 0.34, 0.40, 0.38, 0.58, 0.28],
    "red": [0.72, 0.16, 0.18, 0.34, 0.68, 0.78, 0.52, 0.52],
    "pink": [0.90, 0.55, 0.62, 0.66, 0.38, 0.70, 0.28, 0.32],
    "gray": [0.52, 0.52, 0.54, 0.52, 0.06, 0.48, 0.48, 0.06],
    "gold": [0.78, 0.64, 0.28, 0.64, 0.52, 0.84, 0.30, 0.42],
    "silver": [0.72, 0.74, 0.76, 0.74, 0.08, 0.42, 0.26, 0.08],
    "orange": [0.86, 0.42, 0.16, 0.52, 0.70, 0.88, 0.38, 0.55],
    "purple": [0.46, 0.24, 0.58, 0.36, 0.48, 0.32, 0.58, 0.36],
    "yellow": [0.90, 0.80, 0.22, 0.76, 0.62, 0.80, 0.20, 0.50],
}

_NANO_MEM: Dict[int, Tuple[float, Dict[int, float]]] = {}
_TABLE_READY = False
_WARM_LOCK = threading.Lock()
_WARM_INFLIGHT: set[int] = set()


def _ensure_table() -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    try:
        from app.db.session import engine
        from app.models.product_outfit_visual import ProductOutfitVisual

        ProductOutfitVisual.__table__.create(engine, checkfirst=True)
        _TABLE_READY = True
    except Exception:
        logger.debug("outfit visual table ensure failed", exc_info=True)


@dataclass
class OutfitVisualContext:
    anchor_vector: List[float]
    nano_scores: Dict[int, float] = field(default_factory=dict)


def _zero() -> List[float]:
    return [0.0] * VECTOR_DIM


def _mean_vectors(vectors: Sequence[List[float]]) -> List[float]:
    if not vectors:
        return _zero()
    n = float(len(vectors))
    return [sum(v[i] for v in vectors) / n for i in range(VECTOR_DIM)]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def vector_from_color_families(families: Iterable[str]) -> List[float]:
    vecs = [_COLOR_PROTOS[f] for f in families if f in _COLOR_PROTOS]
    return _mean_vectors(vecs) if vecs else _zero()


def vector_from_product_meta(row: Any) -> List[float]:
    return vector_from_color_families(_color_families_from_product(row))


def color_harmony(anchor_fams: set[str], cand_fams: set[str]) -> float:
    if not anchor_fams or not cand_fams:
        return 0.35
    if anchor_fams & cand_fams:
        return 0.55
    for a in anchor_fams:
        for c in cand_fams:
            if frozenset({a, c}) in _COMPLEMENT:
                return 0.88
    if (anchor_fams & _NEUTRALS) or (cand_fams & _NEUTRALS):
        return 0.78
    return 0.28


def vector_from_image_bytes(data: bytes) -> Optional[List[float]]:
    if not data:
        return None
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        im = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None
    im.thumbnail((48, 48))
    pixels = list(im.getdata())
    if not pixels:
        return None
    kept: List[Tuple[int, int, int]] = []
    for r, g, b in pixels:
        if r > 242 and g > 242 and b > 242:
            continue
        if r < 12 and g < 12 and b < 12 and (r + g + b) < 20:
            # viền/nền đen studio — giữ một ít, bỏ phần lớn
            if len(kept) % 4 != 0:
                continue
        kept.append((r, g, b))
    sample = kept or pixels
    n = float(len(sample))
    rs = sum(p[0] for p in sample) / n / 255.0
    gs = sum(p[1] for p in sample) / n / 255.0
    bs = sum(p[2] for p in sample) / n / 255.0
    luma = 0.2126 * rs + 0.7152 * gs + 0.0722 * bs
    mx = max(rs, gs, bs)
    mn = min(rs, gs, bs)
    sat = 0.0 if mx < 1e-6 else (mx - mn) / mx
    warmth = max(0.0, min(1.0, 0.5 + (rs - bs) * 0.7))
    dark = 1.0 - luma
    chroma = mx - mn
    return [rs, gs, bs, luma, sat, warmth, dark, chroma]


def first_product_image_url(row: Any) -> Optional[str]:
    candidates: List[str] = []
    main = str(getattr(row, "main_image", None) or "").strip()
    if main:
        candidates.append(main)
    for field in ("images", "gallery"):
        raw = getattr(row, field, None)
        if isinstance(raw, list):
            for item in raw:
                s = str(item or "").strip()
                if s:
                    candidates.append(s)
    colors = getattr(row, "colors", None)
    if isinstance(colors, list):
        for entry in colors:
            if isinstance(entry, dict):
                for key in ("img", "image", "url"):
                    s = str(entry.get(key) or "").strip()
                    if s:
                        candidates.append(s)
    for url in candidates:
        if url.lower() in {"null", "none", "nan", "-"}:
            continue
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            site = (getattr(settings, "SITE_PUBLIC_URL", None) or "https://188.com.vn").rstrip("/")
            return urljoin(site + "/", url.lstrip("/"))
        if url.startswith(("http://", "https://")):
            return url
    return None


def fetch_image_bytes(url: str) -> Optional[bytes]:
    if not url:
        return None
    try:
        r = requests.get(
            url,
            timeout=IMAGE_FETCH_TIMEOUT,
            stream=True,
            headers={"User-Agent": "188-outfit-visual/1.0"},
        )
        if r.status_code != 200:
            return None
        buf = r.raw.read(IMAGE_MAX_BYTES + 1, decode_content=True)
        if not buf or len(buf) > IMAGE_MAX_BYTES:
            return None
        return buf
    except Exception:
        logger.debug("outfit visual fetch failed url=%s", url[:120], exc_info=True)
        return None


def _own_session():
    from app.db.session import SessionLocal

    return SessionLocal()


def _load_cached_row(product_id: int):
    if not product_id:
        return None
    sess = None
    try:
        from app.models.product_outfit_visual import ProductOutfitVisual

        _ensure_table()
        sess = _own_session()
        row = sess.query(ProductOutfitVisual).filter(ProductOutfitVisual.product_id == product_id).first()
        if row is not None:
            sess.expunge(row)
        return row
    except Exception:
        if sess is not None:
            try:
                sess.rollback()
            except Exception:
                pass
        logger.debug("outfit visual cache read failed id=%s", product_id, exc_info=True)
        return None
    finally:
        if sess is not None:
            sess.close()


def _upsert_cache(
    db: Optional[Session],
    product_id: int,
    *,
    source_url: Optional[str],
    vector: Optional[List[float]],
    nano_hit_ids: Optional[List[int]] = None,
) -> None:
    if not product_id:
        return
    # Session riêng — không commit transaction request PDP.
    try:
        from app.models.product_outfit_visual import ProductOutfitVisual

        _ensure_table()
        sess = _own_session()
        try:
            row = sess.query(ProductOutfitVisual).filter(ProductOutfitVisual.product_id == product_id).first()
            if row is None:
                row = ProductOutfitVisual(product_id=product_id, model_version=VISUAL_VERSION)
                sess.add(row)
            if source_url is not None:
                row.source_url = source_url
            if vector is not None:
                row.vector = list(vector)
            if nano_hit_ids is not None:
                row.nano_hit_ids = list(nano_hit_ids)
            row.model_version = VISUAL_VERSION
            sess.commit()
        finally:
            sess.close()
    except Exception:
        logger.debug("outfit visual cache write failed id=%s", product_id, exc_info=True)


def resolve_product_vector(row: Any, db: Optional[Session] = None, *, allow_fetch: bool = False) -> List[float]:
    del db  # cache dùng session riêng, không đụng transaction PDP
    meta = vector_from_product_meta(row)
    pid = int(getattr(row, "id", 0) or 0)
    url = first_product_image_url(row)
    cached = _load_cached_row(pid)
    if cached and isinstance(cached.vector, list) and len(cached.vector) == VECTOR_DIM:
        if not url or cached.source_url == url:
            return [float(x) for x in cached.vector]
    if allow_fetch and url:
        raw = fetch_image_bytes(url)
        extracted = vector_from_image_bytes(raw) if raw else None
        if extracted:
            _upsert_cache(None, pid, source_url=url, vector=extracted)
            return extracted
    return meta


def _nano_mem_get(product_id: int) -> Optional[Dict[int, float]]:
    hit = _NANO_MEM.get(product_id)
    if not hit:
        return None
    exp, scores = hit
    if exp <= time.time():
        _NANO_MEM.pop(product_id, None)
        return None
    return scores


def _lookup_nano_local_ids(products: List[Any], exclude_id: int) -> Dict[int, float]:
    from sqlalchemy import func, or_

    from app.models.product import Product as ProductModel

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
        return {}
    conds = []
    if ids:
        conds.append(ProductModel.product_id.in_(ids))
    if codes:
        lowers = list({c.lower() for c in codes})
        conds.append(func.lower(ProductModel.code).in_(lowers))
    sess = None
    extra = []
    try:
        sess = _own_session()
        extra = (
            sess.query(ProductModel.id, ProductModel.product_id, ProductModel.code)
            .filter(or_(*conds), ProductModel.is_active.is_(True))
            .all()
        )
    except Exception:
        if sess is not None:
            try:
                sess.rollback()
            except Exception:
                pass
        logger.debug("outfit nano id lookup failed", exc_info=True)
        extra = []
    finally:
        if sess is not None:
            sess.close()
    extra = [r for r in extra if int(getattr(r, "id", 0) or 0) != exclude_id]
    by_inv: Dict[str, int] = {}
    by_code: Dict[str, int] = {}
    for row in extra:
        pk = int(getattr(row, "id", 0) or 0)
        inv = str(getattr(row, "product_id", "") or "").strip()
        code = str(getattr(row, "code", "") or "").strip().lower()
        if pk and inv:
            by_inv[inv] = pk
        if pk and code:
            by_code[code] = pk
    out: Dict[int, float] = {}
    for p in products:
        if not isinstance(p, dict):
            continue
        inv = str(p.get("inventory_id") or "").strip()
        sku = str(p.get("sku") or "").strip().lower()
        pk = by_inv.get(inv) or by_code.get(sku)
        if not pk:
            continue
        try:
            score = float(p.get("score") or 0.5)
        except (TypeError, ValueError):
            score = 0.5
        out[pk] = max(out.get(pk, 0.0), score)
    return out


def nano_image_scores_for_anchor(
    db: Optional[Session],
    anchor: Any,
    *,
    allow_network: bool = False,
) -> Dict[int, float]:
    del db
    pid = int(getattr(anchor, "id", 0) or 0)
    if not pid:
        return {}
    mem = _nano_mem_get(pid)
    if mem is not None:
        return mem
    cached = _load_cached_row(pid)
    if cached and isinstance(cached.nano_hit_ids, list) and cached.nano_hit_ids:
        scores: Dict[int, float] = {}
        for x in cached.nano_hit_ids:
            try:
                scores[int(x)] = 0.6
            except (TypeError, ValueError):
                continue
        if scores:
            _NANO_MEM[pid] = (time.time() + NANO_CACHE_TTL_SEC, scores)
            return scores
    if not allow_network:
        return {}
    try:
        from app.services import nanoai_partner_search as nanoai

        if not nanoai.is_configured():
            return {}
        url = first_product_image_url(anchor)
        raw = fetch_image_bytes(url) if url else None
        if not raw:
            return {}
        filename = "outfit.jpg"
        if url and ".png" in url.lower():
            filename = "outfit.png"
        status, body = nanoai.post_image_search(
            raw,
            filename,
            "image/jpeg",
            NANO_IMAGE_LIMIT,
            timeout=NANO_IMAGE_TIMEOUT,
        )
        if status != 200 or not isinstance(body, dict):
            _NANO_MEM[pid] = (time.time() + 90, {})
            return {}
        hits = body.get("products")
        if not isinstance(hits, list):
            return {}
        scores = _lookup_nano_local_ids(hits, pid)
        _NANO_MEM[pid] = (time.time() + NANO_CACHE_TTL_SEC, scores)
        _upsert_cache(None, pid, source_url=url, vector=None, nano_hit_ids=list(scores.keys()))
        return scores
    except Exception:
        logger.exception("NanoAI outfit image-search failed id=%s", pid)
        return {}


def build_visual_context(
    db: Optional[Session],
    anchor: Any,
    *,
    allow_network: bool = False,
) -> OutfitVisualContext:
    vec = resolve_product_vector(anchor, db, allow_fetch=allow_network)
    nano = nano_image_scores_for_anchor(db, anchor, allow_network=allow_network)
    return OutfitVisualContext(anchor_vector=vec, nano_scores=nano)


def _nano_cache_ready(product_id: int) -> bool:
    if _nano_mem_get(product_id) is not None:
        return True
    cached = _load_cached_row(product_id)
    return bool(cached and isinstance(cached.nano_hit_ids, list) and cached.nano_hit_ids)


def _warm_outfit_visual(product_id: int) -> None:
    from app.models.product import Product as ProductModel

    sess = None
    try:
        sess = _own_session()
        row = sess.get(ProductModel, product_id) if hasattr(sess, "get") else sess.query(ProductModel).get(product_id)
        if row is None:
            return
        resolve_product_vector(row, allow_fetch=True)
        nano_image_scores_for_anchor(None, row, allow_network=True)
        from app.services.pdp_outfit_suggestions import persist_outfit_picks_for_product

        persist_outfit_picks_for_product(product_id)
    except Exception:
        logger.exception("outfit visual warm failed id=%s", product_id)
    finally:
        if sess is not None:
            sess.close()


def _outfit_visual_warm_enabled() -> bool:
    return bool(getattr(settings, "OUTFIT_VISUAL_WARM", False))


def _has_outfit_visual_row(product_id: int) -> bool:
    """True khi đã có cache visual — không warm lại."""
    if not product_id:
        return False
    sess = None
    try:
        from app.models.product_outfit_visual import ProductOutfitVisual

        _ensure_table()
        sess = _own_session()
        return (
            sess.query(ProductOutfitVisual.product_id)
            .filter(ProductOutfitVisual.product_id == product_id)
            .first()
            is not None
        )
    except Exception:
        if sess is not None:
            try:
                sess.rollback()
            except Exception:
                pass
        logger.debug("outfit visual row probe failed id=%s", product_id, exc_info=True)
        return False
    finally:
        if sess is not None:
            sess.close()


def schedule_outfit_visual_warm(product_id: int) -> None:
    """NanoAI / fetch ảnh chạy nền — không chặn PDP.

    Tắt mặc định (OUTFIT_VISUAL_WARM=0). Khi bật, chỉ warm sản phẩm chưa có row DB.
    /pdp-outfit + persist picks không phụ thuộc hàm này.
    """
    if not _outfit_visual_warm_enabled():
        return
    pid = int(product_id or 0)
    if not pid or _nano_cache_ready(pid) or _has_outfit_visual_row(pid):
        return
    with _WARM_LOCK:
        if pid in _WARM_INFLIGHT:
            return
        _WARM_INFLIGHT.add(pid)

    def _run() -> None:
        try:
            _warm_outfit_visual(pid)
        finally:
            with _WARM_LOCK:
                _WARM_INFLIGHT.discard(pid)

    threading.Thread(target=_run, daemon=True, name=f"outfit-nano-{pid}").start()


def visual_rank_score(anchor: Any, candidate: Any, ctx: Optional[OutfitVisualContext]) -> float:
    a_fams = _color_families_from_product(anchor)
    c_fams = _color_families_from_product(candidate)
    harmony = color_harmony(a_fams, c_fams)
    cand_vec = vector_from_product_meta(candidate)
    anchor_vec = ctx.anchor_vector if ctx and ctx.anchor_vector else vector_from_product_meta(anchor)
    sim = cosine(anchor_vec, cand_vec)
    return 0.55 * sim + 0.45 * harmony


def nano_boost(candidate: Any, ctx: Optional[OutfitVisualContext]) -> float:
    if not ctx or not ctx.nano_scores:
        return 0.0
    pk = int(getattr(candidate, "id", 0) or 0)
    return float(ctx.nano_scores.get(pk) or 0.0)
