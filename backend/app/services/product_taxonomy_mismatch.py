"""
Phát hiện sản phẩm có cây danh mục (taxonomy) lệch so với tên SP,
và tái gán taxonomy bằng DeepSeek (cùng pipeline import link).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.category import Category
from app.models.product import Product
from app.services.import_link_deepseek_taxonomy import apply_deepseek_taxonomy_to_product_data
from app.utils.vietnamese import remove_vietnamese_accents

logger = logging.getLogger(__name__)

DOMAIN_FOOTWEAR = "footwear"
DOMAIN_APPAREL = "apparel"
DOMAIN_BAG = "bag"
DOMAIN_UNDERWEAR = "underwear"
DOMAIN_WATCH = "watch"
DOMAIN_COSMETIC = "cosmetic"
DOMAIN_TOY_BABY = "toy_baby"
DOMAIN_SPORTS = "sports"
DOMAIN_OTHER = "other"

# Gợi ý trong tên SP (regex, không dấu) → domain
_NAME_DOMAIN_PATTERNS: Tuple[Tuple[str, str], ...] = (
    # Không dùng «oxford»/«derby» đơn lẻ — tránh nhầm áo sơ mi Oxford với giày Oxford.
    (DOMAIN_FOOTWEAR, r"(^|[^a-z0-9])(giay|giay dep|giay oxford|giay derby|sneaker|sandal|boot|loafer|mule|monkstrap|clog)([^a-z0-9]|$)"),
    # Không dùng «dam»/«đầm» đơn lẻ — «màu nâu đậm» → «nau dam» nhầm váy đầm.
    (DOMAIN_APPAREL, r"(^|[^a-z0-9])(ao khoac|áo khoác|ao thun|áo thun|ao so mi|áo sơ mi|vay|váy|vay dam|dam cong|dam suon|dam body|dam om|quan jean|quần jean|quan short|quần short|ao polo|blazer|cardigan|chan vay|chân váy)([^a-z0-9]|$)"),
    (DOMAIN_BAG, r"(^|[^a-z0-9])(tui xach|túi xách|balo|backpack|vi da|ví da|handbag|clutch|tote)([^a-z0-9]|$)"),
    (DOMAIN_UNDERWEAR, r"(^|[^a-z0-9])(do lot|đồ lót|ao lot|áo lót|quan lot|quần lót|noi y|nội y)([^a-z0-9]|$)"),
    (DOMAIN_WATCH, r"(^|[^a-z0-9])(dong ho|đồng hồ)([^a-z0-9]|$)"),
    (DOMAIN_COSMETIC, r"(^|[^a-z0-9])(son |kem duong|kem dưỡng|nuoc hoa|nước hoa|my pham|mỹ phẩm)([^a-z0-9]|$)"),
    (DOMAIN_TOY_BABY, r"(^|[^a-z0-9])(do choi|đồ chơi|me va be|mẹ và bé)([^a-z0-9]|$)"),
    (DOMAIN_SPORTS, r"(^|[^a-z0-9])(the thao|thể thao|yoga mat|tham yoga)([^a-z0-9]|$)"),
)

_CATEGORY_L1_DOMAIN: Dict[str, str] = {
    "Giày dép Nam": DOMAIN_FOOTWEAR,
    "Giày dép Nữ": DOMAIN_FOOTWEAR,
    "Thời trang Nam": DOMAIN_APPAREL,
    "Thời trang Nữ": DOMAIN_APPAREL,
    "Thời trang trẻ em": DOMAIN_APPAREL,
    "Trang phục bầu & hậu sản": DOMAIN_APPAREL,
    "Đồ lót Nam": DOMAIN_UNDERWEAR,
    "Đồ lót Nữ": DOMAIN_UNDERWEAR,
    "Túi xách Nam": DOMAIN_BAG,
    "Túi xách Nữ": DOMAIN_BAG,
    "Vali túi du lịch": DOMAIN_BAG,
    "Phụ kiện Nam": DOMAIN_OTHER,
    "Phụ kiện Nữ": DOMAIN_OTHER,
    "Đồng hồ": DOMAIN_WATCH,
    "Mỹ phẩm & làm đẹp": DOMAIN_COSMETIC,
    "Đồ chơi & mẹ bé": DOMAIN_TOY_BABY,
    "Thể thao & dã ngoại": DOMAIN_SPORTS,
}

_DOMAIN_LABEL_VI: Dict[str, str] = {
    DOMAIN_FOOTWEAR: "Giày dép",
    DOMAIN_APPAREL: "Quần áo / thời trang",
    DOMAIN_BAG: "Túi xách / balo",
    DOMAIN_UNDERWEAR: "Đồ lót",
    DOMAIN_WATCH: "Đồng hồ",
    DOMAIN_COSMETIC: "Mỹ phẩm",
    DOMAIN_TOY_BABY: "Đồ chơi & mẹ bé",
    DOMAIN_SPORTS: "Thể thao",
    DOMAIN_OTHER: "Khác",
}

# Chỉ các danh mục cấp 1 có «ngành» rõ — quét / báo lệch chỉ trên tập này.
_SCANNABLE_L1_NAMES: frozenset = frozenset(_CATEGORY_L1_DOMAIN.keys())


def _norm_name(text: str) -> str:
    return remove_vietnamese_accents((text or "").lower())


def infer_domain_from_product_name(name: str) -> Tuple[Optional[str], Dict[str, int]]:
    """Suy domain từ tên SP. Trả (domain_chính hoặc None nếu mơ hồ, điểm theo domain)."""
    text = _norm_name(name)
    if not text.strip():
        return None, {}
    scores: Dict[str, int] = {}
    for domain, pattern in _NAME_DOMAIN_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores[domain] = scores.get(domain, 0) + 1
    if not scores:
        return None, scores
    best_score = max(scores.values())
    leaders = [d for d, s in scores.items() if s == best_score]
    if len(leaders) != 1:
        # Cùng điểm: ưu tiên giày nếu tên có «giày»; quần áo nếu có áo/quần/váy (không dùng «dam» đơn — trùng «đậm»).
        if DOMAIN_FOOTWEAR in scores and re.search(
            r"(^|[^a-z0-9])(giay|giay dep|sneaker|sandal|boot|loafer)([^a-z0-9]|$)", text
        ):
            return DOMAIN_FOOTWEAR, scores
        if DOMAIN_APPAREL in scores and re.search(
            r"(^|[^a-z0-9])(ao |quan |vay|dress|shirt|dam cong|dam suon|vay dam)([^a-z0-9]|$)", text
        ):
            return DOMAIN_APPAREL, scores
        return None, scores
    return leaders[0], scores


def category_l1_domain(l1_name: Optional[str]) -> Optional[str]:
    s = (l1_name or "").strip()
    if not s:
        return None
    return _CATEGORY_L1_DOMAIN.get(s)


def is_severe_l1_name_domain_mismatch(inferred: Optional[str], l1_domain: Optional[str]) -> bool:
    """
    Lệch cấp 1 «quá rõ»: tên SP gợi ý một ngành khác hẳn danh mục cấp 1 đang ghi.
    Không so category_id / subcategory — chỉ cột category (L1) vs tên.
    """
    if not inferred or not l1_domain or inferred == l1_domain:
        return False
    # Phụ kiện: chỉ báo khi tên gợi ý rõ ngành cụ thể (giày, quần áo, đồng hồ…).
    if l1_domain == DOMAIN_OTHER:
        return inferred != DOMAIN_OTHER
    return True


def _build_cat3_id_to_l1_name(db: Session) -> Dict[int, str]:
    rows = (
        db.query(Category.id, Category.parent_id, Category.level, Category.name)
        .filter(Category.is_active.is_(True))
        .all()
    )
    by_id = {r.id: r for r in rows}
    out: Dict[int, str] = {}

    def l1_for(cat_id: int) -> Optional[str]:
        cur = by_id.get(cat_id)
        seen: Set[int] = set()
        while cur and cur.id not in seen:
            seen.add(cur.id)
            if cur.level == 1:
                return (cur.name or "").strip()
            if cur.parent_id is None:
                return None
            cur = by_id.get(cur.parent_id)
        return None

    for r in rows:
        if r.level == 3:
            l1 = l1_for(r.id)
            if l1:
                out[r.id] = l1
    return out


def detect_product_taxonomy_mismatch(
    product: Product,
    *,
    cat3_l1_map: Optional[Dict[int, str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Chỉ ghi nhận lệch cấp 1 rõ: ngành suy từ **tên SP** ≠ ngành của **cột category** (L1).
    Vd quần áo trong Giày dép, giày trong Đồng hồ. Không so FK / subcategory.
    """
    del cat3_l1_map  # giữ tham số tương thích caller cũ
    name = (product.name or "").strip()
    if not name:
        return None

    inferred, scores = infer_domain_from_product_name(name)
    if not inferred:
        return None

    l1_text = (product.category or "").strip()
    l1_domain = category_l1_domain(l1_text)
    if not l1_domain or l1_text not in _SCANNABLE_L1_NAMES:
        return None

    if not is_severe_l1_name_domain_mismatch(inferred, l1_domain):
        return None

    reason = (
        f"Tên gợi ý «{_DOMAIN_LABEL_VI.get(inferred, inferred)}» "
        f"nhưng danh mục cấp 1 là «{l1_text}» "
        f"(«{_DOMAIN_LABEL_VI.get(l1_domain, l1_domain)}»)"
    )

    return {
        "product_pk": product.id,
        "product_id": product.product_id,
        "name": name[:200],
        "category": product.category,
        "subcategory": product.subcategory,
        "sub_subcategory": product.sub_subcategory,
        "category_id": product.category_id,
        "inferred_domain": inferred,
        "inferred_domain_label": _DOMAIN_LABEL_VI.get(inferred, inferred),
        "domain_scores": scores,
        "l1_from_text": l1_text,
        "l1_domain": l1_domain,
        "reason": reason,
    }


