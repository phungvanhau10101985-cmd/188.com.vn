"""
Gắn URL Ladipage (danh mục / nhiều SP) đã publish vào feed catalog Google / Meta / TikTok.

- Ladipage ≥2 SP published → cột `link` TSV trỏ `/lp/{slug}` (landing quảng cáo).
- Ladipage 1 SP → bỏ qua: feed giữ `/products/...` (nội dung AI nằm trên PDP, không đổi nguồn catalog).
"""
from __future__ import annotations

from typing import Dict
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models.ladipage import Ladipage
from app.services.ladipage_ai_service import resolve_products_for_ladipage


def build_published_ladipage_product_links(db: Session, shop_base_url: str) -> Dict[int, str]:
    """
    Map `product.id` → absolute URL `/lp/{slug}` cho sản phẩm thuộc ladipage published (≥2 SP).

    Nếu nhiều ladipage chứa cùng sản phẩm: ladipage publish mới hơn thắng.
    Ladipage 1 SP bị bỏ qua — feed dùng URL PDP mặc định (không thêm nguồn ladipage riêng).
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
