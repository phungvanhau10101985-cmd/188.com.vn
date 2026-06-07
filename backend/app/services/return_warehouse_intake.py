"""Nhập hàng hoàn từ quản lý vận chuyển → tồn kho thanh lý (dòng sale kho độc lập hoặc variant theo SP gốc)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.crud.product import (
    find_product_by_listing_source_prefix,
    generate_consistent_slug,
)
from app.models.product import Product
from app.schemas.product import ProductCreate
from app.services import warehouse_clearance as wh_svc

_LISTING_SOURCE_BASE_RE = re.compile(r"^([AT])(\d{6,})$", re.IGNORECASE)


def parse_listing_source_base_sku(base_sku: str) -> Optional[Dict[str, Any]]:
    """
    Mã gốc dạng nguồn 1688/Tmall: A932203996836 hoặc T932203996836.
    Trả link nền tảng theo id số (932203996836).
    """
    raw = str(base_sku or "").strip()
    m = _LISTING_SOURCE_BASE_RE.match(raw)
    if not m and re.fullmatch(r"\d{6,}", raw):
        m = _LISTING_SOURCE_BASE_RE.match(f"A{raw}")
    if not m:
        return None
    letter = m.group(1).upper()
    offer_id = m.group(2)
    prefix = f"{letter}{offer_id}"
    if letter == "A":
        return {
            "platform": "1688",
            "listing_prefix": prefix,
            "offer_id": offer_id,
            "link_default": f"https://detail.1688.com/offer/{offer_id}.html",
            "origin": "1688",
        }
    return {
        "platform": "tmall",
        "listing_prefix": prefix,
        "offer_id": offer_id,
        "link_default": f"https://detail.tmall.com/item.htm?id={offer_id}",
        "origin": "taobao",
    }


def _listing_source_prefix_dict(listing: Dict[str, Any]) -> Dict[str, str]:
    prefix = str(listing.get("listing_prefix") or "").strip()
    return {"prefix": prefix, "prefix_key": prefix.casefold()}


def find_listing_parent_product(db: Session, base_sku: str) -> Optional[Product]:
    listing = parse_listing_source_base_sku(base_sku)
    if not listing:
        return None
    prefix = listing["listing_prefix"]
    prefix_key = prefix.casefold()

    from app.crud.product import _listing_source_prefix_from_product_id

    candidates = (
        db.query(Product)
        .filter(
            Product.is_warehouse_clearance == False,  # noqa: E712
            or_(
                Product.product_id == prefix,
                Product.product_id.ilike(f"{prefix}a188%"),
                Product.product_id.ilike(f"{prefix}A188%"),
            ),
        )
        .order_by(Product.id.asc())
        .limit(20)
        .all()
    )
    for row in candidates:
        src = _listing_source_prefix_from_product_id(getattr(row, "product_id", None))
        if src and src.get("prefix_key") == prefix_key:
            return row

    # Fallback: quét toàn bảng (mã lệch format cũ)
    row = find_product_by_listing_source_prefix(db, _listing_source_prefix_dict(listing))
    if row is None or getattr(row, "is_warehouse_clearance", False):
        return None
    return row


def resolve_base_sku_from_input(sku_input: str) -> str:
    raw = str(sku_input or "").strip()
    if not raw:
        return ""
    parsed = wh_svc.parse_warehouse_product_id(raw)
    if parsed:
        return str(parsed["base_sku"]).strip()
    return raw


def staff_warehouse_product_id(sku_input: str) -> Optional[str]:
    """
    Mã kho nhân viên gõ nguyên (vd. H9441/1/xl) — lưu đúng chuỗi này, giống cột A import.
    """
    raw = str(sku_input or "").strip()
    if "/" not in raw:
        return None
    if wh_svc.parse_warehouse_product_id(raw):
        return raw
    return None


def parsed_variant_from_warehouse_id(product_id: str) -> Dict[str, Any]:
    """Tách base / màu / size từ mã kho (không đổi chữ hoa nhân viên đã gõ)."""
    raw = str(product_id or "").strip()
    out: Dict[str, Any] = {"base_sku": resolve_base_sku_from_input(raw)}
    parsed = wh_svc.parse_warehouse_product_id(raw) or {}
    out["warehouse_color"] = parsed.get("warehouse_color")
    out["warehouse_size"] = parsed.get("warehouse_size")
    out["warehouse_unit"] = parsed.get("warehouse_unit")
    out["listing_color_image_index"] = parsed.get("listing_color_image_index")
    return out


def _parent_lookup_candidates(base_sku: str) -> List[str]:
    """Thử các biến thể mã gốc (khH0723 → H0723) chỉ khi tra SP cha."""
    sku = str(base_sku or "").strip()
    if not sku:
        return []
    out: List[str] = [sku]
    if len(sku) > 2 and sku[:2].lower() == "kh":
        stripped = sku[2:].strip()
        if stripped and stripped not in out:
            out.append(stripped)
    return out


def find_parent_for_return_intake(db: Session, base_sku: str) -> Optional[Product]:
    """Tìm SP gốc — không gắn khH0723 với H0723 nếu đã có dòng kho độc lập."""
    base = str(base_sku or "").strip()
    if not base:
        return None
    wh_rows = wh_svc.list_warehouse_variants_for_base_sku(db, base, active_only=False)
    for cand in _parent_lookup_candidates(base):
        parent = wh_svc.find_parent_product_by_base_sku(db, cand)
        if parent is None:
            continue
        if wh_rows and cand != base:
            continue
        return parent
    return find_listing_parent_product(db, base)


def _parent_summary_payload(
    parent: Product,
    *,
    listing_prefix_matched: bool = False,
) -> Dict[str, Any]:
    cn = (getattr(parent, "chinese_name", None) or "").strip() or None
    return {
        "id": parent.id,
        "product_id": parent.product_id,
        "name": parent.name,
        "price": float(parent.price or 0),
        "slug": parent.slug,
        "chinese_name": cn,
        "category": (parent.category or "").strip() or None,
        "subcategory": (parent.subcategory or "").strip() or None,
        "sub_subcategory": (parent.sub_subcategory or "").strip() or None,
        "link_default": (parent.link_default or "").strip() or None,
        "main_image": (parent.main_image or "").strip() or None,
        "listing_prefix_matched": listing_prefix_matched,
    }


def _default_unit_suffix(db: Session, base_sku: str, sku_input: str = "") -> Optional[str]:
    parsed_in = wh_svc.parse_warehouse_product_id(str(sku_input or "").strip())
    if parsed_in and parsed_in.get("warehouse_unit"):
        return str(parsed_in["warehouse_unit"]).strip()
    for wh in wh_svc.list_warehouse_variants_for_base_sku(db, base_sku, active_only=False):
        parsed = wh_svc.parse_warehouse_product_id(getattr(wh, "product_id", None))
        if parsed and parsed.get("warehouse_unit"):
            return str(parsed["warehouse_unit"]).strip()
    return None


def build_listing_source_warehouse_product_id(
    base_sku: str,
    *,
    size: Optional[str] = None,
    color_image_index: Optional[int] = None,
    unit: Optional[str] = None,
) -> str:
    """Mã kho sale A/T: base/ô_ảnh_màu, base/size/ô_ảnh_màu, hoặc base/size/unit."""
    base = str(base_sku or "").strip()
    if not base:
        raise ValueError("Thiếu mã SKU gốc.")
    size_s = str(size or "").strip()
    if color_image_index is not None:
        if size_s:
            return f"{base}/{size_s}/{int(color_image_index)}"
        return f"{base}/{int(color_image_index)}"
    if size_s and unit:
        return f"{base}/{size_s}/{str(unit).strip()}"
    if size_s:
        return f"{base}/{size_s}"
    raise ValueError("Thiếu size hoặc ô ảnh màu trên mã nguồn.")


def build_warehouse_product_id(
    base_sku: str,
    *,
    color: Optional[str],
    size: str,
    unit: Optional[str] = None,
) -> str:
    base = str(base_sku or "").strip()
    size_s = str(size or "").strip()
    if not base or not size_s:
        raise ValueError("Thiếu mã SKU gốc hoặc size.")
    color_s = str(color or "").strip()
    unit_s = str(unit or "").strip()
    if color_s:
        return f"{base}/{color_s}/{size_s}"
    if unit_s:
        return f"{base}/{size_s}/{unit_s}"
    return f"{base}/{size_s}"


def _color_options_from_product(row: Optional[Product]) -> List[Dict[str, Any]]:
    if row is None:
        return []
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for item in wh_svc._normalize_excel_colors(getattr(row, "colors", None)):
        name = str(item.get("name") or item.get("value") or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        img = str(item.get("img") or item.get("image") or "").strip() or None
        out.append({"key": key, "name": name, "image": img})
    color_single = (getattr(row, "color", None) or "").strip()
    if color_single and color_single.lower() not in seen:
        out.append({"key": color_single.lower(), "name": color_single, "image": None})
    return out


def _size_options_from_product(row: Optional[Product]) -> List[str]:
    if row is None:
        return []
    sizes: List[str] = []
    seen: Set[str] = set()
    raw_sizes = getattr(row, "sizes", None)
    if isinstance(raw_sizes, list):
        for s in raw_sizes:
            label = str(s or "").strip()
            if not label:
                continue
            key = label.upper()
            if key in seen:
                continue
            seen.add(key)
            sizes.append(label)
    return sizes


def _variant_row_payload(wh: Product) -> Dict[str, Any]:
    parsed = wh_svc.parse_warehouse_product_id(getattr(wh, "product_id", None)) or {}
    color = (getattr(wh, "color", None) or "").strip() or parsed.get("warehouse_color")
    size = ""
    if wh.sizes and isinstance(wh.sizes, list) and wh.sizes:
        size = str(wh.sizes[0] or "").strip()
    if not size:
        size = str(parsed.get("warehouse_size") or "").strip()
    unit = str(parsed.get("warehouse_unit") or "").strip() or None
    return {
        "product_id": wh.product_id,
        "color": color or None,
        "size": size or None,
        "unit": unit,
        "available": int(wh.available or 0),
        "is_active": bool(wh.is_active),
        "price": float(wh.price or 0),
    }


def lookup_return_intake_catalog(db: Session, sku_input: str) -> Dict[str, Any]:
    """Tra mã SKU → danh sách màu/size từ SP gốc + các dòng kho hiện có."""
    base_sku = resolve_base_sku_from_input(sku_input)
    if not base_sku:
        raise ValueError("Nhập mã SKU (vd. H0723 hoặc H0723/40/3).")

    raw_input = str(sku_input or "").strip()
    parent = find_parent_for_return_intake(db, base_sku)
    wh_rows = wh_svc.list_warehouse_variants_for_base_sku(db, base_sku, active_only=False)

    if parent is None and not wh_rows and raw_input:
        exact = (
            db.query(Product)
            .filter(
                or_(
                    Product.product_id == raw_input,
                    Product.code == raw_input,
                    Product.code == base_sku,
                )
            )
            .order_by(Product.is_warehouse_clearance.asc(), Product.id.asc())
            .first()
        )
        if exact is not None:
            if getattr(exact, "is_warehouse_clearance", False):
                wh_rows = [exact]
                if not (getattr(exact, "base_sku", None) or "").strip():
                    base_sku = resolve_base_sku_from_input(
                        getattr(exact, "product_id", None) or base_sku
                    )
            else:
                parent = exact

    listing_source = parse_listing_source_base_sku(base_sku)
    listing_parent = find_listing_parent_product(db, base_sku) if listing_source else None
    if parent is None and listing_parent is not None:
        parent = listing_parent

    listing_prefix_matched = bool(
        listing_source is not None
        and parent is not None
        and listing_parent is not None
        and listing_parent.id == parent.id
    )

    needs_parent_publish = False
    if parent is None and not wh_rows:
        if listing_source is not None:
            # Chưa có dòng kho — «Nhập kho» sẽ tạo SP sale độc lập (A<id>/size/unit), không đăng SP gốc.
            needs_parent_publish = True
        else:
            raise ValueError("SKU không tồn tại.")

    default_unit = _default_unit_suffix(db, base_sku, sku_input)

    if parent is not None:
        colors = wh_svc.expand_parent_colors_for_intake(parent)
        if not colors:
            colors = _color_options_from_product(parent)
    else:
        colors = _color_options_from_product(parent)
    sizes = _size_options_from_product(parent)

    color_seen = {c["key"] for c in colors}
    size_seen = {s.upper() for s in sizes}

    parsed_in = wh_svc.parse_warehouse_product_id(raw_input) or {}
    listing_idx = parsed_in.get("listing_color_image_index")
    if listing_idx is not None:
        key = f"idx:{int(listing_idx)}"
        if key not in color_seen:
            color_seen.add(key)
            colors.append(
                {
                    "key": key,
                    "name": f"Ảnh màu #{int(listing_idx)} (1688)",
                    "image": None,
                    "color_index": int(listing_idx),
                }
            )
    pc = str(parsed_in.get("warehouse_color") or "").strip()
    if pc and pc.lower() not in color_seen:
        color_seen.add(pc.lower())
        colors.append({"key": pc.lower(), "name": pc, "image": None})
    ps = str(parsed_in.get("warehouse_size") or "").strip()
    if ps and ps.upper() not in size_seen:
        size_seen.add(ps.upper())
        sizes.append(ps)

    for wh in wh_rows:
        vp = _variant_row_payload(wh)
        cname = (vp.get("color") or "").strip()
        if cname and cname.lower() not in color_seen:
            color_seen.add(cname.lower())
            colors.append({"key": cname.lower(), "name": cname, "image": None})
        ssize = (vp.get("size") or "").strip()
        if ssize and ssize.upper() not in size_seen:
            size_seen.add(ssize.upper())
            sizes.append(ssize)

    if not colors:
        colors.append({"key": "__default__", "name": "Như ảnh", "image": None})

    variants = [_variant_row_payload(wh) for wh in wh_rows]

    return {
        "base_sku": base_sku,
        "input": sku_input.strip(),
        "has_parent": parent is not None,
        "needs_parent_publish": needs_parent_publish,
        "listing_source": listing_source,
        "parent": (
            _parent_summary_payload(parent, listing_prefix_matched=listing_prefix_matched)
            if parent
            else None
        ),
        "colors": colors,
        "sizes": sizes,
        "variants": variants,
        "warehouse_row_count": len(variants),
        "default_unit": default_unit,
        "warehouse_product_id": staff_warehouse_product_id(raw_input),
        "parsed_size": str(parsed_in.get("warehouse_size") or "").strip() or None,
        "parsed_color_key": (
            f"idx:{int(listing_idx)}"
            if listing_idx is not None
            else (str(parsed_in.get("warehouse_color") or "").strip().lower() or None)
        ),
        "parsed_color_image_index": (
            int(listing_idx) if listing_idx is not None else None
        ),
    }


def _find_existing_variant(
    db: Session,
    base_sku: str,
    *,
    color: Optional[str],
    size: str,
    unit: Optional[str] = None,
) -> Optional[Product]:
    unit_s = str(unit or "").strip() or None
    for target_id in (
        build_warehouse_product_id(base_sku, color=color, size=size, unit=unit_s),
        build_warehouse_product_id(base_sku, color=color, size=size, unit=None),
    ):
        hit = db.query(Product).filter(Product.product_id == target_id).first()
        if hit is not None:
            return hit
    color_norm = (color or "").strip().lower()
    size_norm = str(size or "").strip().upper()
    unit_norm = (unit_s or "").strip()
    for wh in wh_svc.list_warehouse_variants_for_base_sku(db, base_sku, active_only=False):
        vp = _variant_row_payload(wh)
        if (vp.get("size") or "").strip().upper() != size_norm:
            continue
        wh_color = (vp.get("color") or "").strip().lower()
        if color_norm and wh_color != color_norm:
            continue
        if not color_norm and wh_color:
            continue
        wh_unit = (vp.get("unit") or "").strip()
        if unit_norm and wh_unit and wh_unit != unit_norm:
            continue
        return wh
    return None


def _template_product_for_intake(db: Session, base_sku: str) -> Optional[Product]:
    parent = find_parent_for_return_intake(db, base_sku)
    if parent is not None:
        return parent
    rows = wh_svc.list_warehouse_variants_for_base_sku(db, base_sku, active_only=False)
    return rows[0] if rows else None


def _color_for_warehouse_product_path(color_label: Optional[str]) -> Optional[str]:
    """Màu «Như ảnh» không đưa vào product_id — giống A652267320844/XL/3."""
    label = str(color_label or "").strip()
    if not label or label in ("Như ảnh", "__default__"):
        return None
    return label


def _product_orm_payload(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """Chỉ giữ cột ORM — tránh slug_seo / taxonomy_import_error từ DeepSeek."""
    allowed = {c.key for c in Product.__table__.columns}
    return {k: v for k, v in product_data.items() if k in allowed}


def _resolve_intake_color_label(
    *,
    color_key: str,
    color_label: Optional[str],
) -> Optional[str]:
    label = str(color_label or "").strip()
    if label:
        return label
    key = str(color_key or "").strip()
    if key and key != "__default__":
        return key
    if key == "__default__":
        return "Như ảnh"
    return None


def _ensure_sale_sốc_display_name(product_data: Dict[str, Any]) -> None:
    name = str(product_data.get("name") or "").strip()
    if not name:
        return
    lower = name.lower()
    if lower.startswith("sale sốc") or lower.startswith("sale soc"):
        return
    product_data["name"] = f"Sale Sốc {name}"[:500]


def build_standalone_listing_warehouse_product_data(
    db: Session,
    *,
    base_sku: str,
    chinese_name: str,
    price: float,
    size: str = "",
    color_label: Optional[str] = None,
    color_image: Optional[str] = None,
    color_index: Optional[int] = None,
    quantity: int = 1,
    unit: Optional[str] = None,
    product_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Tạo payload dòng kho thanh lý độc lập từ mã nguồn A/T — giống import Excel
    (vd. A652267320844/XL/3, KHA638492774060/29/5), không tạo SP gốc trên shop.
    """
    listing = parse_listing_source_base_sku(base_sku)
    if not listing:
        raise ValueError(
            "Chỉ hỗ trợ mã nguồn dạng A<id> (1688) hoặc T<id> (Tmall), vd. A932203996836."
        )

    base = listing["listing_prefix"]
    chinese = str(chinese_name or "").strip()
    if not chinese:
        raise ValueError("Nhập tên tiếng Trung.")
    size_s = str(size or "").strip()
    price_f = float(price or 0)
    if price_f <= 0:
        raise ValueError("Giá list phải lớn hơn 0.")

    color_label_s = str(color_label or "").strip() or None

    explicit_id = staff_warehouse_product_id(product_id or "")
    unit_s = str(unit or "").strip() or None
    size_opt = size_s or None
    listing_idx_build = color_index
    if listing_idx_build is None and explicit_id:
        parsed_explicit = wh_svc.parse_warehouse_product_id(explicit_id) or {}
        listing_idx_build = parsed_explicit.get("listing_color_image_index")
    if not size_opt and listing_idx_build is None:
        raise ValueError(
            "Nhập size hoặc dùng mã có ô ảnh màu (vd. A757876600366/4)."
        )
    if explicit_id:
        product_id = explicit_id
        parsed = wh_svc.parse_warehouse_product_id(product_id) or {
            "base_sku": base,
            "warehouse_size": size_opt,
            "warehouse_unit": unit_s,
        }
        if not parsed.get("warehouse_size") and size_opt:
            parsed["warehouse_size"] = size_opt
        if not parsed.get("warehouse_unit") and unit_s:
            parsed["warehouse_unit"] = unit_s
    else:
        color_for_path = _color_for_warehouse_product_path(color_label_s)
        if listing_idx_build is not None and not size_opt:
            product_id = build_listing_source_warehouse_product_id(
                base, color_image_index=listing_idx_build
            )
        elif size_opt:
            product_id = build_listing_source_warehouse_product_id(
                base,
                size=size_opt,
                color_image_index=listing_idx_build,
                unit=unit_s,
            )
        else:
            raise ValueError("Nhập size hoặc dùng mã có ô ảnh màu (vd. A757876600366/4).")
        parsed = wh_svc.parse_warehouse_product_id(product_id) or {
            "base_sku": base,
            "warehouse_size": size_opt or None,
            "warehouse_color": color_for_path,
            "warehouse_unit": unit_s,
            "listing_color_image_index": listing_idx_build,
        }

    color_entry: Optional[Dict[str, Any]] = None
    if color_label_s:
        color_entry = {"name": color_label_s, "value": color_label_s}
    img = str(color_image or "").strip()
    if img:
        if color_entry is None:
            color_entry = {"name": "Như ảnh", "value": "Như ảnh"}
        color_entry["img"] = img
        color_entry["image"] = img

    image_list = [img] if img else []

    product_data: Dict[str, Any] = {
        "product_id": product_id,
        "name": chinese,
        "chinese_name": chinese,
        "price": price_f,
        "sizes": [size_s] if size_s else [],
        "colors": [color_entry] if color_entry else [],
        "color": color_label_s,
        "link_default": listing["link_default"],
        "origin": listing["origin"],
        "main_image": img or None,
        "images": image_list,
        "gallery": image_list,
        "features": [],
        "is_active": True,
        "deposit_require": True,
        "available": max(1, int(quantity or 1)),
    }

    from app.services.import_link_deepseek_taxonomy import apply_deepseek_taxonomy_to_product_data

    warnings = list(apply_deepseek_taxonomy_to_product_data(db, product_data))
    if not str(product_data.get("name") or "").strip():
        product_data["name"] = chinese
    _ensure_sale_sốc_display_name(product_data)

    wh_svc.apply_warehouse_import_from_row(product_data, parsed)
    wh_svc._apply_excel_variant_media(product_data, product_data.get("colors"))

    from app.services.product_info_web_compact import compact_product_info_for_web

    compact_product_info_for_web(product_data)
    return product_data, warnings