def scan_taxonomy_mismatches(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 100,
    category_l1: Optional[str] = None,
    is_active: Optional[bool] = True,
    max_scan: int = 5000,
) -> Dict[str, Any]:
    """
    Quét SP — trả danh sách lệch + meta phân trang.
    max_scan: số dòng DB tối đa duyệt để tìm `limit` kết quả (tránh quét 24k mỗi lần).
    """
    q = db.query(Product).order_by(Product.id.asc())
    if is_active is True:
        q = q.filter(Product.is_active.is_(True))
    elif is_active is False:
        q = q.filter(Product.is_active.is_(False))
    if category_l1 and category_l1.strip():
        l1 = category_l1.strip()
        q = q.filter(Product.category.ilike(l1))

    items: List[Dict[str, Any]] = []
    scanned = 0
    offset = max(0, int(skip))
    need = max(1, min(int(limit), 500))
    cap = max(need, min(int(max_scan), 50000))

    for product in q.offset(offset).limit(cap).all():
        scanned += 1
        row = detect_product_taxonomy_mismatch(product)
        if row:
            items.append(row)
            if len(items) >= need:
                break

    return {
        "items": items,
        "count": len(items),
        "scanned": scanned,
        "skip": offset,
        "limit": need,
        "category_l1_filter": category_l1,
        "is_active": is_active,
    }


