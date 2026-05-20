"""
Cache nhóm danh mục hero trang chủ: 2 nhóm Nam + 2 nhóm Nữ (mỗi nhóm ~8 tile),
xếp hạng theo tổng lượt xem SP (user + khách). Đọc DB O(1) — không GROUP BY nặng mỗi request.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.crud import category_hero_suggestions as hero
from app.models.guest_behavior import GuestProductView
from app.models.home_hero_category_group import HomeHeroCategoryGroup
from app.models.product import Product
from app.models.user import UserProductView

_log = logging.getLogger(__name__)

TILES_PER_GROUP = 8
GENDERS = ("Nam", "Nữ")
GROUP_INDICES = (1, 2)


def _gender_suffix(label: str) -> str:
    return " Nam" if (label or "").strip() == "Nam" else " Nữ"


def _aggregate_product_view_weights(db: Session) -> Dict[int, int]:
    out: Dict[int, int] = {}
    for model in (UserProductView, GuestProductView):
        rows = (
            db.query(model.product_id, func.coalesce(func.sum(model.view_count), 0).label("v"))
            .group_by(model.product_id)
            .all()
        )
        for r in rows:
            pid = int(r[0]) if r[0] is not None else 0
            if pid <= 0:
                continue
            out[pid] = out.get(pid, 0) + int(r.v or 0)
    return out


def _branch_key(level: int, cat: str, sub: Optional[str], subsub: Optional[str]) -> str:
    return f"{level}|{cat}|{sub or ''}|{subsub or ''}"


def _collect_branch_candidates_for_gender(
    db: Session,
    *,
    gender_label: str,
    view_weights: Dict[int, int],
) -> List[Dict[str, Any]]:
    suffix = _gender_suffix(gender_label)
    gender_clause = hero._gender_filter_clause(suffix)
    active = Product.is_active.is_(True)  # noqa: E712

    if not view_weights:
        return _collect_branch_candidates_from_catalog(db, gender_label=gender_label)

    pids = list(view_weights.keys())
    chunk = 800
    candidates: Dict[str, Dict[str, Any]] = {}

    def _touch(level: int, cat: str, sub: Optional[str], subsub: Optional[str], add_score: float):
        cat = (cat or "").strip()
        if not cat:
            return
        sub = (sub or "").strip() or None
        subsub = (subsub or "").strip() or None
        if not hero._branch_matches_gender(suffix, cat, sub, subsub):
            return
        name = hero._display_name(level, cat, sub, subsub)
        if not name:
            return
        key = _branch_key(level, cat, sub, subsub)
        if level not in (2, 3):
            return
        row = candidates.get(key)
        if not row:
            row = {
                "level": level,
                "name": name,
                "category": cat,
                "subcategory": sub,
                "sub_subcategory": subsub,
                "product_count": 0,
                "purchases": 0,
                "score": 0.0,
                "key": key,
            }
            candidates[key] = row
        row["score"] += add_score

    for i in range(0, len(pids), chunk):
        batch = pids[i : i + chunk]
        products = (
            db.query(Product)
            .filter(Product.id.in_(batch), active, gender_clause)
            .all()
        )
        for p in products:
            w = float(view_weights.get(p.id, 0))
            if w <= 0:
                continue
            c = (p.category or "").strip()
            s = (p.subcategory or "").strip()
            ss = (p.sub_subcategory or "").strip()
            if c and s and ss:
                _touch(3, c, s, ss, w * 1.2)
            if c and s:
                _touch(2, c, s, None, w)

    if not candidates:
        return _collect_branch_candidates_from_catalog(db, gender_label=gender_label)

    unique = sorted(candidates.values(), key=lambda x: x["score"], reverse=True)
    return unique


def _collect_branch_candidates_from_catalog(
    db: Session,
    *,
    gender_label: str,
) -> List[Dict[str, Any]]:
    """Fallback khi chưa có lượt xem — dùng logic purchases như hero cũ."""
    suffix = _gender_suffix(gender_label)
    payload = hero.get_hero_category_tiles(
        db,
        user_id=None,
        guest_session_id=None,
        profile_gender="male" if gender_label == "Nam" else "female",
        recent_limit=0,
        limit=24,
    )
    out: List[Dict[str, Any]] = []
    for t in payload.get("tiles") or []:
        lv = int(t.get("level") or 2)
        if lv not in (2, 3):
            continue
        cat = (t.get("category") or "").strip()
        if not cat:
            continue
        out.append(
            {
                "level": lv,
                "name": t.get("name") or "",
                "category": cat,
                "subcategory": t.get("subcategory"),
                "sub_subcategory": t.get("sub_subcategory"),
                "product_count": int(t.get("product_count") or 0),
                "purchases": int(t.get("purchases") or 0),
                "score": float(t.get("product_count") or 0),
                "key": _branch_key(
                    lv,
                    cat,
                    t.get("subcategory"),
                    t.get("sub_subcategory"),
                ),
            }
        )
    return out


def _pick_two_groups(
    candidates: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    seen: Set[str] = set()
    ordered: List[Dict[str, Any]] = []
    for c in candidates:
        k = c["key"]
        if k in seen:
            continue
        seen.add(k)
        ordered.append(c)

    g1 = ordered[:TILES_PER_GROUP]
    g2: List[Dict[str, Any]] = []
    used = {c["key"] for c in g1}
    for c in ordered[TILES_PER_GROUP:]:
        if c["key"] in used:
            continue
        g2.append(c)
        used.add(c["key"])
        if len(g2) >= TILES_PER_GROUP:
            break
    if len(g2) < TILES_PER_GROUP:
        for c in ordered:
            if c["key"] not in used:
                g2.append(c)
                used.add(c["key"])
            if len(g2) >= TILES_PER_GROUP:
                break
    return g1, g2


def _build_tiles_payload(
    db: Session,
    picked: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    if not picked:
        return [], 0
    used_images: Set[str] = set()
    l2_pairs: List[Tuple[str, str]] = []
    l3_triples: List[Tuple[str, str, str]] = []
    for c in picked:
        cat = (c.get("category") or "").strip()
        sub = (c.get("subcategory") or "").strip()
        subsub = (c.get("sub_subcategory") or "").strip()
        if int(c["level"]) == 2 and cat and sub:
            l2_pairs.append((cat, sub))
        elif int(c["level"]) == 3 and cat and sub and subsub:
            l3_triples.append((cat, sub, subsub))
    img_l2 = hero._bulk_branch_images_l2(db, l2_pairs, used_images)
    img_l3 = hero._bulk_branch_images_l3(db, l3_triples, used_images)

    tiles: List[Dict[str, Any]] = []
    score_total = 0
    for i, c in enumerate(picked):
        cat = (c.get("category") or "").strip()
        sub = (c.get("subcategory") or "").strip()
        subsub = (c.get("sub_subcategory") or "").strip()
        img: Optional[str] = None
        if int(c["level"]) == 2 and cat and sub:
            img = img_l2.get((cat, sub))
        elif int(c["level"]) == 3 and cat and sub and subsub:
            img = img_l3.get((cat, sub, subsub))
        if not img:
            img = hero._sample_image_for_branch(
                db,
                category=cat,
                subcategory=sub or None,
                sub_subcategory=subsub or None,
                level=int(c["level"]),
                viewed_product_ids=[],
                exclude_urls=used_images,
            )
        if img:
            used_images.add(img)
        score_total += int(c.get("score") or 0)
        tiles.append(
            {
                "level": c["level"],
                "name": c["name"],
                "short_name": hero._short_display_name(c["name"]),
                "category": c["category"],
                "subcategory": c.get("subcategory"),
                "sub_subcategory": c.get("sub_subcategory"),
                "product_count": c.get("product_count", 0),
                "purchases": c.get("purchases", 0),
                "ctr_hint": hero._ctr_hint(c["name"], int(c.get("product_count") or 0), i),
                "aspect_ratio": hero._aspect_ratio(c["key"], i),
                "image_url": img,
            }
        )
    with_img = [t for t in tiles if t.get("image_url")]
    without_img = [t for t in tiles if not t.get("image_url")]
    return (with_img + without_img)[: len(picked)], score_total


def rebuild_home_hero_category_groups(db: Session) -> Dict[str, Any]:
    """Tính lại 4 nhóm (2 Nam + 2 Nữ) và upsert vào DB."""
    view_weights = _aggregate_product_view_weights(db)
    summary: Dict[str, Any] = {"groups": [], "viewed_products": len(view_weights)}

    for gender_label in GENDERS:
        candidates = _collect_branch_candidates_for_gender(
            db, gender_label=gender_label, view_weights=view_weights
        )
        g1_pick, g2_pick = _pick_two_groups(candidates)
        for group_index, picked in ((1, g1_pick), (2, g2_pick)):
            tiles, score_total = _build_tiles_payload(db, picked)
            anchor = picked[0]["name"] if picked else None
            heading = f"Đồ {gender_label}" if anchor else f"Danh mục {gender_label}"
            subtitle = "Nhóm hot theo lượt khách xem"
            row = (
                db.query(HomeHeroCategoryGroup)
                .filter(
                    HomeHeroCategoryGroup.gender == gender_label,
                    HomeHeroCategoryGroup.group_index == group_index,
                )
                .first()
            )
            if row is None:
                row = HomeHeroCategoryGroup(
                    gender=gender_label,
                    group_index=group_index,
                )
                db.add(row)
            row.tiles = tiles
            row.heading = heading
            row.subtitle = subtitle
            row.anchor_category = anchor
            row.view_score_total = score_total
            summary["groups"].append(
                {
                    "gender": gender_label,
                    "group_index": group_index,
                    "tile_count": len(tiles),
                    "view_score_total": score_total,
                }
            )
    db.commit()
    _log.info("rebuild_home_hero_category_groups: %s", summary)
    return summary


def _rows_for_gender(db: Session, gender_label: str) -> List[HomeHeroCategoryGroup]:
    return (
        db.query(HomeHeroCategoryGroup)
        .filter(HomeHeroCategoryGroup.gender == gender_label)
        .order_by(HomeHeroCategoryGroup.group_index.asc())
        .all()
    )


def get_cached_home_hero_payload(
    db: Session,
    *,
    gender_label: str = "Nam",
    limit: int = 16,
) -> Dict[str, Any]:
    """
    Đọc 2 nhóm đã lưu (group 1 + group 2) cho giới — trả về tối đa `limit` tile.
    """
    gl = "Nữ" if (gender_label or "").strip() in ("Nữ", "Nu", "nu", "nữ") else "Nam"
    rows = _rows_for_gender(db, gl)
    if not rows:
        return {
            "tiles": [],
            "gender_label": gl,
            "heading": None,
            "subtitle": None,
            "anchor_category": None,
            "source": "cached_db",
        }

    tiles: List[Dict[str, Any]] = []
    heading = None
    subtitle = None
    anchor = None
    for row in rows:
        chunk = row.tiles if isinstance(row.tiles, list) else []
        tiles.extend(chunk)
        if not heading and row.heading:
            heading = row.heading
        if not subtitle and row.subtitle:
            subtitle = row.subtitle
        if not anchor and row.anchor_category:
            anchor = row.anchor_category
        if len(tiles) >= limit:
            break

    cap = max(8, min(int(limit), hero.HERO_CAROUSEL_TILE_MAX))
    display = tiles[:cap]
    if not heading:
        heading = f"Danh mục {gl}"
    if not subtitle:
        subtitle = "Nhóm & chi tiết — vuốt xem thêm"

    return {
        "tiles": display,
        "gender_label": gl,
        "heading": heading,
        "subtitle": subtitle,
        "anchor_category": anchor,
        "source": "cached_db",
    }


def resolve_hero_gender_for_session(
    db: Session,
    *,
    user_id: Optional[int] = None,
    guest_session_id: Optional[str] = None,
    profile_gender: Optional[str] = None,
    recent_limit: int = 8,
) -> str:
    """Chọn Nam/Nữ nhẹ — không build tile."""
    info = hero.infer_category_gender_priority(
        db,
        user_id=user_id,
        guest_session_id=guest_session_id,
        profile_gender=profile_gender,
        recent_limit=recent_limit,
    )
    gl = (info.get("gender_label") or "").strip()
    if gl in ("Nam", "Nữ"):
        return gl
    return "Nam"


def get_home_hero_tiles_fast(
    db: Session,
    *,
    user_id: Optional[int] = None,
    guest_session_id: Optional[str] = None,
    profile_gender: Optional[str] = None,
    recent_limit: int = 8,
    limit: int = 16,
) -> Dict[str, Any]:
    """API trang chủ: suy giới nhẹ + đọc cache DB."""
    gender = resolve_hero_gender_for_session(
        db,
        user_id=user_id,
        guest_session_id=guest_session_id,
        profile_gender=profile_gender,
        recent_limit=recent_limit,
    )
    payload = get_cached_home_hero_payload(db, gender_label=gender, limit=limit)
    if payload.get("tiles"):
        if user_id or guest_session_id:
            payload["source"] = "cached_db_profile"
        return payload

    # Cache trống — fallback tính realtime (lần đầu / chưa rebuild)
    _log.warning("home_hero cache empty for %s — fallback realtime", gender)
    return hero.get_hero_category_tiles(
        db,
        user_id=user_id,
        guest_session_id=guest_session_id,
        profile_gender=profile_gender,
        recent_limit=recent_limit,
        limit=limit,
    )


def cache_has_groups(db: Session) -> bool:
    return db.query(HomeHeroCategoryGroup.id).limit(1).first() is not None
