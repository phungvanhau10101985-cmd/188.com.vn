# backend/app/services/ladipage_cleanup.py
"""Dọn ladipage khi sản phẩm / dữ liệu liên quan thay đổi.

Chỉ xóa ladipage **1 sản phẩm** khi sản phẩm đó bị xóa.
Ladipage **nhiều sản phẩm** hoặc **theo danh mục** luôn được giữ nguyên,
kể cả khi một sản phẩm trong ladipage bị xóa.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence

from sqlalchemy import cast, func, or_
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


def _dialect_name(db: Session) -> str:
    try:
        bind = db.get_bind()
    except Exception:
        return ""
    return str(getattr(getattr(bind, "dialect", None), "name", "") or "")


def _filter_single_product_ladipages_query(
    db: Session,
    q,
    product_db_ids: Sequence[int],
):
    """
    Thu hẹp SQL trước khi lọc Python.
    Giữ đúng semantics: chỉ ladipage `products` có đúng 1 id ∈ product_db_ids.
    """
    ids = [int(x) for x in product_db_ids if int(x) > 0]
    if not ids:
        return q.filter(Ladipage.id.in_([]))

    q = q.filter(Ladipage.source_type == "products")
    try:
        pid_len = func.coalesce(func.json_array_length(Ladipage.product_ids), 0)
        q = q.filter(pid_len == 1)
    except Exception:
        # Dialect/FakeDb không hỗ trợ json_array_length — để Python filter.
        return q

    id_strs = [str(i) for i in ids]
    dialect = _dialect_name(db)
    if dialect == "postgresql":
        try:
            from sqlalchemy.dialects.postgresql import JSONB

            first = func.jsonb_extract_path_text(cast(Ladipage.product_ids, JSONB), "0")
            return q.filter(first.in_(id_strs))
        except Exception:
            logger.debug("ladipage JSONB filter fallback", exc_info=True)

    # SQLite / khác: khớp mảng JSON gọn [id] hoặc ["id"] (đủ cho dữ liệu app ghi).
    exacts = []
    for i in ids:
        exacts.append([i])
        exacts.append([str(i)])
    try:
        return q.filter(or_(*[Ladipage.product_ids == ex for ex in exacts]))
    except Exception:
        return q


def find_single_product_ladipages_for_products(
    db: Session, product_db_ids: Sequence[int]
) -> Dict[int, List[Ladipage]]:
    """
    Một query cho nhiều ``products.id`` — map id → list ladipage 1-SP.
    Tránh full-scan toàn bộ bảng ladipages cho mỗi sản phẩm.
    """
    ordered: List[int] = []
    seen: set[int] = set()
    for raw in product_db_ids:
        try:
            pk = int(raw)
        except (TypeError, ValueError):
            continue
        if pk <= 0 or pk in seen:
            continue
        seen.add(pk)
        ordered.append(pk)
    if not ordered:
        return {}

    q = db.query(Ladipage)
    q = _filter_single_product_ladipages_query(db, q, ordered)
    rows = q.all()

    out: Dict[int, List[Ladipage]] = {pk: [] for pk in ordered}
    for lp in rows:
        ids = _normalize_product_ids(lp.product_ids)
        if len(ids) != 1:
            continue
        pk = ids[0]
        if pk in out and is_single_product_ladipage_for_product(lp, pk):
            out[pk].append(lp)
    return out


def find_single_product_ladipages_for_product(db: Session, product_db_id: int) -> List[Ladipage]:
    return find_single_product_ladipages_for_products(db, [product_db_id]).get(
        int(product_db_id), []
    )


def get_published_single_product_ladipage_slug(db: Session, product_db_id: int) -> str | None:
    """Slug ladipage 1 SP đã publish gắn với ``products.id`` — dùng redirect PDP → /lp/…"""
    pid = int(product_db_id)
    q = db.query(Ladipage).filter(Ladipage.status == "published")
    q = _filter_single_product_ladipages_query(db, q, [pid])
    rows = q.order_by(
        Ladipage.published_at.desc(), Ladipage.updated_at.desc(), Ladipage.id.desc()
    ).all()
    for lp in rows:
        if is_single_product_ladipage_for_product(lp, pid):
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


def delete_single_product_ladipages_for_products(
    db: Session,
    product_db_ids: Sequence[int],
    *,
    defer_bunny: bool = False,
    prefetched: Optional[Dict[int, List[Ladipage]]] = None,
) -> List[str]:
    """
    Xóa mọi ladipage 1-SP gắn các ``products.id`` trong session (chưa commit).
    ``defer_bunny=True``: không gọi Bunny sync — trả URL để enqueue sau commit.
    """
    by_id = (
        prefetched
        if prefetched is not None
        else find_single_product_ladipages_for_products(db, product_db_ids)
    )
    bunny_urls: List[str] = []
    url_seen: set[str] = set()
    deleted_pairs: List[tuple[int, int]] = []

    for pk, ladipages in by_id.items():
        for lp in ladipages:
            for url in collect_ladipage_section_image_urls(lp):
                if url not in url_seen:
                    url_seen.add(url)
                    bunny_urls.append(url)
            deleted_pairs.append((int(pk), int(lp.id)))
            db.delete(lp)

    if deleted_pairs:
        by_product: Dict[int, List[int]] = {}
        for pk, lp_id in deleted_pairs:
            by_product.setdefault(pk, []).append(lp_id)
        logger.info(
            "Xóa %s ladipage 1 SP vì xóa sản phẩm: %s",
            len(deleted_pairs),
            {str(k): v for k, v in list(by_product.items())[:40]},
        )

    if not bunny_urls:
        return []

    if defer_bunny:
        return bunny_urls

    try:
        bunny_storage.delete_bunny_storage_objects_for_urls(bunny_urls)
    except Exception:
        logger.warning(
            "Dọn ảnh Bunny ladipage sau khi xóa SP thất bại (bỏ qua)",
            exc_info=True,
        )
    return []


def delete_single_product_ladipages_for_product(
    db: Session,
    product_db_id: int,
    *,
    defer_bunny: bool = False,
) -> List[str]:
    """
    Xóa ladipage 1 sản phẩm khi sản phẩm chính bị xóa khỏi DB.

    Ladipage nhiều SP / theo danh mục không bị xóa — hàm này bỏ qua hoàn toàn.
    Trả URL Bunny còn phải dọn khi ``defer_bunny=True``; ngược lại [] (đã sync hoặc không có).
    """
    return delete_single_product_ladipages_for_products(
        db, [product_db_id], defer_bunny=defer_bunny
    )