def list_active_category_l1_names(db: Session) -> List[str]:
    rows = (
        db.query(Category.name)
        .filter(Category.level == 1, Category.is_active.is_(True))
        .order_by(Category.name.asc())
        .all()
    )
    names = [(r[0] or "").strip() for r in rows if (r[0] or "").strip()]
    return [n for n in names if n in _SCANNABLE_L1_NAMES]


def scan_taxonomy_mismatches_all_l1(
    db: Session,
    *,
    limit_per_l1: int = 50,
    is_active: Optional[bool] = True,
    max_scan_per_l1: int = 12000,
    sample_items: int = 2,
) -> Dict[str, Any]:
    """
    Quét lần lượt từng danh mục cấp 1 — trả tổng hợp số lệch / đã quét mỗi nhánh.
    """
    cap = max(1, min(int(limit_per_l1), 500))
    samples_n = max(0, min(int(sample_items), 10))
    blocks: List[Dict[str, Any]] = []
    total_mismatch = 0
    for l1 in list_active_category_l1_names(db):
        block = scan_taxonomy_mismatches(
            db,
            skip=0,
            limit=cap,
            category_l1=l1,
            is_active=is_active,
            max_scan=max_scan_per_l1,
        )
        total_mismatch += int(block.get("count") or 0)
        blocks.append(
            {
                "category_l1": l1,
                "count": block.get("count", 0),
                "scanned": block.get("scanned", 0),
                "limit": block.get("limit", cap),
                "samples": (block.get("items") or [])[:samples_n],
            }
        )
    return {
        "categories": blocks,
        "total_mismatch": total_mismatch,
        "category_count": len(blocks),
        "is_active": is_active,
    }


