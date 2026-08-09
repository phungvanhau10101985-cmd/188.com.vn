"""
Fallback "phổ biến" khi không có same-shop/cohort để đề xuất — trộn round-robin
"bán chạy nhất" (`purchases desc`) + "được xem nhiều nhất" (view_total desc), đa dạng
theo `subcategory` để tránh dồn hết vào 1 ngành hàng.

Dùng cho 2 trường hợp:
- User đăng nhập có hồ sơ đầy đủ nhưng chưa có peer cùng tuổi/giới (`cohort_mode ==
  "popular_fallback"` trong `app.crud.cohort_view_pool_cache`).
- Guest chưa xem sản phẩm nào, hoặc đã xem nhưng toàn bộ SP thiếu `shop_name_chinese`
  (nên same-shop rỗng).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from app.crud.category_hero_suggestions import _text_has_gender_nam, _text_has_gender_nu
from app.crud.product import _product_view_totals_subquery
from app.models.product import Product

# Cap SP/subcategory trong danh sách fallback — giữ đa dạng ngành hàng.
POPULAR_FALLBACK_MAX_PER_SUBCATEGORY = 5


def _fetch_ranked(
    db: Session,
    *,
    order_exprs: Sequence[Any],
    exclude_ids: set,
    fetch_limit: int,
    join_target=None,
    join_condition=None,
) -> List[Product]:
    from app.services.warehouse_clearance import apply_catalog_visibility_filter

    query = db.query(Product).filter(Product.is_active == True)  # noqa: E712
    if join_target is not None and join_condition is not None:
        query = query.outerjoin(join_target, join_condition)
    if exclude_ids:
        query = query.filter(~Product.id.in_(exclude_ids))
    query = apply_catalog_visibility_filter(query)
    return query.order_by(*order_exprs).limit(fetch_limit).all()


def _interleave_and_diversify(
    ranked_lists: List[List[Product]],
    *,
    limit: int,
    max_per_subcategory: int = POPULAR_FALLBACK_MAX_PER_SUBCATEGORY,
) -> List[Product]:
    """Round-robin qua các danh sách đã xếp hạng, cap SP/subcategory, loại trùng id."""
    seen_ids: set = set()
    subcat_counts: Dict[str, int] = {}
    result: List[Product] = []
    cursors = [0] * len(ranked_lists)

    progressed = True
    while progressed and len(result) < limit:
        progressed = False
        for i, lst in enumerate(ranked_lists):
            if len(result) >= limit:
                break
            while cursors[i] < len(lst):
                product = lst[cursors[i]]
                cursors[i] += 1
                if product.id in seen_ids:
                    continue
                sub = (product.subcategory or "").strip().lower() or "_none"
                if subcat_counts.get(sub, 0) >= max_per_subcategory:
                    continue
                seen_ids.add(product.id)
                subcat_counts[sub] = subcat_counts.get(sub, 0) + 1
                result.append(product)
                progressed = True
                break

    return result


def _gender_tag(product: Product) -> str:
    """'nam' | 'nu' | 'neutral' — suy từ tên category/subcategory/sub_subcategory (đuôi
    " Nam"/" Nữ" — cùng quy ước với `category_hero_suggestions`)."""
    blob = " ".join(
        x
        for x in [
            getattr(product, "category", None) or "",
            getattr(product, "subcategory", None) or "",
            getattr(product, "sub_subcategory", None) or "",
        ]
        if x
    )
    is_nam = _text_has_gender_nam(blob)
    is_nu = _text_has_gender_nu(blob)
    if is_nam and not is_nu:
        return "nam"
    if is_nu and not is_nam:
        return "nu"
    return "neutral"


def _partition_by_gender(products: List[Product]) -> Dict[str, List[Product]]:
    buckets: Dict[str, List[Product]] = {"nam": [], "nu": [], "neutral": []}
    for p in products:
        buckets[_gender_tag(p)].append(p)
    return buckets


def _macro_interleave_two(a: List[Product], b: List[Product], limit: int) -> List[Product]:
    """Xen kẽ 1-1 giữa 2 danh sách (đã dedup/cap riêng), giữ thứ tự trong từng danh sách."""
    result: List[Product] = []
    i = j = 0
    while (i < len(a) or j < len(b)) and len(result) < limit:
        if i < len(a):
            result.append(a[i])
            i += 1
        if len(result) >= limit:
            break
        if j < len(b):
            result.append(b[j])
            j += 1
    return result[:limit]


def get_popular_fallback_products(
    db: Session,
    *,
    exclude_product_ids: Optional[Sequence[int]] = None,
    limit: int = 24,
    balance_gender: bool = False,
) -> List[Product]:
    """
    Trả về tối đa `limit` sản phẩm "phổ biến" — trộn bán chạy nhất + được xem nhiều nhất,
    đa dạng theo subcategory, loại `exclude_product_ids` (SP khách đã xem/đã có trong lưới).

    `balance_gender=True`: ép tỷ lệ ~50/50 Nam/Nữ (theo tên category/subcategory) thay vì để
    thứ hạng bán chạy/xem nhiều tự quyết — dùng cho khách CHƯA CÓ tín hiệu gì (chưa xem sản
    phẩm nào) để tránh lệch giới ngoài ý muốn (ví dụ catalog/lượt mua nghiêng Nam nhiều hơn
    Nữ) khi hoàn toàn không biết khách là ai.
    """
    exclude_ids = {int(pid) for pid in (exclude_product_ids or []) if pid is not None}
    limit = max(1, int(limit))
    fetch_limit = max(limit * (8 if balance_gender else 4), 100)

    bestsellers = _fetch_ranked(
        db,
        order_exprs=[Product.purchases.desc().nullslast(), Product.id.desc()],
        exclude_ids=exclude_ids,
        fetch_limit=fetch_limit,
    )

    view_totals_subq = _product_view_totals_subquery()
    view_count_expr = sql_func.coalesce(view_totals_subq.c.view_total, 0)
    most_viewed = _fetch_ranked(
        db,
        order_exprs=[view_count_expr.desc(), Product.id.desc()],
        exclude_ids=exclude_ids,
        fetch_limit=fetch_limit,
        join_target=view_totals_subq,
        join_condition=view_totals_subq.c.product_id == Product.id,
    )

    if not balance_gender:
        return _interleave_and_diversify([bestsellers, most_viewed], limit=limit)

    best_by_gender = _partition_by_gender(bestsellers)
    viewed_by_gender = _partition_by_gender(most_viewed)

    half = limit // 2
    other_half = limit - half
    nam_pool = _interleave_and_diversify(
        [best_by_gender["nam"], viewed_by_gender["nam"]], limit=half
    )
    nu_pool = _interleave_and_diversify(
        [best_by_gender["nu"], viewed_by_gender["nu"]], limit=other_half
    )

    result = _macro_interleave_two(nam_pool, nu_pool, limit)

    shortfall = limit - len(result)
    if shortfall > 0:
        # nam_pool + nu_pool không đủ lấp limit (catalog ít SP rõ giới) — bù bằng SP trung
        # tính (không xác định được giới qua tên category/subcategory).
        used_ids = {p.id for p in result}
        neutral_candidates = [
            p
            for p in best_by_gender["neutral"] + viewed_by_gender["neutral"]
            if p.id not in used_ids
        ]
        result.extend(_interleave_and_diversify([neutral_candidates, []], limit=shortfall))

    return result[:limit]
