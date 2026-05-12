"""
Đọc file Excel danh sách link: URL mặc định cột F (dòng 2+), **cột D** «Tên shop» → `shop_name_chinese`, **cột K** «Tên tiếng trung» → `chinese_name`; shop/giá phụ từ tiêu đề + khối **L–O** → xuất **H–K** file kết quả.
**Cột B** («Mã sp»): nếu có giá trị thì dùng làm SKU nội bộ ([A-Z][0-9]{4]) **chỉ khi mã đã nằm trong danh sách đã xuất**
(`internal_sku_exports`, từ bước tải SKU trống trong Admin) và chưa trùng `products.code`; ô trống → backend gán mã **đã xuất** đầu tiên còn chưa gán sản phẩm (FIFO).

**Giá đặt hàng (`price`):** **cột Q (17)** nếu có giá trị. **Cột G (7):** giá VND (~tham khảo) ghép vào `product_info.market_info.price_vnd` — không dùng cho `price` — để tab AK hiển thị VND thay vì chỉ chú thích trang nguồn/₮.

`shop_id` (cột I file đầy đủ) đồng bộ với **Style** (cột AI) khi có dữ liệu — áp sau shop_id ô riêng và khối L–O.
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
# Cột B: «Mã sp» — nếu có giá trị thì dùng làm SKU nội bộ (format [A-Z][0-9]{4}); không thì backend tự sinh.
OPTIONAL_INTERNAL_SKU_COLUMN_B_1BASED = 2
# Template 37 cột (A–AK): Style = cột AI (35) — dùng khi sheet rộng nhưng không có dòng tiêu đề khớp
STYLE_COLUMN_1BASED_FALLBACK = 35
# Giá bán (`price`): chỉ cột Q (17). Không bao giờ lấy cột G (7).
PRICE_SKIP_COLUMN_G_1BASED = 7
PRICE_EXCEL_COLUMN_Q_1BASED = 17
# Cột D / K cố định (template thường gặp): tên shop Trung Quốc, tên sản phẩm tiếng Trung — không gán `shop_name` từ ô D.
CHINESE_SHOP_COLUMN_D_1BASED = 4
CHINESE_PRODUCT_NAME_COLUMN_K_1BASED = 11
# Cột L–O (12–15) trên file nguồn → cột H–K trên Excel kết quả (shop_name, shop_id, pro_lower_price, pro_high_price)
SOURCE_COL_BLOCK_LO_EXTRA_SHOP: Tuple[Tuple[int, str], ...] = (
    (12, "shop_name"),
    (13, "shop_id"),
    (14, "pro_lower_price"),
    (15, "pro_high_price"),
)
DATA_FIRST_ROW = 2
_MAX_ROWS = 500
# openpyxl read_only có thể trả tuple hàng ngắn hơn `max_column` nội bộ → coord(17) thành None, mất giá Q.
# Luôn đọc tối thiểu tới đây (≥ Q=17, đủ template A–AK).
MAX_IMPORT_COL_1BASED = 40


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


_VND_CELL_NOISE_RE = re.compile(
    r"[\u00a0\s]|₫|\bVNĐ\b|\bvnd\b|đồng",
    re.IGNORECASE,
)


def _parse_vnd_amount_from_excel_cell(val: Any) -> Optional[float]:
    """Ô Excel cột G (VND): số Excel, hoặc chuỗi kiểu 1.500.000 / 79000 đ."""
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return float(val)
    if isinstance(val, float):
        return float(val)
    s = _VND_CELL_NOISE_RE.sub("", str(val).strip()).replace("\u2212", "-")
    # Ô dạng «79 000 đ» — bỏ ký hiệu đ/₫ sót cuối sau khi đã bỏ noise.
    s = re.sub(r"(?i)[\s]*(?:đ|vnđ|[₫])[\s]*$", "", s).strip()
    if not s:
        return None
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    comma_to_dot = s.replace(",", ".")
    dot_count = comma_to_dot.count(".")
    # Nhiều dấu . → phân hàng ngàn VI (vd. 1.500.000); một dấu . với nhóm cuối 3 chữ số → vd. "1.500"
    if dot_count >= 2:
        try:
            return float(comma_to_dot.replace(".", ""))
        except ValueError:
            return None
    if dot_count == 1:
        left, right = comma_to_dot.split(".", 1)
        if left.lstrip("-").isdigit() and right.isdigit() and len(right) == 3 and len(left.replace("-", "")) <= 3:
            try:
                return float(left.replace("-", "") + right) * (-1 if left.startswith("-") else 1)
            except ValueError:
                pass
    try:
        return float(comma_to_dot)
    except ValueError:
        return None


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
    """Ghi đè shop + giá + SKU (cột B) + tên TQ/shop TQ (cột D/K bulk) từ Excel. Khóa `_...` là meta, không merge."""
    if not overlay or not isinstance(overlay, dict):
        _fill_shop_id_from_style_if_empty(product_data)
        return
    co = overlay.get("code")
    if co is not None and str(co).strip():
        product_data["code"] = str(co).strip().upper()
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
    if (sk := overlay.get("_sync_style_kieu_dang")) is not None and str(sk).strip():
        product_data["style"] = str(sk).strip()
    if (cn := overlay.get("chinese_name")) is not None and str(cn).strip():
        product_data["chinese_name"] = str(cn).strip()
    if (sc := overlay.get("shop_name_chinese")) is not None and str(sc).strip():
        product_data["shop_name_chinese"] = str(sc).strip()
    vnd_raw = overlay.get("price_display_vnd_g")
    if vnd_raw is not None and str(vnd_raw).strip() != "":
        _merge_excel_column_g_vnd_into_product_info(product_data, vnd_raw)
    _fill_shop_id_from_style_if_empty(product_data)


def _merge_excel_column_g_vnd_into_product_info(product_data: Dict[str, Any], raw: Any) -> None:
    """Gép giá VND (cột G file bulk) vào product_info.market_info; bỏ note kiểu trang nguồn / ₮."""
    pi_any = product_data.get("product_info")
    pi: Dict[str, Any]
    if isinstance(pi_any, dict):
        pi = pi_any
    else:
        pi = {}
        product_data["product_info"] = pi
    mk_any = pi.get("market_info")
    mk: Dict[str, Any] = mk_any if isinstance(mk_any, dict) else {}

    parsed = _parse_vnd_amount_from_excel_cell(raw)
    if parsed is not None:
        vn = round(parsed, 2)
        if abs(vn - round(vn)) < 1e-6:
            mk["price_vnd"] = int(round(vn))
        else:
            mk["price_vnd"] = vn
        mk.pop("price_vnd_display", None)
    else:
        s = _cell_str(raw)
        if not s:
            return
        mk["price_vnd_display"] = s
        mk.pop("price_vnd", None)

    mk.pop(
        "note", None
    )  # vd. «Giá hiển thị theo trang nguồn (đơn vị có thể là ₮).»
    mk["excel_price_vnd_source"] = "Cột G (nhập Excel hàng loạt)"
    pi["market_info"] = mk


def _fill_shop_id_from_style_if_empty(product_data: Dict[str, Any]) -> None:
    """Khi không có shop_id (hoặc rỗng) sau overlay, dùng style từ scrape/taxonomy."""
    cur = str(product_data.get("shop_id") or "").strip()
    if cur:
        return
    sty = product_data.get("style")
    if isinstance(sty, str) and sty.strip():
        product_data["shop_id"] = sty.strip()


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
        if j == PRICE_SKIP_COLUMN_G_1BASED:
            continue
        lab = _labels_at(header_row1, header_row2, j)
        if "price" in lab:
            cols_price.append(j)
        # Một ô tiêu đề đích danh là «Giá»
        if lab == {"gia"}:
            cols_gia_hdr.append(j)

    price_col: Optional[int] = None
    if cols_price:
        # Nhiều cột "price": lấy cột phải nhất (thường Q), không lấy G (đã loại)
        price_col = max(cols_price)
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
        merged = sorted({*g1, *g2} - exclude_price - {PRICE_SKIP_COLUMN_G_1BASED})
        price_col = max(merged) if merged else None

    return shop_col, shop_id_col, lower_col, upper_col, price_col, style_col


def parse_link_import_excel(path: str | Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Trả ([{excel_row, url, overlays}], skip_messages).

    overlays: **code** (cột **B** «Mã sp» nếu có), shop_name (không lấy từ cột D), shop_name_chinese (**cột D**),
    chinese_name (**cột K**), shop_id, pro_lower_price, pro_high_price,
    **price_display_vnd_g** (**cột G** — đổ vào `product_info.market_info` làm giá VND),
    và **price** (chỉ khi ô **cột Q** có giá trị).
    shop_id lấy trùng ô **Style** (tiêu đề hoặc cột AI) nếu ô đó có dữ liệu.
    """
    p = Path(path)
    skip: List[str] = []
    out: List[Dict[str, Any]] = []

    wb = load_workbook(p, read_only=True, data_only=True)
    try:
        ws = wb.active
        rows_hdr = ws.iter_rows(
            min_row=1,
            max_row=2,
            min_col=1,
            max_col=MAX_IMPORT_COL_1BASED,
            values_only=True,
        )
        rows_pair = list(rows_hdr)
        header = tuple(rows_pair[0]) if rows_pair else ()
        header2 = tuple(rows_pair[1] if len(rows_pair) > 1 else ())
        if not (
            any(x is not None and str(x).strip() for x in header)
            or any(x is not None and str(x).strip() for x in header2)
        ):
            return [], ["Dòng tiêu đề trống hoặc không đọc được."]

        shop_col, shop_id_col, lower_col, upper_col, _, style_col = _resolve_overlay_columns(
            header, header2
        )

        data_iter = ws.iter_rows(
            min_row=DATA_FIRST_ROW,
            max_row=DATA_FIRST_ROW + _MAX_ROWS,
            min_col=1,
            max_col=MAX_IMPORT_COL_1BASED,
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
            sku_b = _cell_str(coord(OPTIONAL_INTERNAL_SKU_COLUMN_B_1BASED))
            if sku_b:
                overlays["code"] = sku_b.upper()
            if shop_col:
                sv = coord(shop_col)
                if sv is not None and str(sv).strip():
                    # D«Tên shop» = tên shop Trung Quốc (`shop_name_chinese`), không đồng thời là shop_name VN.
                    if shop_col != CHINESE_SHOP_COLUMN_D_1BASED:
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
                sv = _cell_str(st_v)
                overlays["shop_id"] = sv
                # Ghi vào product_data.style khi merge overlay (cột Kiểu dáng Excel = shop_id)
                overlays["_sync_style_kieu_dang"] = sv

            # Giá đặt (`price`): chỉ cột Q (ghi đè sau cùng). Cột G: VND vào AK `market_info` (không dùng cho `price`).
            q_price = coord(PRICE_EXCEL_COLUMN_Q_1BASED)
            if q_price is not None and str(q_price).strip() != "":
                overlays["price"] = q_price
            g_vnd = coord(PRICE_SKIP_COLUMN_G_1BASED)
            if g_vnd is not None and str(g_vnd).strip() != "":
                overlays["price_display_vnd_g"] = g_vnd

            # Cố định: D = Shop Trung Quốc, K = Tên tiếng Trung (khớp template cột chữ cái)
            d_cn_shop = coord(CHINESE_SHOP_COLUMN_D_1BASED)
            if d_cn_shop is not None and str(d_cn_shop).strip():
                overlays["shop_name_chinese"] = _cell_str(d_cn_shop)
            k_cn_name = coord(CHINESE_PRODUCT_NAME_COLUMN_K_1BASED)
            if k_cn_name is not None and str(k_cn_name).strip():
                overlays["chinese_name"] = _cell_str(k_cn_name)

            out.append({"excel_row": excel_row, "url": url.strip(), "overlays": overlays})

    finally:
        wb.close()

    if not out and not skip:
        skip.append("Không có dòng dữ liệu có link sau dòng tiêu đề.")
    return out, skip