def _product_to_taxonomy_payload(product: Product) -> Dict[str, Any]:
    return {
        "name": product.name,
        "description": product.description,
        "category": product.category,
        "subcategory": product.subcategory,
        "sub_subcategory": product.sub_subcategory,
        "raw_category": product.raw_category,
        "raw_subcategory": product.raw_subcategory,
        "raw_sub_subcategory": product.raw_sub_subcategory,
        "material": product.material,
        "style": product.style,
        "color": product.color,
        "occasion": product.occasion,
        "features": product.features,
        "weight": product.weight,
        "product_info": product.product_info,
        "brand_name": product.brand_name,
        "origin": product.origin,
    }


def _apply_taxonomy_payload_to_product(db: Session, product: Product, data: Dict[str, Any]) -> None:
    from app.crud.product import (
        _build_cat3_lookup_indexes,
        _build_cat3_triple_name_lookup,
        _sync_product_category_id_from_taxonomy,
    )

    for key in (
        "category",
        "subcategory",
        "sub_subcategory",
        "raw_category",
        "raw_subcategory",
        "raw_sub_subcategory",
        "name",
        "description",
        "material",
        "style",
        "color",
        "occasion",
        "features",
        "weight",
        "product_info",
    ):
        if key in data and data[key] is not None:
            setattr(product, key, data[key])
    triple_idx = _build_cat3_triple_name_lookup(db)
    cat3_idx = _build_cat3_lookup_indexes(db)
    _sync_product_category_id_from_taxonomy(product, triple_idx, cat3_idx)


def reclassify_product_taxonomy_deepseek(
    db: Session,
    product: Product,
    *,
    force: bool = True,
) -> Dict[str, Any]:
    """
    Gán lại taxonomy từ tên + mô tả (DeepSeek).
    force=True: xóa bộ ba category hiện tại trước khi gọi model.
    """
    if not settings.IMPORT_LINK_DEEPSEEK_TAXONOMY_ENABLED:
        return {
            "ok": False,
            "product_id": product.product_id,
            "error": "IMPORT_LINK_DEEPSEEK_TAXONOMY_ENABLED đang tắt",
            "warnings": [],
        }

    old_path = {
        "category": product.category,
        "subcategory": product.subcategory,
        "sub_subcategory": product.sub_subcategory,
        "category_id": product.category_id,
    }
    data = _product_to_taxonomy_payload(product)
    if force:
        data["category"] = ""
        data["subcategory"] = ""
        data["sub_subcategory"] = ""

    warnings = apply_deepseek_taxonomy_to_product_data(db, data)
    new_c1 = (data.get("category") or "").strip()
    if not new_c1:
        return {
            "ok": False,
            "product_id": product.product_id,
            "old": old_path,
            "warnings": warnings,
            "error": "DeepSeek không gán được nhánh taxonomy hợp lệ",
        }

    _apply_taxonomy_payload_to_product(db, product, data)
    return {
        "ok": True,
        "product_id": product.product_id,
        "old": old_path,
        "new": {
            "category": product.category,
            "subcategory": product.subcategory,
            "sub_subcategory": product.sub_subcategory,
            "category_id": product.category_id,
        },
        "warnings": warnings,
    }


