"""
Gợi ý danh mục hero (cấp 1/2/3) theo giới tính — từ hồ sơ hoặc suy ra từ SP xem gần nhất.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.user import UserProductView

_ASPECT_RATIOS = ("portrait", "landscape", "square")

HERO_CAROUSEL_TILE_MAX = 24


def _short_display_name(name: str, max_len: int = 22) -> str:
    s = re.sub(r"\s+(Nam|Nữ)\s*$", "", (name or "").strip(), flags=re.IGNORECASE)
    if len(s) > max_len:
        return s[: max_len - 1].rstrip() + "…"
    return s

_CTR_HINTS = (
    "{count} sản phẩm đang chờ bạn",
    "Đang hot — xem ngay",
    "Cùng phong cách bạn vừa xem",
    "Mẫu mới cập nhật liên tục",
    "Đừng bỏ lỡ — săn deal",
    "Khám phá thêm hàng ngàn mẫu",
)


def _gender_suffix_from_profile(gender: Optional[str]) -> Optional[str]:
    g = (gender or "").strip().lower()
    if g in ("male", "m", "nam"):
        return " Nam"
    if g in ("female", "f", "nu", "nữ"):
        return " Nữ"
    return None


def _text_has_gender_nam(text: str) -> bool:
    t = (text or "").strip()
    if t.endswith(" Nam"):
        return True
    return re.search(r"\bnam\b", t.lower()) is not None


def _text_has_gender_nu(text: str) -> bool:
    t = (text or "").strip()
    if t.endswith(" Nữ"):
        return True
    return re.search(r"\b(nu|nữ)\b", t.lower()) is not None


def _infer_gender_suffix_from_products(products: List[Product]) -> Optional[str]:
    nam = nu = 0
    for p in products:
        blob = " ".join(
            x for x in [(p.category or ""), (p.subcategory or ""), (p.sub_subcategory or "")] if x
        )
        if _text_has_gender_nam(blob):
            nam += 1
        if _text_has_gender_nu(blob):
            nu += 1
    if nam > nu:
        return " Nam"
    if nu > nam:
        return " Nữ"
    return None


def _recent_view_product_ids(
    db: Session,
    *,
    user_id: Optional[int],
    guest_session_id: Optional[str],
    recent_limit: int,
) -> List[int]:
    cap = max(1, min(int(recent_limit), 24))
    if user_id is not None:
        rows = (
            db.query(UserProductView.product_id)
            .filter(UserProductView.user_id == user_id)
            .order_by(UserProductView.viewed_at.desc())
            .limit(cap)
            .all()
        )
        return [int(r[0]) for r in rows if r[0] is not None]
    sid = (guest_session_id or "").strip()
    if not sid:
        return []
    from app.crud import guest_behavior as guest_behavior_crud

    return guest_behavior_crud.recent_guest_view_product_ids(db, sid, limit=cap)


def _branch_matches_gender(
    suffix: str,
    category: str,
    subcategory: Optional[str],
    sub_subcategory: Optional[str],
) -> bool:
    parts = [category, subcategory or "", sub_subcategory or ""]
    if suffix == " Nam":
        return any(_text_has_gender_nam(p) for p in parts if p)
    if suffix == " Nữ":
        return any(_text_has_gender_nu(p) for p in parts if p)
    return False


def _gender_filter_clause(suffix: str):
    if suffix == " Nam":
        return or_(
            Product.category.like("% Nam"),
            Product.subcategory.like("% Nam"),
            Product.sub_subcategory.like("% Nam"),
        )
    return or_(
        Product.category.like("% Nữ"),
        Product.subcategory.like("% Nữ"),
        Product.sub_subcategory.like("% Nữ"),
    )


def _token_overlap(a: str, b: str) -> int:
    ta = {w.lower() for w in re.split(r"\W+", a) if len(w) > 2}
    tb = {w.lower() for w in re.split(r"\W+", b) if len(w) > 2}
    return len(ta & tb)


def _display_name(level: int, cat: str, sub: Optional[str], subsub: Optional[str]) -> str:
    if level == 3 and subsub:
        return subsub.strip()
    if level == 2 and sub:
        return sub.strip()
    return cat.strip()


def _aspect_ratio(key: str, index: int) -> str:
    h = sum(ord(c) for c in key) + index * 17
    return _ASPECT_RATIOS[h % len(_ASPECT_RATIOS)]


def _branch_product_query(
    db: Session,
    *,
    category: str,
    subcategory: Optional[str],
    sub_subcategory: Optional[str],
    level: int,
):
    q = db.query(Product).filter(Product.is_active.is_(True))  # noqa: E712
    q = q.filter(Product.category == category)
    if level >= 2 and subcategory:
        q = q.filter(Product.subcategory == subcategory)
    if level >= 3 and sub_subcategory:
        q = q.filter(Product.sub_subcategory == sub_subcategory)
    return q


def _sample_image_for_branch(
    db: Session,
    *,
    category: str,
    subcategory: Optional[str],
    sub_subcategory: Optional[str],
    level: int,
    viewed_product_ids: List[int],
    exclude_urls: Optional[Set[str]] = None,
) -> Optional[str]:
    """Ảnh SP đại diện — ưu tiên lượt xem, tránh trùng URL giữa các ô."""
    used = exclude_urls or set()

    def _first_unused(rows: List[Product]) -> Optional[str]:
        for row in rows:
            url = (row.main_image or "").strip()
            if url and url not in used:
                return url
        return None

    base_q = _branch_product_query(
        db,
        category=category,
        subcategory=subcategory,
        sub_subcategory=sub_subcategory,
        level=level,
    ).filter(Product.main_image.isnot(None), Product.main_image != "")

    if viewed_product_ids:
        viewed_rows = (
            base_q.filter(Product.id.in_(viewed_product_ids))
            .order_by(Product.purchases.desc().nullslast(), Product.id)
            .limit(16)
            .all()
        )
        hit = _first_unused(viewed_rows)
        if hit:
            return hit

    popular_rows = base_q.order_by(Product.purchases.desc().nullslast(), Product.id).limit(24).all()
    return _first_unused(popular_rows)


def _ctr_hint(name: str, count: int, index: int) -> str:
    tpl = _CTR_HINTS[index % len(_CTR_HINTS)]
    if "{count}" in tpl:
        return tpl.format(count=f"{count:,}".replace(",", "."))
    return tpl


def _anchor_from_products(products: List[Product], product_ids: List[int]) -> Optional[str]:
    by_id = {p.id: p for p in products}
    for pid in product_ids:
        p = by_id.get(pid)
        if not p:
            continue
        for field in (p.sub_subcategory, p.subcategory, p.category):
            if field and str(field).strip():
                return str(field).strip()
    return None


def get_hero_category_tiles(
    db: Session,
    *,
    user_id: Optional[int] = None,
    guest_session_id: Optional[str] = None,
    profile_gender: Optional[str] = None,
    recent_limit: int = 8,
    limit: int = 8,
) -> Dict[str, Any]:
    """
    Trả payload hero: tiles cấp 1/2/3 cùng giới, gợi ý CTR, tỷ lệ khung gợi ý.
    Ưu tiên giới tính hồ sơ (nếu có); không thì suy từ SP xem gần nhất.
    """
    product_ids = _recent_view_product_ids(
        db, user_id=user_id, guest_session_id=guest_session_id, recent_limit=recent_limit
    )
    viewed_products: List[Product] = []
    if product_ids:
        viewed_products = (
            db.query(Product)
            .filter(Product.id.in_(product_ids), Product.is_active.is_(True))  # noqa: E712
            .all()
        )

    profile_suffix = _gender_suffix_from_profile(profile_gender)
    inferred_suffix = _infer_gender_suffix_from_products(viewed_products)
    suffix = profile_suffix or inferred_suffix
    if not suffix:
        return {
            "tiles": [],
            "gender_label": None,
            "heading": None,
            "subtitle": None,
            "anchor_category": None,
            "source": "profile_gender" if profile_suffix else "recent_views",
        }

    gender_label = "Nam" if suffix.strip() == "Nam" else "Nữ"
    source = "profile_gender" if profile_suffix else "recent_views"

    viewed_l1: Set[str] = set()
    viewed_l2: Set[Tuple[str, str]] = set()
    viewed_l3: Set[Tuple[str, str, str]] = set()
    viewed_sub_names: List[str] = []
    for p in viewed_products:
        c = (p.category or "").strip()
        s = (p.subcategory or "").strip()
        ss = (p.sub_subcategory or "").strip()
        if c:
            viewed_l1.add(c)
        if c and s:
            viewed_l2.add((c, s))
            viewed_sub_names.append(s)
        if c and s and ss:
            viewed_l3.add((c, s, ss))
            viewed_sub_names.append(ss)

    anchor = _anchor_from_products(viewed_products, product_ids)
    purchase_sum = func.coalesce(func.sum(Product.purchases), 0)
    gender_clause = _gender_filter_clause(suffix)
    active = Product.is_active.is_(True)  # noqa: E712

    candidates: List[Dict[str, Any]] = []

    def add_candidate(level: int, cat: str, sub: Optional[str], subsub: Optional[str], cnt: int, purch: int):
        cat = (cat or "").strip()
        if not cat:
            return
        sub = (sub or "").strip() or None
        subsub = (subsub or "").strip() or None
        if not _branch_matches_gender(suffix, cat, sub, subsub):
            return
        name = _display_name(level, cat, sub, subsub)
        if not name:
            return
        key = f"{level}|{cat}|{sub or ''}|{subsub or ''}"
        score = float(cnt) + float(purch) * 0.05
        if cat in viewed_l1:
            score += 80
        if sub and (cat, sub) in viewed_l2:
            score += 60
        if subsub and (cat, sub or "", subsub) in viewed_l3:
            score -= 40
        for vn in viewed_sub_names:
            score += _token_overlap(name, vn) * 12
        candidates.append(
            {
                "level": level,
                "name": name,
                "category": cat,
                "subcategory": sub,
                "sub_subcategory": subsub,
                "product_count": int(cnt),
                "purchases": int(purch),
                "score": score,
                "key": key,
            }
        )

    l1_rows = (
        db.query(
            Product.category.label("cat"),
            func.count(Product.id).label("cnt"),
            purchase_sum.label("purch"),
        )
        .filter(active, gender_clause, Product.category.isnot(None), Product.category != "")
        .group_by(Product.category)
        .order_by(purchase_sum.desc(), func.count(Product.id).desc())
        .limit(40)
        .all()
    )
    for r in l1_rows:
        add_candidate(1, r.cat, None, None, int(r.cnt or 0), int(r.purch or 0))

    l2_rows = (
        db.query(
            Product.category.label("cat"),
            Product.subcategory.label("sub"),
            func.count(Product.id).label("cnt"),
            purchase_sum.label("purch"),
        )
        .filter(
            active,
            gender_clause,
            Product.category.isnot(None),
            Product.category != "",
            Product.subcategory.isnot(None),
            Product.subcategory != "",
        )
        .group_by(Product.category, Product.subcategory)
        .order_by(purchase_sum.desc(), func.count(Product.id).desc())
        .limit(60)
        .all()
    )
    for r in l2_rows:
        add_candidate(2, r.cat, r.sub, None, int(r.cnt or 0), int(r.purch or 0))

    l3_rows = (
        db.query(
            Product.category.label("cat"),
            Product.subcategory.label("sub"),
            Product.sub_subcategory.label("subsub"),
            func.count(Product.id).label("cnt"),
            purchase_sum.label("purch"),
        )
        .filter(
            active,
            gender_clause,
            Product.sub_subcategory.isnot(None),
            Product.sub_subcategory != "",
        )
        .group_by(Product.category, Product.subcategory, Product.sub_subcategory)
        .order_by(purchase_sum.desc(), func.count(Product.id).desc())
        .limit(150)
        .all()
    )
    for r in l3_rows:
        add_candidate(3, r.cat, r.sub, r.subsub, int(r.cnt or 0), int(r.purch or 0))

    seen_keys: Set[str] = set()
    unique: List[Dict[str, Any]] = []
    for c in sorted(candidates, key=lambda x: x["score"], reverse=True):
        if c["key"] in seen_keys:
            continue
        seen_keys.add(c["key"])
        unique.append(c)

    by_level: Dict[int, List[Dict[str, Any]]] = {1: [], 2: [], 3: []}
    for c in unique:
        lv = c["level"]
        if lv in by_level:
            by_level[lv].append(c)

    target = max(8, min(int(limit), HERO_CAROUSEL_TILE_MAX))
    picked: List[Dict[str, Any]] = []
    half = max(4, target // 2)
    picked.extend(by_level[2][:half])
    picked.extend(by_level[3][:half])
    picked_keys = {p["key"] for p in picked}
    for c in unique:
        if c["level"] not in (2, 3):
            continue
        if len(picked) >= target:
            break
        if c["key"] not in picked_keys:
            picked.append(c)
            picked_keys.add(c["key"])

    used_images: Set[str] = set()
    tiles: List[Dict[str, Any]] = []
    for i, c in enumerate(picked[:target]):
        img = _sample_image_for_branch(
            db,
            category=c["category"],
            subcategory=c.get("subcategory"),
            sub_subcategory=c.get("sub_subcategory"),
            level=int(c["level"]),
            viewed_product_ids=product_ids,
            exclude_urls=used_images,
        )
        if img:
            used_images.add(img)
        tiles.append(
            {
                "level": c["level"],
                "name": c["name"],
                "short_name": _short_display_name(c["name"]),
                "category": c["category"],
                "subcategory": c["subcategory"],
                "sub_subcategory": c["sub_subcategory"],
                "product_count": c["product_count"],
                "purchases": c["purchases"],
                "ctr_hint": _ctr_hint(c["name"], c["product_count"], i),
                "aspect_ratio": _aspect_ratio(c["key"], i),
                "image_url": img,
            }
        )

    with_img = [t for t in tiles if t.get("image_url")]
    without_img = [t for t in tiles if not t.get("image_url")]
    display_tiles = (with_img + without_img)[:target]

    if anchor:
        heading = f"Đồ {gender_label}"
        subtitle = "Nhóm & chi tiết theo sở thích của bạn"
    else:
        heading = f"Danh mục {gender_label}"
        subtitle = "Nhóm & chi tiết — vuốt xem thêm"

    return {
        "tiles": display_tiles,
        "gender_label": gender_label,
        "heading": heading,
        "subtitle": subtitle,
        "anchor_category": anchor,
        "source": source,
    }


def _gender_rank_for_name(name: str, prefer_suffix: str) -> int:
    """0 = ưu tiên, 1 = trung tính, 2 = đẩy xuống."""
    n = (name or "").strip()
    if not n:
        return 1
    if prefer_suffix == " Nam":
        if _text_has_gender_nam(n) and not _text_has_gender_nu(n):
            return 0
        if _text_has_gender_nu(n) and not _text_has_gender_nam(n):
            return 2
        return 1
    if prefer_suffix == " Nữ":
        if _text_has_gender_nu(n) and not _text_has_gender_nam(n):
            return 0
        if _text_has_gender_nam(n) and not _text_has_gender_nu(n):
            return 2
        return 1
    return 1


def sort_category_tree_by_gender(
    tree: List[Dict[str, Any]], prefer_suffix: Optional[str]
) -> List[Dict[str, Any]]:
    """Sắp xếp L1/L2/L3: danh mục khớp giới ưu tiên (Nam hoặc Nữ) lên trước."""
    suffix = (prefer_suffix or "").strip()
    if suffix == "Nam":
        suffix = " Nam"
    elif suffix == "Nữ" or suffix.lower() in ("nu", "nữ"):
        suffix = " Nữ"
    elif suffix not in (" Nam", " Nữ"):
        return tree
    if not tree:
        return tree

    def _sort_level(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        indexed = list(enumerate(nodes))
        ordered = sorted(
            indexed,
            key=lambda t: (
                _gender_rank_for_name(t[1].get("name") or "", suffix),
                t[0],
                (t[1].get("name") or "").lower(),
            ),
        )
        out: List[Dict[str, Any]] = []
        for _, node in ordered:
            copy = dict(node)
            children = copy.get("children")
            if isinstance(children, list) and children and isinstance(children[0], dict):
                copy["children"] = _sort_level(children)
            out.append(copy)
        return out

    return _sort_level(tree)


def infer_category_gender_priority(
    db: Session,
    *,
    user_id: Optional[int] = None,
    guest_session_id: Optional[str] = None,
    profile_gender: Optional[str] = None,
    recent_limit: int = 8,
) -> Dict[str, Any]:
    """
    Suy giới tính ưu tiên menu danh mục: hồ sơ (nếu có) hoặc tối đa 8 SP xem gần nhất.
    """
    profile_suffix = _gender_suffix_from_profile(profile_gender)
    product_ids = _recent_view_product_ids(
        db,
        user_id=user_id,
        guest_session_id=guest_session_id,
        recent_limit=recent_limit,
    )
    viewed_products: List[Product] = []
    if product_ids:
        viewed_products = (
            db.query(Product)
            .filter(Product.id.in_(product_ids), Product.is_active.is_(True))  # noqa: E712
            .all()
        )
    inferred_suffix = _infer_gender_suffix_from_products(viewed_products)
    suffix = profile_suffix or inferred_suffix
    source = "profile_gender" if profile_suffix else "recent_views"
    if not suffix:
        return {
            "gender_suffix": None,
            "gender_label": None,
            "source": source,
            "recent_view_count": len(product_ids),
        }
    gender_label = "Nam" if suffix.strip() == "Nam" else "Nữ"
    return {
        "gender_suffix": gender_label,
        "gender_label": gender_label,
        "source": source,
        "recent_view_count": len(product_ids),
    }
