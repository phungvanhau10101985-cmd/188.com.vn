"""
Chuỗi tìm kiếm gom sẵn (search_document) — khớp apply_product_search_word_filters / ILIKE concat cũ.
Cập nhật khi create/update/import; index pg_trgm trên Postgres.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Optional

SEARCH_DOCUMENT_FIELDS: Iterable[str] = (
    "name",
    "slug",
    "code",
    "category",
    "subcategory",
    "sub_subcategory",
    "material",
    "style",
    "color",
    "occasion",
    "features",
    "sizes",
    "product_info",
)


def _field_part(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _read_field(source: Any, name: str) -> Any:
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def build_product_search_document(
    *,
    product: Any = None,
    mapping: Optional[Dict[str, Any]] = None,
) -> str:
    """Ghép các cột tìm kiếm (lower) — cùng thứ tự với func.concat trong product.py."""
    src = mapping if mapping is not None else product
    if src is None:
        return ""
    parts = [_field_part(_read_field(src, name)) for name in SEARCH_DOCUMENT_FIELDS]
    return " ".join(parts).lower()


def assign_search_document_to_mapping(data: Dict[str, Any]) -> None:
    data["search_document"] = build_product_search_document(mapping=data)


def assign_search_document_to_product(product: Any) -> None:
    product.search_document = build_product_search_document(product=product)


def product_search_blob(product: Any) -> str:
    """Blob dùng cho product_matches_search_keyword — ưu tiên search_document."""
    doc = getattr(product, "search_document", None)
    if doc:
        return str(doc)
    return build_product_search_document(product=product)