def intake_return_to_warehouse(
    db: Session,
    *,
    base_sku: str,
    color: Optional[str],
    size: str,
    quantity: int,
    color_index: Optional[int] = None,
    color_image: Optional[str] = None,
    color_label: Optional[str] = None,
    warehouse_product_id: Optional[str] = None,
    admin_id: Optional[int] = None,
    chinese_name: Optional[str] = None,
    price: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Cộng tồn (hoặc tạo mới) dòng kho thanh lý — gắn SP gốc nếu có.
    Chưa có dòng kho (mã A/T): tạo SP sale kho độc lập (vd. A652267320844/XL/3) trong một lần.
    """
    raw_wh = staff_warehouse_product_id(warehouse_product_id or base_sku) or ""
    base = resolve_base_sku_from_input(raw_wh or base_sku)
    if not base:
        raise ValueError("Thiếu mã SKU gốc.")
    qty = max(1, int(quantity or 1))

    listing_base = parse_listing_source_base_sku(base)
    if raw_wh and listing_base:
        parsed_staff = wh_svc.parse_warehouse_product_id(raw_wh) or {}
        listing_idx_only = parsed_staff.get("listing_color_image_index")
        if listing_idx_only is not None and not parsed_staff.get("warehouse_size"):
            # Mã chỉ ô ảnh màu (A…/4) — không ghép size UI (vd. 40 nhầm với ô màu).
            wh_parts = [p.strip() for p in raw_wh.split("/") if p.strip()]
            color_only_id = len(wh_parts) == 2
            size_for_id = str(size or "").strip()
            if size_for_id and not color_only_id:
                raw_wh = build_listing_source_warehouse_product_id(
                    base,
                    size=size_for_id,
                    color_image_index=int(listing_idx_only),
                )

    display_color = _resolve_intake_color_label(
        color_key=str(color or "").strip(),
        color_label=color_label,
    )

    color_key = str(color or "").strip()
    if color_key.startswith("idx:"):
        try:
            color_index = int(color_key.split(":", 1)[1])
        except (TypeError, ValueError):
            pass

    existing: Optional[Product] = None
    if raw_wh:
        existing = db.query(Product).filter(Product.product_id == raw_wh).first()
    else:
        size_s = str(size or "").strip()
        unit_suffix = _default_unit_suffix(db, base, base_sku)
        listing_idx_ex: Optional[int] = None
        if color_key.startswith("idx:"):
            try:
                listing_idx_ex = int(color_key.split(":", 1)[1])
            except (TypeError, ValueError):
                listing_idx_ex = None
        if not size_s and listing_idx_ex is not None and listing_base:
            pid_no_size = build_listing_source_warehouse_product_id(
                base, color_image_index=listing_idx_ex
            )
            existing = db.query(Product).filter(Product.product_id == pid_no_size).first()
        elif not size_s:
            raise ValueError(
                "Chọn size hoặc đánh dấu «Không có size» (túi xách, đồng hồ…)."
            )
        else:
            existing = _find_existing_variant(
                db,
                base,
                color=_color_for_warehouse_product_path(display_color),
                size=size_s,
                unit=unit_suffix,
            )
    if existing is not None:
        before = int(existing.available or 0)
        existing.available = before + qty
        existing.is_active = True
        existing.is_warehouse_clearance = True
        if not (existing.base_sku or "").strip():
            existing.base_sku = base
        parent_for_fill = find_parent_for_return_intake(db, base)
        if parent_for_fill is not None:
            wh_svc.backfill_warehouse_row_from_parent(
                existing,
                parent_for_fill,
                color_name=None,
                color_index=color_index,
            )
            if not (existing.base_sku or "").strip():
                existing.base_sku = wh_svc.resolve_parent_base_sku(parent_for_fill)
        db.commit()
        db.refresh(existing)
        return {
            "action": "updated",
            "product_id": existing.product_id,
            "slug": (existing.slug or "").strip() or None,
            "available_before": before,
            "available_after": int(existing.available or 0),
            "quantity_added": qty,
            "is_warehouse_clearance": True,
            "admin_id": admin_id,
        }

    template = _template_product_for_intake(db, base)
    listing_for_standalone = parse_listing_source_base_sku(base)
    standalone_warnings: List[str] = []
    used_standalone_listing = False

    if raw_wh:
        product_id = raw_wh
        parsed = parsed_variant_from_warehouse_id(raw_wh)
        parsed["base_sku"] = base
    else:
        size_s = str(size or "").strip()
        unit_suffix = _default_unit_suffix(db, base, base_sku)
        listing_idx = None
        if color_key.startswith("idx:"):
            try:
                listing_idx = int(color_key.split(":", 1)[1])
            except (TypeError, ValueError):
                listing_idx = None
        if listing_idx is None and color_index is not None:
            listing_idx = color_index
        if listing_base and listing_idx is not None:
            product_id = build_listing_source_warehouse_product_id(
                base,
                size=size_s or None,
                color_image_index=listing_idx,
            )
            parsed = wh_svc.parse_warehouse_product_id(product_id) or {
                "base_sku": base,
                "warehouse_size": size_s or None,
                "listing_color_image_index": listing_idx,
            }
        elif listing_base and unit_suffix and not listing_idx and size_s:
            product_id = build_listing_source_warehouse_product_id(
                base, size=size_s, unit=unit_suffix
            )
            parsed = wh_svc.parse_warehouse_product_id(product_id) or {
                "base_sku": base,
                "warehouse_size": size_s,
                "warehouse_unit": unit_suffix,
            }
        elif size_s:
            product_id = build_warehouse_product_id(
                base,
                color=_color_for_warehouse_product_path(display_color),
                size=size_s,
                unit=unit_suffix,
            )
            parsed = {
                "base_sku": base,
                "warehouse_size": size_s,
                "warehouse_color": display_color,
            }
            if unit_suffix:
                parsed["warehouse_unit"] = unit_suffix
        elif listing_base and listing_idx is not None:
            product_id = build_listing_source_warehouse_product_id(
                base, color_image_index=listing_idx
            )
            parsed = wh_svc.parse_warehouse_product_id(product_id) or {
                "base_sku": base,
                "listing_color_image_index": listing_idx,
            }
        else:
            raise ValueError(
                "Chọn size hoặc dùng mã có ô ảnh màu (vd. A757876600366/4)."
            )

    product_data: Dict[str, Any] = {"product_id": product_id, "available": qty}
    parent = find_parent_for_return_intake(db, base)

    if template is None and listing_for_standalone is not None:
        size_s = str(size or "").strip() or str(parsed.get("warehouse_size") or "").strip()
        listing_idx_create = parsed.get("listing_color_image_index")
        if not size_s and listing_idx_create is None and not raw_wh:
            raise ValueError("Chọn size, hoặc dùng mã chỉ có ô ảnh màu (vd. A…/4).")
        try:
            price_f = float(price or 0)
        except (TypeError, ValueError):
            price_f = 0.0
        unit_suffix = _default_unit_suffix(db, base, base_sku)
        idx_create = parsed.get("listing_color_image_index")
        if idx_create is None and color_key.startswith("idx:"):
            try:
                idx_create = int(color_key.split(":", 1)[1])
            except (TypeError, ValueError):
                idx_create = None
        product_data, standalone_warnings = build_standalone_listing_warehouse_product_data(
            db,
            base_sku=base,
            chinese_name=str(chinese_name or "").strip(),
            price=price_f,
            size=size_s,
            color_label=display_color,
            color_image=color_image,
            color_index=idx_create,
            quantity=qty,
            unit=unit_suffix,
            product_id=raw_wh or None,
        )
        product_data["available"] = qty
        parent = None
        used_standalone_listing = True
    elif template is None:
        raise ValueError(
            f"Chưa có SP gốc hoặc dòng kho «{base}» — import sản phẩm gốc, một dòng kho mẫu, "
            "hoặc dùng mã nguồn A/T kèm tên Trung + giá list."
        )
    elif parent is not None:
        wh_svc.merge_return_intake_from_parent(
            parent,
            product_data,
            parsed,
            color_name=display_color,
            color_index=color_index,
            color_image=color_image,
        )
        product_data["available"] = qty
        if raw_wh and parsed.get("warehouse_size"):
            product_data["sizes"] = [str(parsed["warehouse_size"])]
    elif not used_standalone_listing and getattr(template, "is_warehouse_clearance", False):
        for field in wh_svc._WAREHOUSE_CLONE_FIELDS:
            if hasattr(template, field):
                product_data[field] = getattr(template, field)
        for field in wh_svc._WAREHOUSE_INTAKE_MEDIA_FIELDS:
            if hasattr(template, field):
                val = getattr(template, field)
                if val is not None and val != [] and val != "":
                    product_data[field] = val
        size_for_row = str(parsed.get("warehouse_size") or size or "").strip()
        wh_svc._apply_warehouse_variant_fields(
            product_data,
            parsed,
            excel_sizes=[size_for_row] if size_for_row else None,
            excel_colors=product_data.get("colors"),
        )
        wh_svc._apply_excel_variant_media(product_data, product_data.get("colors"))
        wh_svc._apply_parent_media_fallback(product_data, template)
    elif not used_standalone_listing:
        wh_svc.merge_return_intake_from_parent(
            template,
            product_data,
            parsed,
            color_name=display_color,
            color_index=color_index,
            color_image=color_image,
        )
        product_data["available"] = qty

    from app.services.alicdn_urls import normalize_product_data_image_urls_for_db

    link_parent = parent if not used_standalone_listing else None
    if link_parent is not None:
        wh_svc.attach_warehouse_row_to_parent(product_data, link_parent)
    template_name = (getattr(template, "name", None) or "") if template is not None else ""
    product_data["slug"] = generate_consistent_slug(
        product_data.get("name") or template_name or base,
        product_id,
    )

    normalize_product_data_image_urls_for_db(product_data)
    from app.services.product_search_document import assign_search_document_to_mapping

    assign_search_document_to_mapping(product_data)

    row = Product(**_product_orm_payload(product_data))
    db.add(row)
    db.commit()
    db.refresh(row)

    out: Dict[str, Any] = {
        "action": "created",
        "product_id": row.product_id,
        "slug": (row.slug or "").strip() or None,
        "available_before": 0,
        "available_after": int(row.available or 0),
        "quantity_added": qty,
        "is_warehouse_clearance": True,
        "admin_id": admin_id,
    }
    if used_standalone_listing and standalone_warnings:
        out["warnings"] = standalone_warnings
    return out


def publish_listing_parent_for_return_intake(
    db: Session,
    *,
    base_sku: str,
    chinese_name: str,
    price: float,
    size: str,
    color_image: Optional[str] = None,
    color_name: str = "Như ảnh",
    admin_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Tạo SP gốc từ mã A/T + id nguồn — DeepSeek dịch tên & gán danh mục."""
    base = resolve_base_sku_from_input(base_sku)
    listing = parse_listing_source_base_sku(base)
    if not listing:
        raise ValueError(
            "Chỉ hỗ trợ mã nguồn dạng A<id> (1688) hoặc T<id> (Tmall), vd. A932203996836."
        )

    prefix = listing["listing_prefix"]
    existing = find_listing_parent_product(db, base)
    if existing is not None:
        raise ValueError(
            f"SP gốc đã tồn tại: {existing.product_id} — {existing.name}. "
            "Dùng «Tra cứu SKU» lại rồi nhập kho."
        )

    chinese = str(chinese_name or "").strip()
    if not chinese:
        raise ValueError("Nhập tên tiếng Trung.")
    size_s = str(size or "").strip()
    if not size_s:
        raise ValueError("Nhập size.")
    price_f = float(price or 0)
    if price_f <= 0:
        raise ValueError("Giá phải lớn hơn 0.")

    color_label = str(color_name or "Như ảnh").strip() or "Như ảnh"
    color_entry: Dict[str, Any] = {"name": color_label, "value": color_label}
    img = str(color_image or "").strip()
    if img:
        color_entry["img"] = img
        color_entry["image"] = img

    image_list = [img] if img else []

    product_data: Dict[str, Any] = {
        "product_id": prefix,
        "name": chinese,
        "chinese_name": chinese,
        "price": price_f,
        "sizes": [size_s] if size_s else [],
        "colors": [color_entry],
        "color": color_label,
        "link_default": listing["link_default"],
        "origin": listing["origin"],
        "main_image": img or None,
        "images": image_list,
        "gallery": image_list,
        "features": [],
        "is_active": True,
        "deposit_require": True,
        "available": 500,
    }

    from app.services.import_link_deepseek_taxonomy import apply_deepseek_taxonomy_to_product_data

    warnings = list(apply_deepseek_taxonomy_to_product_data(db, product_data))

    if not str(product_data.get("name") or "").strip():
        product_data["name"] = chinese

    for key, label in (
        ("category", "danh mục cấp 1"),
        ("subcategory", "danh mục cấp 2"),
        ("sub_subcategory", "danh mục cấp 3"),
    ):
        if not str(product_data.get(key) or "").strip():
            warnings.append(f"Chưa gán {label} — có thể bổ sung sau trên trang SP.")

    from app.services.alicdn_urls import normalize_product_data_image_urls_for_db
    from app.services.product_info_web_compact import compact_product_info_for_web

    normalize_product_data_image_urls_for_db(product_data)
    compact_product_info_for_web(product_data)
    product_data["slug"] = generate_consistent_slug(
        product_data.get("name") or chinese,
        prefix,
    )

    allowed = set(ProductCreate.model_fields.keys())
    payload = {k: v for k, v in product_data.items() if k in allowed}
    from app.crud import product as product_crud

    row = product_crud.create_product(db, ProductCreate(**payload))

    return {
        "ok": True,
        "product_id": row.product_id,
        "name": row.name,
        "slug": row.slug,
        "category": row.category,
        "subcategory": row.subcategory,
        "sub_subcategory": row.sub_subcategory,
        "link_default": row.link_default,
        "warnings": warnings,
        "admin_id": admin_id,
        "message": f"Đã đăng SP gốc «{row.product_id}» — {row.name}.",
    }
