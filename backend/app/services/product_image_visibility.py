"""
Ẩn / gỡ SP storefront không có ảnh đại diện hợp lệ khỏi catalog.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.product import Product

_logger = logging.getLogger(__name__)

_INVALID_LITERALS = frozenset({"null", "none", "nan", "undefined", "n/a", "-", "0"})
_PLACEHOLDER_HOST_RE = re.compile(r"^(?:https?://)?(?:www\.)?188\.com\.vn/?$", re.I)


def _norm_url(raw: Any) -> str:
    return str(raw or "").strip()


def is_plausible_product_image_url(url: Any) -> bool:
    """URL ảnh SP hợp lệ cho storefront (http/https, //, /path, data:image)."""
    u = _norm_url(url)
    if not u or u.lower() in _INVALID_LITERALS:
        return False
    if _PLACEHOLDER_HOST_RE.match(u):
        return False
    if u.lower().startswith("data:image"):
        return len(u) > 16
    if u.startswith("//"):
        return len(u) > 4 and "." in u[2:]
    if u.startswith("/"):
        return len(u) > 2
    if u.startswith(("http://", "https://")):
        return len(u) > 12 and "." in u
    return False


def _iter_image_candidates(product: Product) -> Iterable[str]:
    main = _norm_url(getattr(product, "main_image", None))
    if main:
        yield main

    for field in ("images", "gallery"):
        raw = getattr(product, field, None) or []
        if isinstance(raw, list):
            for item in raw:
                s = _norm_url(item)
                if s:
                    yield s

    colors = getattr(product, "colors", None) or []
    if isinstance(colors, list):
        for entry in colors:
            if isinstance(entry, dict):
                for key in ("img", "image", "url"):
                    s = _norm_url(entry.get(key))
                    if s:
                        yield s


def resolve_product_display_image_url(product: Product) -> Optional[str]:
    """Ảnh đại diện thực tế dùng cho thẻ SP / PDP."""
    for url in _iter_image_candidates(product):
        if is_plausible_product_image_url(url):
            return url
    return None


def product_has_storefront_image(product: Product) -> bool:
    return resolve_product_display_image_url(product) is not None


def _variant_image_url(entry: dict) -> str:
    for key in ("img", "image_url", "url", "image"):
        s = _norm_url(entry.get(key))
        if s:
            return s
    return ""


def _variant_entry_has_name_or_http_image(entry: dict) -> bool:
    if _norm_url(entry.get("name")):
        return True
    img = _variant_image_url(entry)
    return img.startswith("http://") or img.startswith("https://")


def colors_valid_for_import(colors: Any) -> bool:
    """Variant/colors hợp lệ trước import: không rỗng []; ít nhất 1 màu có tên hoặc URL ảnh http(s)."""
    if not isinstance(colors, list) or len(colors) == 0:
        return False
    for entry in colors:
        if isinstance(entry, dict) and _variant_entry_has_name_or_http_image(entry):
            return True
    return False


def product_should_remove_after_localization(product: Product) -> bool:
    """SP không còn Variant hoặc ảnh hiển thị sau bản địa hóa."""
    colors = getattr(product, "colors", None) or []
    if not isinstance(colors, list) or len(colors) == 0:
        return True
    if not product_has_storefront_image(product):
        return True
    return False


def delete_product_if_no_variant_or_images(
    db: Session,
    product: Product,
    *,
    reason: str = "Variant/ảnh rỗng",
) -> str:
    """
    Xóa SP khi không còn Variant/ảnh; nếu nghiệp vụ kho chặn xóa thì gỡ khỏi web.
    Trả về 'deleted', 'deactivated', hoặc 'kept'.
    """
    if not product_should_remove_after_localization(product):
        return "kept"

    from app.crud.product import _delete_product_orm_only
    from app.services import warehouse_clearance as wh_clearance_svc

    pk = getattr(product, "id", None)
    pid = getattr(product, "product_id", None)
    try:
        wh_clearance_svc.assert_product_deletion_allowed(db, product)
        _delete_product_orm_only(db, product)
        _logger.info("Đã xóa SP (%s): id=%s product_id=%s", reason, pk, pid)
        return "deleted"
    except ValueError as exc:
        product.is_active = False
        _logger.warning(
            "SP không xóa được (%s), đã gỡ khỏi web: id=%s product_id=%s — %s",
            reason,
            pk,
            pid,
            exc,
        )
        return "deactivated"


def storefront_image_sql_filter():
    """
    Lọc nhanh ở SQL — chỉ loại main_image *đã set* nhưng rõ ràng không hợp lệ.
    main_image trống vẫn qua SQL (ảnh có thể nằm trong images/gallery/colors — kiểm tra Python).
    """
    mi = func.trim(Product.main_image)
    explicitly_bad_main = and_(
        Product.main_image.isnot(None),
        mi != "",
        or_(
            func.lower(mi).in_(tuple(_INVALID_LITERALS)),
            func.lower(mi).like("%188.com.vn%"),
            and_(
                ~or_(
                    mi.ilike("http%"),
                    mi.ilike("https%"),
                    mi.ilike("//%"),
                    mi.ilike("/%"),
                    mi.ilike("data:image%"),
                ),
            ),
        ),
    )
    return ~explicitly_bad_main


def apply_storefront_image_filter(query, *, enabled: bool = True):
    if not enabled:
        return query
    return query.filter(storefront_image_sql_filter())


def repair_main_image_from_candidates(product: Product) -> bool:
    """Gán main_image từ images/gallery/colors nếu đang trống hoặc không hợp lệ."""
    url = resolve_product_display_image_url(product)
    if not url:
        return False
    current = _norm_url(getattr(product, "main_image", None))
    if current == url and is_plausible_product_image_url(current):
        return False
    product.main_image = url
    return True


def deactivate_product_without_storefront_image(
    db: Session,
    product: Product,
    *,
    commit: bool = True,
) -> bool:
    """Gỡ SP khỏi web (is_active=False) khi không có ảnh hợp lệ."""
    if product is None:
        return False
    if not getattr(product, "is_active", True):
        return False
    if repair_main_image_from_candidates(product):
        if commit:
            db.commit()
        return False
    if product_has_storefront_image(product):
        return False
    product.is_active = False
    if commit:
        db.commit()
    _logger.info(
        "Đã gỡ SP không có ảnh khỏi storefront: id=%s product_id=%s",
        getattr(product, "id", None),
        getattr(product, "product_id", None),
    )
    return True


def deactivate_products_without_storefront_image(
    db: Session,
    *,
    limit: int = 200,
    commit: bool = True,
) -> int:
    """
    Quét batch SP đang active nhưng không có ảnh hợp lệ → is_active=False.
    """
    if limit <= 0:
        return 0

    scan_limit = max(limit * 5, limit)
    rows = (
        db.query(Product)
        .filter(Product.is_active.is_(True))
        .order_by(Product.updated_at.asc().nullsfirst(), Product.id.asc())
        .limit(scan_limit)
        .all()
    )
    repaired = 0
    deactivated = 0
    for row in rows:
        if deactivated >= limit:
            break
        if repair_main_image_from_candidates(row):
            repaired += 1
            continue
        if product_has_storefront_image(row):
            continue
        row.is_active = False
        deactivated += 1

    if (repaired or deactivated) and commit:
        db.commit()
        if repaired:
            _logger.info("Batch sửa main_image cho %s SP từ gallery/colors", repaired)
        if deactivated:
            _logger.info("Batch gỡ %s SP không có ảnh khỏi storefront", deactivated)
    return deactivated