def reclassify_products_batch(
    db: Session,
    *,
    product_ids: Optional[List[str]] = None,
    category_l1: Optional[str] = None,
    is_active: Optional[bool] = True,
    limit: int = 20,
    only_mismatched: bool = True,
    dry_run: bool = False,
    max_scan: Optional[int] = None,
) -> Dict[str, Any]:
    """Tái phân loại theo danh sách product_id hoặc quét mismatch (giới hạn)."""
    cap = max(1, min(int(limit), 100))
    results: List[Dict[str, Any]] = []

    targets: List[Product] = []
    if product_ids:
        ids = [str(x).strip() for x in product_ids if str(x).strip()]
        if ids:
            targets = (
                db.query(Product)
                .filter(Product.product_id.in_(ids))
                .order_by(Product.id.asc())
                .limit(cap)
                .all()
            )
    else:
        scan_cap = max(cap * 40, int(max_scan)) if max_scan else cap * 40
        scan = scan_taxonomy_mismatches(
            db,
            skip=0,
            limit=cap,
            category_l1=category_l1,
            is_active=is_active,
            max_scan=scan_cap,
        )
        pk_ids = [int(x["product_pk"]) for x in scan.get("items", []) if x.get("product_pk")]
        if pk_ids:
            targets = db.query(Product).filter(Product.id.in_(pk_ids)).all()
        if not only_mismatched:
            q = db.query(Product).order_by(Product.id.asc())
            if is_active is True:
                q = q.filter(Product.is_active.is_(True))
            if category_l1:
                q = q.filter(Product.category.ilike(category_l1.strip()))
            targets = q.limit(cap).all()

    ok_n = 0
    fail_n = 0
    for product in targets:
        if only_mismatched and product_ids is None:
            if not detect_product_taxonomy_mismatch(product):
                continue
        if dry_run:
            results.append(
                {
                    "product_id": product.product_id,
                    "dry_run": True,
                    "would_reclassify": True,
                    "name": (product.name or "")[:120],
                    "current": {
                        "category": product.category,
                        "subcategory": product.subcategory,
                        "sub_subcategory": product.sub_subcategory,
                    },
                }
            )
            ok_n += 1
            continue
        try:
            row = reclassify_product_taxonomy_deepseek(db, product, force=True)
            if row.get("ok"):
                ok_n += 1
            else:
                fail_n += 1
            results.append(row)
        except Exception as exc:
            fail_n += 1
            results.append(
                {
                    "ok": False,
                    "product_id": product.product_id,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    if not dry_run and (ok_n or fail_n):
        try:
            db.commit()
            from app.utils.ttl_cache import cache as ttl_cache

            ttl_cache.invalidate_all()
        except Exception:
            db.rollback()
            raise
    elif dry_run:
        db.rollback()

    return {
        "dry_run": dry_run,
        "processed": len(results),
        "ok": ok_n,
        "failed": fail_n,
        "results": results,
    }


def reclassify_products_batch_all_l1(
    db: Session,
    *,
    limit_per_l1: int = 20,
    is_active: Optional[bool] = True,
    max_scan_per_l1: int = 12000,
    only_mismatched: bool = True,
    dry_run: bool = False,
    category_l1_names: Optional[List[str]] = None,
    only_categories_with_mismatch: bool = True,
) -> Dict[str, Any]:
    """
    Tái gán DeepSeek lần lượt mọi danh mục cấp 1 (tối đa `limit_per_l1` SP mỗi nhánh).
    Mỗi nhánh commit riêng — tránh mất toàn bộ nếu một nhánh lỗi giữa chừng.
    """
    cap = max(1, min(int(limit_per_l1), 100))
    l1_list = [x.strip() for x in (category_l1_names or list_active_category_l1_names(db)) if x.strip()]
    blocks: List[Dict[str, Any]] = []
    total_ok = 0
    total_failed = 0
    total_processed = 0

    for l1 in l1_list:
        if only_categories_with_mismatch:
            scan_preview = scan_taxonomy_mismatches(
                db,
                skip=0,
                limit=1,
                category_l1=l1,
                is_active=is_active,
                max_scan=max_scan_per_l1,
            )
            if not (scan_preview.get("items") or []):
                blocks.append(
                    {
                        "category_l1": l1,
                        "skipped": True,
                        "ok": 0,
                        "failed": 0,
                        "processed": 0,
                    }
                )
                continue

        block = reclassify_products_batch(
            db,
            product_ids=None,
            category_l1=l1,
            is_active=is_active,
            limit=cap,
            only_mismatched=only_mismatched,
            dry_run=dry_run,
            max_scan=max_scan_per_l1,
        )
        blocks.append(
            {
                "category_l1": l1,
                "skipped": False,
                "ok": block.get("ok", 0),
                "failed": block.get("failed", 0),
                "processed": block.get("processed", 0),
            }
        )
        total_ok += int(block.get("ok") or 0)
        total_failed += int(block.get("failed") or 0)
        total_processed += int(block.get("processed") or 0)

    return {
        "dry_run": dry_run,
        "categories": blocks,
        "category_count": len(blocks),
        "categories_processed": sum(1 for b in blocks if not b.get("skipped")),
        "ok": total_ok,
        "failed": total_failed,
        "processed": total_processed,
        "limit_per_l1": cap,
    }
