"""
Thu gọn JSON cột AK (`product_info`) cho hiển thị tab «Thông tin sản phẩm» trên web.

Loại dữ liệu thô scrape (Mông Cổ, pairs, swatches, slug nội bộ…) — giữ bản tóm tắt tiếng Việt
đã merge (specifications / variants colors+sizes / danh mục).
"""
from __future__ import annotations

import copy
from typing import Any, Dict


_INNER_WEB_KEYS = frozenset(
    {
        "sku",
        "name",
        "brand",
        "origin",
        "category",
        "target_audience_suggestion_vi",
        "name_vi",
        "display_name_vi",
        "material_vi",
    }
)

_SPEC_WEB_KEYS = frozenset(
    {
        "upper_material",
        "lining_material",
        "outsole_material",
        "style",
        "occasion",
        "heel_height",
        "thong_so_kich_thuoc_vi",
        "weight_note_vi",
        "weight_grams",
    }
)


def _truthy(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, str):
        return bool(val.strip())
    if isinstance(val, dict):
        return bool(val)
    if isinstance(val, (list, tuple, set)):
        return len(val) > 0
    return True


def _should_compact_hibox_style_product_info(pi: Dict[str, Any]) -> bool:
    """Nhận diện bản scrape catalog liệt kê ₮ — không phụ thuộc nhãn tên miền trong JSON."""
    inner_chk = pi.get("product_info")
    if isinstance(inner_chk, dict):
        if str(inner_chk.get("source") or "").lower() == "hibox":
            return True
    var_chk = pi.get("variants")
    if isinstance(var_chk, dict):
        if str(var_chk.get("source") or "").lower() == "hibox":
            return True
    mk = pi.get("market_info")
    if isinstance(mk, dict):
        if str(mk.get("currency") or "").strip().upper() == "MNT":
            return True
        # Listing Hibox sau khi quy ₮→VNĐ vẫn lưu footprint giá nguồn Hibox (draft đời cũ có thể thiếu variants.source).
        if mk.get("hibox_display_mnt_integer") is not None:
            return True
        if mk.get("hibox_mnt_per_cny_used") is not None:
            return True
    return False


def compact_product_info_for_web(product_data: Dict[str, Any]) -> None:
    """
    Mutate `product_data['product_info']` thành cấu trúc gọn cho PDP.

    Chỉ áp dụng khi payload nhận diện là import Hibox/listing (`_should_compact_hibox_style_product_info`),
    để không làm mất cấu trúc cột AK do Excel nhập tay.

    Không giữ `supplier_specs_excerpt` / `hibox_specs_excerpt`, `import_taxonomy_meta`,
    `pairs`, `color_swatches`, …; `market_info.note` không đưa ra web (ghi chú máy scrape).
    """
    pi = product_data.get("product_info")
    if not isinstance(pi, dict):
        return

    if not _should_compact_hibox_style_product_info(pi):
        return

    slim_inner: Dict[str, Any] = {}
    inner_src = pi.get("product_info")
    if isinstance(inner_src, dict):
        for k in _INNER_WEB_KEYS:
            if k not in inner_src:
                continue
            v = inner_src[k]
            if not _truthy(v):
                continue
            if k == "category" and isinstance(v, dict):
                if not any((vv is not None and str(vv).strip()) for vv in v.values()):
                    continue
            slim_inner[k] = copy.deepcopy(v)

    slim_spec: Dict[str, Any] = {}
    spec_src = pi.get("specifications")
    if isinstance(spec_src, dict):
        for k in _SPEC_WEB_KEYS:
            if k not in spec_src:
                continue
            v = spec_src[k]
            if not _truthy(v):
                continue
            slim_spec[k] = copy.deepcopy(v)

    slim_var: Dict[str, Any] = {}
    var_src = pi.get("variants")
    if isinstance(var_src, dict):
        for k in ("colors", "sizes"):
            if k not in var_src:
                continue
            v = var_src[k]
            if not _truthy(v):
                continue
            slim_var[k] = copy.deepcopy(v)

    slim_mk: Dict[str, Any] = {}
    mk = pi.get("market_info")
    if isinstance(mk, dict):
        if mk.get("stock") is not None:
            slim_mk["stock"] = mk["stock"]
        cur = (mk.get("currency") or "").strip()
        if cur:
            slim_mk["currency"] = cur
        for ek in ("price_vnd", "price_vnd_display", "excel_price_vnd_source"):
            if ek not in mk:
                continue
            ev = mk[ek]
            if ev is None or (isinstance(ev, str) and not ev.strip()):
                continue
            slim_mk[ek] = copy.deepcopy(ev)

    new_pi: Dict[str, Any] = {}
    if slim_inner:
        new_pi["product_info"] = slim_inner
    if slim_spec:
        new_pi["specifications"] = slim_spec
    if slim_var:
        new_pi["variants"] = slim_var
    if slim_mk:
        new_pi["market_info"] = slim_mk

    ta = pi.get("target_audience")
    if isinstance(ta, dict) and ta:
        new_pi["target_audience"] = copy.deepcopy(ta)

    product_data["product_info"] = new_pi if new_pi else {}
