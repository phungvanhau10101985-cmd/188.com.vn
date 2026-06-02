"""Nhập hàng hoàn từ quản lý vận chuyển → tồn kho thanh lý (variant theo mã SKU gốc)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.crud.product import generate_consistent_slug
from app.models.product import Product
from app.services import warehouse_clearance as wh_svc


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
    parts = [p.strip() for p in raw.split("/") if p.strip()]
    out["warehouse_color"] = parsed.get("warehouse_color")
    out["warehouse_size"] = parsed.get("warehouse_size")
    out["warehouse_unit"] = parsed.get("warehouse_unit")
    if len(parts) >= 3 and out.get("warehouse_color") is None and out.get("warehouse_size"):
        out["warehouse_color"] = parts[1]
        out["warehouse_size"] = parts[2]
    elif len(parts) == 2 and not out.get("warehouse_size"):
        out["warehouse_size"] = parts[1]
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
    return None


def _default_unit_suffix(db: Session, base_sku: str, sku_input: str = "") -> Optional[str]:
    parsed_in = wh_svc.parse_warehouse_product_id(str(sku_input or "").strip())
    if parsed_in and parsed_in.get("warehouse_unit"):
        return str(parsed_in["warehouse_unit"]).strip()
    for wh in wh_svc.list_warehouse_variants_for_base_sku(db, base_sku, active_only=False):
        parsed = wh_svc.parse_warehouse_product_id(getattr(wh, "product_id", None))
        if parsed and parsed.get("warehouse_unit"):
            return str(parsed["warehouse_unit"]).strip()
    return None


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

    if parent is None and not wh_rows:
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
        "parent": (
            {
                "id": parent.id,
                "product_id": parent.product_id,
                "name": parent.name,
                "price": float(parent.price or 0),
                "slug": parent.slug,
            }
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
            str(parsed_in.get("warehouse_color") or "").strip().lower() or None
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


def intake_return_to_warehouse(
    db: Session,
    *,
    base_sku: str,
    color: Optional[str],
    size: str,
    quantity: int,
    color_index: Optional[int] = None,
    color_image: Optional[str] = None,
    warehouse_product_id: Optional[str] = None,
    admin_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Cộng tồn (hoặc tạo mới) dòng kho thanh lý — gắn SP gốc nếu có.
    Nếu có mã kho đầy đủ (H9441/1/xl): lưu đúng mã đó; màu/size UI chỉ cho ảnh web.
    """
    raw_wh = staff_warehouse_product_id(warehouse_product_id or base_sku) or ""
    base = resolve_base_sku_from_input(raw_wh or base_sku)
    if not base:
        raise ValueError("Thiếu mã SKU gốc.")
    qty = max(1, int(quantity or 1))

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
        color_name: Optional[str] = None
        if color_key and color_key != "__default__":
            color_name = color_key
        size_s = str(size or "").strip()
        if not size_s:
            raise ValueError("Chọn size trước khi nhập kho.")
        unit_suffix = _default_unit_suffix(db, base, base_sku)
        existing = _find_existing_variant(
            db, base, color=color_name, size=size_s, unit=unit_suffix
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
            "available_before": before,
            "available_after": int(existing.available or 0),
            "quantity_added": qty,
            "is_warehouse_clearance": True,
            "admin_id": admin_id,
        }

    template = _template_product_for_intake(db, base)
    if template is None:
        raise ValueError(
            f"Chưa có SP gốc hoặc dòng kho «{base}» — import sản phẩm gốc hoặc một dòng kho mẫu trước."
        )

    if raw_wh:
        product_id = raw_wh
        parsed = parsed_variant_from_warehouse_id(raw_wh)
        parsed["base_sku"] = base
    else:
        color_name = color_key if color_key and color_key != "__default__" else None
        size_s = str(size or "").strip()
        unit_suffix = _default_unit_suffix(db, base, base_sku)
        product_id = build_warehouse_product_id(
            base, color=color_name, size=size_s, unit=unit_suffix
        )
        parsed = {
            "base_sku": base,
            "warehouse_size": size_s,
            "warehouse_color": color_name,
        }
        if unit_suffix:
            parsed["warehouse_unit"] = unit_suffix

    product_data: Dict[str, Any] = {"product_id": product_id, "available": qty}
    parent = find_parent_for_return_intake(db, base)
    display_color_name: Optional[str] = None
    if parent is not None:
        wh_svc.merge_return_intake_from_parent(
            parent,
            product_data,
            parsed,
            color_name=display_color_name,
            color_index=color_index,
            color_image=color_image,
        )
        product_data["available"] = qty
        if raw_wh and parsed.get("warehouse_size"):
            product_data["sizes"] = [str(parsed["warehouse_size"])]
    elif getattr(template, "is_warehouse_clearance", False):
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
    else:
        wh_svc.merge_return_intake_from_parent(
            template,
            product_data,
            parsed,
            color_name=display_color_name,
            color_index=color_index,
            color_image=color_image,
        )
        product_data["available"] = qty

    from app.services.alicdn_urls import normalize_product_data_image_urls_for_db

    link_parent = parent
    if link_parent is not None:
        wh_svc.attach_warehouse_row_to_parent(product_data, link_parent)
    product_data["slug"] = generate_consistent_slug(
        product_data.get("name") or getattr(template, "name", "") or base,
        product_id,
    )

    normalize_product_data_image_urls_for_db(product_data)

    row = Product(**product_data)
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "action": "created",
        "product_id": row.product_id,
        "available_before": 0,
        "available_after": int(row.available or 0),
        "quantity_added": qty,
        "is_warehouse_clearance": True,
        "admin_id": admin_id,
    }
