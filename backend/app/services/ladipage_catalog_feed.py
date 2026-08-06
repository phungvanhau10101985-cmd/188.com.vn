"""
Gắn URL Ladipage đã publish vào feed catalog Google / Meta / TikTok.

Mỗi sản phẩm thuộc ladipage published → cột `link` trong TSV trỏ `/lp/{slug}`
thay vì `/products/{slug}` để quảng cáo đưa khách vào landing AI.
"""
from __future__ import annotations

from typing import Dict
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models.ladipage import Ladipage
from app.services.ladipage_ai_service import resolve_products_for_ladipage


def build_published_ladipage_product_links(db: Session, shop_base_url: str) -> Dict[int, str]:
    """
    Map `product.id` → absolute URL `/lp/{slug}` cho mọi sản phẩm nằm trong ladipage đã publish.

    Nếu nhiều ladipage chứa cùng sản phẩm: ladipage publish mới hơn thắng.
    Ladipage 1 SP bị bỏ qua — feed dùng URL sản phẩm mặc định.
    """
    base = shop_base_url.rstrip("/")
    links: Dict[int, str] = {}
    priority: Dict[int, int] = {}

    rows = (
        db.query(Ladipage)
        .filter(Ladipage.status == "published")
        .order_by(Ladipage.published_at.desc(), Ladipage.updated_at.desc(), Ladipage.id.desc())
        .all()
    )
    for lp in rows:
        products = resolve_products_for_ladipage(db, lp)
        if not products or len(products) == 1:
            # Ladipage 1 SP: URL public là PDP — không ghi đè link feed catalog.
            continue
        url = f"{base}/lp/{quote(lp.slug, safe='')}"
        prio = 1
        for product in products:
            prev = priority.get(product.id)
            if prev is None or prio < prev:
                links[product.id] = url
                priority[product.id] = prio

    return links
