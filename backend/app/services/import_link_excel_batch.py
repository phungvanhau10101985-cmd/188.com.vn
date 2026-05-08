"""
Đọc file Excel danh sách link: URL mặc định cột F (dòng 2+), thông tin shop/giá nhận từ tiêu đề (G–K…) và từ khối cố định **L–O** → xuất vào cột **H–K** của file kết quả.

`shop_id` (cột I trên file import sản phẩm đầy đủ) lấy cùng giá trị ô với **Style** (cột AI / tiêu đề «Style» | «Kiểu dáng») khi ô đó có dữ liệu — áp sau shop_id ô riêng và khối L–O.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openpyxl import load_workbook

_ws_re = re.compile(r"\s+")

DEFAULT_LINK_COLUMN_1BASED = 6  # F
_FALLBACK_LINK_COLUMN = 3  # C «Link sp»
# Template 37 cột (A–AK): Style = cột AI (35) — dùng khi sheet rộng nhưng không có dòng tiêu đề khớp
STYLE_COLUMN_1BASED_FALLBACK = 35
# Cột L–O (12–15) trên file nguồn → cột H–K trên Excel kết quả (shop_name, shop_id, pro_lower_price, pro_high_price)
SOURCE_COL_BLOCK_LO_EXTRA_SHOP: Tuple[Tuple[int, str], ...] = (
    (12, "shop_name"),
    (13, "shop_id"),
    (14, "pro_lower_price"),
    (15, "pro_high_price"),
)
DATA_FIRST_ROW = 2
_MAX_ROWS = 500


def _norm_header(text: Any) -> str:
    if text is None:
        return ""
    s = unicodedata.normalize("NFKC", str(text)).strip().casefold()
    return _ws_re.sub(" ", s)


def _cell_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val).strip()


def _cell_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", ".").replace(" ", "").replace("\u00a0", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def merge_import_excel_overlay_into_product_data(
    product_data: Dict[str, Any],
    overlay: Optional[Dict[str, Any]],
) -> None:
    """Ghi đè shop + giá từ Excel (ưu tiên sau scrape). Khóa `_...` là meta (vd. _excel_row), không ảnh hưởng merge."""
    if not overlay or not isinstance(overlay, dict):
        return
    if (sn := overlay.get("shop_name")) is not None and str(sn).strip():
        product_data["shop_name"] = str(sn).strip()
    pl = overlay.get("pro_lower_price")
    if pl is not None and str(pl).strip() != "":
        product_data["pro_lower_price"] = _cell_str(pl)
    ph = overlay.get("pro_high_price")
    if ph is not None and str(ph).strip() != "":
        product_data["pro_high_price"] = _cell_str(ph)
    num = _cell_float(overlay.get("price"))
    if num is not None:
        product_data["price"] = num
    if (sid := overlay.get("shop_id")) is not None and str(sid).strip():
        product_data["shop_id"] = str(sid).strip()


def _hdr_col(header_cells: Tuple[Any, ...], *needles: str) -> Optional[int]:
    want = {_norm_header(n) for n in needles}
    for j, raw in enumerate(header_cells, start=1):
        if _norm_header(raw) in want:
            return j
    return None


def _gia_columns(header_cells: Tuple[Any, ...]) -> List[int]:
    out: List[int] = []
    for j, raw in enumerate(header_cells, start=1):
        if _norm_header(raw) == "gia":
            out.append(j)
    return out


def _labels_at(
    header_row1: Tuple[Any, ...], header_row2: Tuple[Any, ...], col_1based: int
) -> set[str]:
    """Ghép nhãn đã chuẩn hóa từ tối đa hai dòng tiêu đề (EN / VI) cho một cột."""
    out: set[str] = set()
    for row in (header_row1, header_row2):
        if 1 <= col_1based <= len(row):
            v = row[col_1based - 1]
            if v is not None and str(v).strip():
                out.add(_norm_header(v))
    return out


def _max_header_cols(header_row1: Tuple[Any, ...], header_row2: Tuple[Any, ...]) -> int:
    return max(len(header_row1), len(header_row2), 0)


def _first_col_matching_labels(
    header_row1: Tuple[Any, ...],
    header_row2: Tuple[Any, ...],
    max_col: int,
    needles_normalized: frozenset[str],
) -> Optional[int]:
    for j in range(1, max_col + 1):
        if needles_normalized.intersection(_labels_at(header_row1, header_row2, j)):
            return j
    return None


def _resolve_overlay_columns(
    header_row1: Tuple[Any, ...], header_row2: Tuple[Any, ...]
) -> Tuple[
    Optional[int],
    Optional[int],
    Optional[int],
    Optional[int],
    Optional[int],
    Optional[int],
]:
    """
    shop / shop_id / pro_lower / pro_high / price / style — hỗ trợ 1 hoặc 2 dòng tiêu đề:
    - Row1: shop_name, price, pro_lower_price, …
    - Row2: Tên shop, Giá, Sp giá thấp hơn, …
    Cột Style dùng để đồng bộ giá trị shop_id (file mẫu: cột AI).
    """
    mc = max(1, _max_header_cols(header_row1, header_row2))

    shop_needles = frozenset(
        _norm_header(x) for x in ("Shop name", "shop_name", "Tên shop", "Ten shop")
    )
    lower_needles = frozenset(
        _norm_header(x)
        for x in (
            "Giá thấp hơn",
            "pro_lower_price",
            "SP giá thấp hơn",
            "Sp giá thấp hơn",
            "sp giá thấp hơn",
        )
    )
    upper_needles = frozenset(
        _norm_header(x)
        for x in (
            "Giá cao hơn",
            "pro_high_price",
            "SP giá cao hơn",
            "Sp giá cao hơn",
            "sp giá cao hơn",
        )
    )

    shop_col = _first_col_matching_labels(header_row1, header_row2, mc, shop_needles)
    shop_id_needles = frozenset(
        _norm_header(x) for x in ("shop_id", "Shop id", "shop id")
    )
    shop_id_col = _first_col_matching_labels(header_row1, header_row2, mc, shop_id_needles)
    style_needles = frozenset(
        _norm_header(x) for x in ("Style", "style", "Kiểu dáng", "kiểu dáng")
    )
    style_col = _first_col_matching_labels(header_row1, header_row2, mc, style_needles)
    lower_col = _first_col_matching_labels(header_row1, header_row2, mc, lower_needles)
    upper_col = _first_col_matching_labels(header_row1, header_row2, mc, upper_needles)

    exclude_price = {c for c in (lower_col, upper_col) if c is not None}
    cols_price: List[int] = []
    cols_gia_hdr: List[int] = []
    for j in range(1, mc + 1):
        if j in exclude_price:
            continue
        lab = _labels_at(header_row1, header_row2, j)
        if "price" in lab:
            cols_price.append(j)
        # Một ô tiêu đề đích danh là «Giá»
        if lab == {"gia"}:
            cols_gia_hdr.append(j)

    price_col: Optional[int] = None
    if cols_price:
        price_col = min(cols_price)
    elif cols_gia_hdr:
        price_col = max(cols_gia_hdr)

    if shop_col is None:
        shop_col = _hdr_col(header_row1, "shop name", "Shop name") or _hdr_col(
            header_row2, "shop name", "Shop name", "Tên shop"
        )
    if shop_id_col is None:
        shop_id_col = _hdr_col(header_row1, "shop id", "Shop id") or _hdr_col(
            header_row2, "shop id", "Shop id"
        )
    if style_col is None:
        style_col = _hdr_col(header_row1, "Style", "style", "Kiểu dáng") or _hdr_col(
            header_row2, "Style", "style", "Kiểu dáng"
        )
    if lower_col is None:
        lower_col = _hdr_col(header_row1, "Giá thấp hơn", "SP giá thấp hơn", "Sp giá thấp hơn") or _hdr_col(
            header_row2, "Giá thấp hơn", "SP giá thấp hơn", "Sp giá thấp hơn"
        )
    if upper_col is None:
        upper_col = _hdr_col(header_row1, "Giá cao hơn", "SP giá cao hơn", "Sp giá cao hơn") or _hdr_col(
            header_row2, "Giá cao hơn", "SP giá cao hơn", "Sp giá cao hơn"
        )
    if price_col is None:
        g1 = _gia_columns(header_row1)
        g2 = _gia_columns(header_row2)
        merged = sorted({*g1, *g2} - exclude_price)
        price_col = max(merged) if merged else None

    return shop_col, shop_id_col, lower_col, upper_col, price_col, style_col


def parse_link_import_excel(path: str | Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Trả ([{excel_row, url, overlays}], skip_messages).

    overlays: shop_name, shop_id, pro_lower_price, pro_high_price, price (chỉ các trường có giá trị).
    shop_id lấy trùng ô **Style** (tiêu đề hoặc cột AI) nếu ô đó có dữ liệu.
    """
    p = Path(path)
    skip: List[str] = []
    out: List[Dict[str, Any]] = []

    wb = load_workbook(p, read_only=True, data_only=True)
    try:
        ws = wb.active
        rows_hdr = ws.iter_rows(min_row=1, max_row=2, values_only=True)
        rows_pair = list(rows_hdr)
        header = tuple(rows_pair[0]) if rows_pair else ()
        header2 = tuple(rows_pair[1] if len(rows_pair) > 1 else ())
        if not (
            any(x is not None and str(x).strip() for x in header)
            or any(x is not None and str(x).strip() for x in header2)
        ):
            return [], ["Dòng tiêu đề trống hoặc không đọc được."]

        shop_col, shop_id_col, lower_col, upper_col, price_col, style_col = _resolve_overlay_columns(
            header, header2
        )

        data_iter = ws.iter_rows(
            min_row=DATA_FIRST_ROW,
            max_row=DATA_FIRST_ROW + _MAX_ROWS,
            values_only=True,
        )
        for excel_row, row in enumerate(data_iter, start=DATA_FIRST_ROW):
            cells = tuple(row or ())
            if not any(v is not None and str(v).strip() != "" for v in cells):
                continue

            def coord(j: int) -> Optional[Any]:
                if j < 1 or j > len(cells):
                    return None
                return cells[j - 1]

            url = _cell_str(coord(DEFAULT_LINK_COLUMN_1BASED))
            if not url:
                url = _cell_str(coord(_FALLBACK_LINK_COLUMN))

            if not url.startswith(("http://", "https://")):
                skip.append(f"Dòng {excel_row}: bỏ qua (thiếu link hợp lệ).")
                continue

            overlays: Dict[str, Any] = {}
            if shop_col:
                sv = coord(shop_col)
                if sv is not None and str(sv).strip():
                    overlays["shop_name"] = _cell_str(sv)
            if shop_id_col:
                sid_v = coord(shop_id_col)
                if sid_v is not None and str(sid_v).strip():
                    overlays["shop_id"] = _cell_str(sid_v)
            if lower_col:
                lv = coord(lower_col)
                if lv is not None and str(lv).strip():
                    overlays["pro_lower_price"] = _cell_str(lv)
            if upper_col:
                hv = coord(upper_col)
                if hv is not None and str(hv).strip():
                    overlays["pro_high_price"] = _cell_str(hv)
            if price_col:
                pv = coord(price_col)
                if pv is not None and str(pv).strip() != "":
                    overlays["price"] = pv

            # Mẫu còn có cột «Giá» nhỏ ở G (trước cột đúng) — chỉ làm fallback khi chưa có price
            if "price" not in overlays:
                gv = coord(7)  # G
                if gv is not None and str(gv).strip() != "":
                    overlays["price"] = gv

            # Ghi đè / bổ sung từ khối L–O (ưu tiên khi có giá trị — khớp vị trí H–K file xuất)
            for col_1b, fld in SOURCE_COL_BLOCK_LO_EXTRA_SHOP:
                cell_v = coord(col_1b)
                if cell_v is None or str(cell_v).strip() == "":
                    continue
                overlays[fld] = _cell_str(cell_v)

            # shop_id trùng nguồn với cột Style (template A–AK: AI) khi có giá trị
            st_v: Optional[Any] = None
            if style_col:
                st_v = coord(style_col)
            if (st_v is None or str(st_v).strip() == "") and len(cells) >= STYLE_COLUMN_1BASED_FALLBACK:
                st_v = coord(STYLE_COLUMN_1BASED_FALLBACK)
            if st_v is not None and str(st_v).strip() != "":
                overlays["shop_id"] = _cell_str(st_v)

            out.append({"excel_row": excel_row, "url": url.strip(), "overlays": overlays})

    finally:
        wb.close()

    if not out and not skip:
        skip.append("Không có dòng dữ liệu có link sau dòng tiêu đề.")
    return out, skip
