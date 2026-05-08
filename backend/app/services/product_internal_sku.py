"""SKU hiển thị web: đúng 1 chữ Latin in hoa + 4 chữ số (vd K0842).

Đảm bảo không trùng trong một lô import (`batch_reserved`) và không trùng `products.code` đã có
(trừ bản ghi `exclude_product_id` khi đang cập nhật).
"""
from __future__ import annotations

import copy
import json
import re
import secrets
import string
from typing import Any, Optional, Set

from sqlalchemy.orm import Session

from app.models.product import Product

INTERNAL_SKU_RE = re.compile(r"^[A-Z][0-9]{4}$")
_LETTERS = string.ascii_uppercase
_MAX_RANDOM_TRIES = 50_000


def _code_taken(db: Session, code: str, exclude_product_id: Optional[int]) -> bool:
    q = db.query(Product.id).filter(Product.code == code)
    if exclude_product_id is not None:
        q = q.filter(Product.id != exclude_product_id)
    return q.first() is not None


def _random_sku() -> str:
    return secrets.choice(_LETTERS) + f"{secrets.randbelow(10000):04d}"


def ensure_unique_internal_product_code(
    db: Session,
    proposed: Optional[str],
    *,
    exclude_product_id: Optional[int] = None,
    batch_reserved: Optional[Set[str]] = None,
) -> str:
    """
    Trả `code` đúng `[A-Z][0-9]{4}`.

    - Nếu `proposed` đã đúng định dạng (không phân biệt hoa/thường chữ cái đầu),
      không trùng `batch_reserved` và không bị SP khác chiếm trong DB → giữ.
    - Ngược lại → sinh ngẫu nhiên; `batch_reserved` được mutate để tránh trùng trong cùng batch.
    """
    reserved = batch_reserved if batch_reserved is not None else set()

    raw = (proposed or "").strip()
    if raw:
        cand = raw.upper()
        if INTERNAL_SKU_RE.fullmatch(cand):
            if cand not in reserved and not _code_taken(db, cand, exclude_product_id):
                reserved.add(cand)
                return cand

    for _ in range(_MAX_RANDOM_TRIES):
        sku = _random_sku()
        if sku in reserved:
            continue
        if _code_taken(db, sku, exclude_product_id):
            continue
        reserved.add(sku)
        return sku

    for letter in _LETTERS:
        for n in range(10000):
            sku = f"{letter}{n:04d}"
            if sku in reserved:
                continue
            if _code_taken(db, sku, exclude_product_id):
                continue
            reserved.add(sku)
            return sku

    raise RuntimeError("product_internal_sku: không còn mã trống (A-Z × 0000-9999).")


def sync_internal_code_into_product_info(product_info: Any, code: str) -> Any:
    """
    Ghi `product_info.product_info.sku` = mã nội bộ (A1234).
    Slug link / id offer không đặt vào đây (giữ ở `source_slug`, variants.slug…).
    """
    if not (code or "").strip():
        return product_info
    sku_clean = (code or "").strip().upper()

    root: Any = product_info
    if root is None:
        root = {}
    elif isinstance(root, str):
        s = root.strip()
        if not s:
            root = {}
        else:
            try:
                root = json.loads(s)
            except json.JSONDecodeError:
                return product_info
    if not isinstance(root, dict):
        return product_info

    out = copy.deepcopy(root)
    inner = out.get("product_info")
    inner_dict = dict(inner) if isinstance(inner, dict) else {}
    inner_dict["sku"] = sku_clean
    out["product_info"] = inner_dict
    return out
