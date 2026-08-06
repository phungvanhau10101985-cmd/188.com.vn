# backend/app/services/ladipage_cleanup.py
"""Dọn ladipage khi sản phẩm / dữ liệu liên quan thay đổi.

Chỉ xóa ladipage **1 sản phẩm** khi sản phẩm đó bị xóa.
Ladipage **nhiều sản phẩm** hoặc **theo danh mục** luôn được giữ nguyên,
kể cả khi một sản phẩm trong ladipage bị xóa.
"""
from __future__ import annotations

import logging
from typing import List

from sqlalchemy.orm import Session

from app.models.ladipage import Ladipage
from app.services import bunny_storage

logger = logging.getLogger(__name__)


def _normalize_product_ids(raw: object) -> List[int]:
    if not isinstance(raw, list):
        return []
    out: List[int] = []
    for item in raw:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def is_single_product_ladipage_for_product(lp: Ladipage, product_db_id: int) -> bool:
    """Ladipage nguồn `products` gắn đúng 1 sản phẩm (theo products.id)."""
    if lp.source_type != "products":
        return False
    ids = _normalize_product_ids(lp.product_ids)
    return len(ids) == 1 and ids[0] == int(product_db_id)


def find_single_product_ladipages_for_product(db: Session, product_db_id: int) -> List[Ladipage]:
    rows = db.query(Ladipage).filter(Ladipage.source_type == "products").all()
    return [lp for lp in rows if is_single_product_ladipage_for_product(lp, product_db_id)]


def get_published_single_product_ladipage_slug(db: Session, product_db_id: int) -> str | None:
    """Slug ladipage 1 SP đã publish gắn với ``products.id`` — dùng redirect PDP → /lp/…"""
    rows = (
        db.query(Ladipage)
        .filter(Ladipage.status == "published", Ladipage.source_type == "products")
        .order_by(Ladipage.published_at.desc(), Ladipage.updated_at.desc(), Ladipage.id.desc())
        .all()
    )
    for lp in rows:
        if is_single_product_ladipage_for_product(lp, product_db_id):
            return lp.slug
    return None


def collect_ladipage_section_image_urls(lp: Ladipage) -> List[str]:
    urls: List[str] = []
    for section in lp.sections:
        data = section.data or {}
        url = data.get("image_url")
        if isinstance(url, str) and url.strip():
            urls.append(url.strip())
    return urls


def delete_single_product_ladipages_for_product(db: Session, product_db_id: int) -> int:
    """
    Xóa ladipage 1 sản phẩm khi sản phẩm chính bị xóa khỏi DB.

    Ladipage nhiều SP / theo danh mục không bị xóa — hàm này bỏ qua hoàn toàn.
    Trả số ladipage đã xóa trong session hiện tại (chưa commit).
    """
    ladipages = find_single_product_ladipages_for_product(db, product_db_id)
    if not ladipages:
        return 0

    bunny_urls: List[str] = []
    deleted_ids: List[int] = []
    for lp in ladipages:
        bunny_urls.extend(collect_ladipage_section_image_urls(lp))
        deleted_ids.append(lp.id)
        db.delete(lp)

    if deleted_ids:
        logger.info(
            "Xóa %s ladipage 1 SP vì sản phẩm id=%s bị xóa: %s",
            len(deleted_ids),
            product_db_id,
            deleted_ids,
        )

    if bunny_urls:
        try:
            bunny_storage.delete_bunny_storage_objects_for_urls(bunny_urls)
        except Exception:
            logger.warning(
                "Dọn ảnh Bunny ladipage sau khi xóa SP id=%s thất bại (bỏ qua)",
                product_db_id,
                exc_info=True,
            )

    return len(deleted_ids)
