"""
Khi nguồn hết hàng nhưng kho thanh lý còn tồn: cất colors/sizes order nguồn rồi xóa
khỏi sản phẩm gốc. Dòng kho giữ nguyên. Khi nguồn có hàng lại thì trả colors/sizes.
"""
from __future__ import annotations

import copy
import logging
from typing import Optional, Set

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.product import Product
from app.services.warehouse_clearance import (
    _resolve_base_sku_for_parent,
    list_warehouse_variants_for_base_sku,
)

logger = logging.getLogger(__name__)


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _parent_has_active_warehouse_stock(db: Session, product: Product) -> bool:
    if getattr(product, "is_warehouse_clearance", False):
        return False
    base = _resolve_base_sku_for_parent(product)
    if not base:
        return False
    for row in list_warehouse_variants_for_base_sku(db, base, active_only=True):
        if int(row.available or 0) > 0:
            return True
    return False


def restore_source_variants(product: Product) -> bool:
    """Trả colors/sizes đã cất. Không đụng dòng kho thanh lý."""
    if getattr(product, "is_warehouse_clearance", False):
        return False
    snap = getattr(product, "source_variant_snapshot", None)
    if not isinstance(snap, dict):
        return False
    if "colors" not in snap and "sizes" not in snap:
        return False
    product.colors = copy.deepcopy(_as_list(snap.get("colors")))
    product.sizes = copy.deepcopy(_as_list(snap.get("sizes")))
    product.source_variant_snapshot = None
    return True


def stash_source_variants_if_warehouse_remains(
    db: Session,
    product: Product,
    *,
    warehouse_bases: Optional[Set[str]] = None,
) -> bool:
    """
    Nguồn hết hàng và còn dòng kho active, tồn > 0: lưu colors/sizes rồi xóa trên SP gốc.
    Không có biến thể nguồn, hoặc không còn kho, thì giữ nguyên.
    """
    if getattr(product, "is_warehouse_clearance", False):
        return False
    if warehouse_bases is not None:
        base = (_resolve_base_sku_for_parent(product) or "").strip()
        if not base or base not in warehouse_bases:
            return False
    elif not _parent_has_active_warehouse_stock(db, product):
        return False

    colors = _as_list(getattr(product, "colors", None))
    sizes = _as_list(getattr(product, "sizes", None))
    if not colors and not sizes:
        return False

    product.source_variant_snapshot = {
        "colors": copy.deepcopy(colors),
        "sizes": copy.deepcopy(sizes),
    }
    product.colors = []
    product.sizes = []
    return True


def apply_source_stock_variant_policy(db: Session, product: Product, *, new_status: str) -> None:
    status = (new_status or "").strip().lower()
    if status == "out_of_stock":
        stash_source_variants_if_warehouse_remains(db, product)
    elif status == "in_stock":
        restore_source_variants(product)


def warehouse_bases_with_stock(db: Session) -> Set[str]:
    rows = (
        db.query(Product.base_sku, Product.product_id)
        .filter(
            Product.is_warehouse_clearance == True,  # noqa: E712
            Product.is_active == True,  # noqa: E712
            Product.available > 0,
        )
        .all()
    )
    bases: Set[str] = set()
    for base_sku, product_id in rows:
        base = str(base_sku or "").strip()
        if not base and product_id and "/" in str(product_id):
            base = str(product_id).split("/", 1)[0].strip()
        if base:
            bases.add(base)
    return bases


def backfill_oos_parents_with_warehouse_stock(db: Session) -> int:
    """Một lượt: SP gốc đang out_of_stock mà còn kho thì cất và xóa colors/sizes."""
    bases = warehouse_bases_with_stock(db)
    if not bases:
        return 0
    changed = 0
    base_list = sorted(bases)
    for offset in range(0, len(base_list), 400):
        chunk = base_list[offset : offset + 400]
        parents = (
            db.query(Product)
            .filter(
                Product.source_stock_status == "out_of_stock",
                or_(
                    Product.is_warehouse_clearance == False,  # noqa: E712
                    Product.is_warehouse_clearance.is_(None),
                ),
                or_(Product.code.in_(chunk), Product.product_id.in_(chunk)),
            )
            .all()
        )
        for product in parents:
            if stash_source_variants_if_warehouse_remains(
                db, product, warehouse_bases=bases
            ):
                changed += 1
        db.commit()
    if changed:
        logger.info("source variant oos backfill stripped colors/sizes on %s parent(s)", changed)
    return changed
