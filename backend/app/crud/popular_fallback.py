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


def get_popular_fallback_products(
    db: Session,
    *,
    exclude_product_ids: Optional[Sequence[int]] = None,
    limit: int = 24,
) -> List[Product]:
    """
    Trả về tối đa `limit` sản phẩm "phổ biến" — trộn bán chạy nhất + được xem nhiều nhất,
    đa dạng theo subcategory, loại `exclude_product_ids` (SP khách đã xem/đã có trong lưới).
    """
    exclude_ids = {int(pid) for pid in (exclude_product_ids or []) if pid is not None}
    fetch_limit = max(int(limit) * 4, 100)

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

    return _interleave_and_diversify([bestsellers, most_viewed], limit=max(1, int(limit)))
