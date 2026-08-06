# backend/app/services/ladipage_public_url.py
"""URL public cho Ladipage — ladipage 1 SP dùng PDP, còn lại dùng /lp/."""
from __future__ import annotations

from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models.ladipage import Ladipage
from app.models.product import Product
from app.services.ladipage_cleanup import _normalize_product_ids
from app.services.merchant_feed_tsv import _feed_path_segment_from_slug


def product_pdp_path(product: Product) -> str:
    seg = _feed_path_segment_from_slug(
        str(product.slug or ""),
        str(product.product_id or product.id),
    )
    return f"/products/{quote(seg, safe='')}"


def resolve_ladipage_public_path(db: Session, lp: Ladipage) -> str:
    """Ladipage 1 SP → URL sản phẩm; ladipage nhiều SP / danh mục → /lp/slug."""
    if lp.source_type == "products":
        ids = _normalize_product_ids(lp.product_ids)
        if len(ids) == 1:
            product = db.query(Product).filter(Product.id == ids[0]).first()
            if product is not None:
                return product_pdp_path(product)
    return f"/lp/{lp.slug}"


def is_single_product_ladipage(lp: Ladipage) -> bool:
    return lp.source_type == "products" and len(_normalize_product_ids(lp.product_ids)) == 1
