"""
Đồng bộ Google Sheet theo **web/DB** (chuẩn). Luồng xử lý trước khi ghi (tiết kiệm quota API):

1. Đọc sheet (cột A… theo cấu hình) một lần.
2. So với toàn bộ sản phẩm trong DB — chỉ **batchUpdate** những hàng có ô lệch; hàng trùng dữ liệu bỏ qua.
3. Chỉ **append** hàng mới cho mã chưa có trên sheet; xóa hàng orphan / trùng mã ở lớp này.

Lịch gọi: CRUD lẻ được **debounce** (mặc định 45s) ở `crud/product.py`; import Excel
chạy đồng bộ **ngay** một lần; endpoint sync tay gọi trực tiếp không debounce.

Quy mô ~30k hàng: đọc sheet + so khớp DB vẫn chạy trong một phiên (có thể vài phút); xóa/append
đã chia lô để tránh một HTTP payload quá lớn. Cần **quota Google Sheets** đủ và client/proxy (Next)
**timeout đủ dài** — nếu đứt kết nối giữa chừng xem lại proxy/nginx `proxy_read_timeout`.

Xác thực: GOOGLE_SHEETS_SKU_CREDENTIALS_PATH → runtime/.../gcp-vision-service-account.json
→ GOOGLE_APPLICATION_CREDENTIALS → IMAGE_LOCALIZATION_GCP_KEY_FILE.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.product import Product

logger = logging.getLogger(__name__)

_SYNC_LOCK = threading.Lock()

SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)

# Cache đọc cột A (SKU sheet) khi cấp mã nội bộ — tránh gọi API mỗi lần thử một mã.
_SHEET_INTERNAL_SKU_CACHE: Tuple[float, frozenset[str]] | None = None
_SHEET_INTERNAL_SKU_CACHE_TTL_SEC = 60.0


def fetch_internal_sku_keys_from_sheet_cached() -> Set[str]:
    """
    Trả các ô cột A (sau header) khớp định dạng SKU nội bộ [A-Z][0-9]{4} (không *0000).
    Dùng để không cấp / không xuất trùng mã đã có trên sheet khách vận hành.

    Sheet tắt / lỗi API → set rỗng (không chặn toàn hệ thống).
    """
    global _SHEET_INTERNAL_SKU_CACHE
    now = time.monotonic()
    if _SHEET_INTERNAL_SKU_CACHE is not None:
        ts, frozen_s = _SHEET_INTERNAL_SKU_CACHE
        if now - ts < _SHEET_INTERNAL_SKU_CACHE_TTL_SEC:
            return set(frozen_s)

    out: Set[str] = set()
    if not getattr(settings, "GOOGLE_SHEETS_SKU_SYNC_ENABLED", False):
        _SHEET_INTERNAL_SKU_CACHE = (now, frozenset())
        return out

    spread = getattr(settings, "GOOGLE_SHEETS_SKU_SPREADSHEET_ID", "") or ""
    gid = int(getattr(settings, "GOOGLE_SHEETS_SKU_SHEET_GID", 0) or 0)
    if not spread or gid <= 0:
        _SHEET_INTERNAL_SKU_CACHE = (now, frozenset())
        return out

    header_rows = int(getattr(settings, "GOOGLE_SHEETS_SKU_HEADER_ROWS", 1) or 0)

    try:
        from app.services.product_internal_sku import internal_sku_is_valid_format

        service = _get_sheets_service()
        title = _sheet_title_for_gid(service, spread, gid)
        sku_to_rows = _parse_column_a(service, spread, title, header_rows)
        for key in sku_to_rows.keys():
            k = (key or "").strip().upper()
            if internal_sku_is_valid_format(k):
                out.add(k)
    except Exception:
        logger.warning("[SKU_SHEET_ALLOC] Không đọc được sheet để kiểm tra trùng SKU (bỏ qua chặn sheet).", exc_info=True)

    _SHEET_INTERNAL_SKU_CACHE = (now, frozenset(out))
    return out


def invalidate_internal_sku_sheet_cache() -> None:
    """Gọi sau khi ghi sheet để lần cấp SKU sau đọc lại cột A."""
    global _SHEET_INTERNAL_SKU_CACHE
    _SHEET_INTERNAL_SKU_CACHE = None


# Giới hạn thực tế Google API / kích thước HTTP — đồng bộ ~30k hàng vẫn ổn nếu chia lô.
_BATCH_UPDATE_MAX_SUBREQUESTS = 100
_APPEND_ROWS_PER_REQUEST = 2000


def _default_vision_service_account_path() -> Path:
    return Path(__file__).resolve().parents[2] / "runtime" / "image_localization" / "gcp-vision-service-account.json"


def _credentials_path() -> str:
    p = (getattr(settings, "GOOGLE_SHEETS_SKU_CREDENTIALS_PATH", None) or "").strip()
    if p:
        return p
    vision_default = _default_vision_service_account_path()
    if vision_default.is_file():
        return str(vision_default)
    p2 = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if p2:
        return p2
    return (getattr(settings, "IMAGE_LOCALIZATION_GCP_KEY_FILE", None) or "").strip()


def _escape_sheet_title(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


def _column_letters_one_based(index: int) -> str:
    """Cột 1-based: 1=A, 26=Z, 27=AA."""
    if index < 1:
        return "A"
    n = index
    parts: List[str] = []
    while n > 0:
        n, r = divmod(n - 1, 26)
        parts.append(chr(65 + r))
    return "".join(reversed(parts))


def _get_sheets_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    path = _credentials_path()
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(
            "Thiếu file JSON service account (GOOGLE_SHEETS_SKU_CREDENTIALS_PATH, "
            "GOOGLE_APPLICATION_CREDENTIALS hoặc IMAGE_LOCALIZATION_GCP_KEY_FILE)."
        )
    creds = service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _sheet_title_for_gid(service: Any, spreadsheet_id: str, sheet_gid: int) -> str:
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in meta.get("sheets", []):
        props = sheet.get("properties") or {}
        if props.get("sheetId") == sheet_gid:
            return props.get("title") or ""
    raise ValueError(f"Không tìm thấy tab sheetId={sheet_gid} trong spreadsheet.")


def _fetch_products_by_key(db: Session, field: str) -> Dict[str, Product]:
    m: Dict[str, Product] = {}
    for p in db.query(Product).all():
        if field == "product_id":
            k = (p.product_id or "").strip()
        else:
            k = (p.code or "").strip()
        if not k:
            continue
        if k not in m:
            m[k] = p
    return m


def _row_values_from_product(p: Product, key_field: str, n_cols: int) -> List[str]:
    if key_field == "product_id":
        key = (p.product_id or "").strip()
    else:
        key = (p.code or "").strip()
    row: List[str] = []
    row.append(key)
    if n_cols >= 2:
        row.append((p.link_default or "").strip())
    if n_cols >= 3:
        shop = (p.shop_name_chinese or p.shop_name or "").strip()
        row.append(shop)
    if n_cols >= 4:
        price = p.price
        if price is None:
            row.append("")
        elif isinstance(price, (int, float)) and float(price) == int(float(price)):
            row.append(str(int(float(price))))
        else:
            row.append(str(price))
    while len(row) < n_cols:
        row.append("")
    return row[:n_cols]


def _normalize_price_cell(s: str) -> str:
    raw = (s or "").strip().replace(",", "").replace(" ", "").replace("\u00a0", "")
    if not raw:
        return ""
    try:
        x = float(raw)
        if abs(x - int(x)) < 1e-9:
            return str(int(x))
        return str(x)
    except ValueError:
        return (s or "").strip()


def _cells_semantically_equal(
    sheet_val: str,
    db_val: str,
    col_index: int,
    n_cols: int,
) -> bool:
    """So sánh ô sheet với giá trị chuẩn từ DB (web). Cột giá (cột cuối khi n_cols>=4): so theo số."""
    s = (sheet_val or "").strip()
    d = (db_val or "").strip()
    if n_cols >= 4 and col_index == n_cols - 1:
        ps, pd = _normalize_price_cell(s), _normalize_price_cell(d)
        if ps == pd:
            return True
        try:
            if not ps and not pd:
                return True
            return abs(float(ps) - float(pd)) < 1e-6
        except ValueError:
            return (s or "").strip() == (d or "").strip()
    return s == d


def _row_matches_db(sheet_row: List[str], db_row: List[str], n_cols: int) -> bool:
    for i in range(n_cols):
        sv = sheet_row[i] if i < len(sheet_row) else ""
        dv = db_row[i] if i < len(db_row) else ""
        if not _cells_semantically_equal(str(sv), str(dv), i, n_cols):
            return False
    return True


def _read_data_rows_map(
    service: Any,
    spreadsheet_id: str,
    title: str,
    header_rows: int,
    n_cols: int,
    last_col_letter: str,
) -> Dict[int, List[str]]:
    """Mỗi số dòng 1-based -> giá trị A.. (độ dài n_cols)."""
    t = _escape_sheet_title(title)
    start_row = header_rows + 1
    rng = f"{t}!A{start_row}:{last_col_letter}1000000"
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=rng, majorDimension="ROWS")
        .execute()
    )
    values = result.get("values") or []
    out: Dict[int, List[str]] = {}
    for i, row in enumerate(values):
        rnum = start_row + i
        cells: List[str] = []
        for j in range(n_cols):
            if j < len(row) and row[j] is not None:
                cells.append(str(row[j]))
            else:
                cells.append("")
        out[rnum] = cells
    return out


def _parse_column_a(
    service: Any,
    spreadsheet_id: str,
    title: str,
    header_rows: int,
) -> Dict[str, List[int]]:
    t = _escape_sheet_title(title)
    start_row = header_rows + 1
    range_a1 = f"{t}!A{start_row}:A1000000"
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_a1, majorDimension="ROWS")
        .execute()
    )
    values = result.get("values") or []
    sku_to_rows: Dict[str, List[int]] = {}
    for i, row in enumerate(values):
        rnum = start_row + i
        cell = ""
        if row:
            cell = str(row[0]).strip()
        if not cell:
            continue
        sku_to_rows.setdefault(cell, []).append(rnum)
    return sku_to_rows


def _merge_row_blocks(sorted_desc: List[int]) -> List[Tuple[int, int]]:
    rows = sorted(set(sorted_desc), reverse=True)
    if not rows:
        return []
    blocks: List[Tuple[int, int]] = []
    i = 0
    while i < len(rows):
        hi = rows[i]
        lo = hi
        j = i + 1
        while j < len(rows) and rows[j] == lo - 1:
            lo = rows[j]
            j += 1
        blocks.append((lo, hi))
        i = j
    return blocks


def _delete_row_ranges(service: Any, spreadsheet_id: str, sheet_gid: int, human_rows: List[int]) -> None:
    if not human_rows:
        return
    blocks = _merge_row_blocks(human_rows)
    blocks.sort(key=lambda b: b[1], reverse=True)
    requests: List[Dict[str, Any]] = []
    for lo, hi in blocks:
        requests.append(
            {
                "deleteDimension": {
                    "range": {
                        "sheetId": sheet_gid,
                        "dimension": "ROWS",
                        "startIndex": lo - 1,
                        "endIndex": hi,
                    }
                }
            }
        )
    # Một batchUpdate quá nhiều deleteDimension → payload/timeout; chia lô.
    for i in range(0, len(requests), _BATCH_UPDATE_MAX_SUBREQUESTS):
        part = requests[i : i + _BATCH_UPDATE_MAX_SUBREQUESTS]
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": part}
        ).execute()


def _values_batch_update(
    service: Any,
    spreadsheet_id: str,
    data_chunks: List[Dict[str, Any]],
) -> None:
    """Google values.batchUpdate: gom range; chia nhóm tránh payload / quota (hàng chục nghìn ô cập nhật)."""
    chunk_size = 100
    for i in range(0, len(data_chunks), chunk_size):
        part = data_chunks[i : i + chunk_size]
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "USER_ENTERED",
                "data": part,
            },
        ).execute()


def sync_product_skus_to_google_sheet(db: Session) -> Dict[str, Any]:
    """
    DB/web là chuẩn: sheet phản ánh DB sau khi so khớp — chỉ ghi ô thay đổi.

    - Hàng không còn trong DB → xóa.
    - Trùng mã → giữ một hàng, xóa dư.
    - Mã có ở cả hai: đối chiếu từng ô với DB; khác mới batchUpdate.
    - Mã mới trong DB → append.

    Tần suất gọi: hạn chế ở lớp schedule (debounce CRUD); import Excel/sync tay gọi trực tiếp.
    """
    if not getattr(settings, "GOOGLE_SHEETS_SKU_SYNC_ENABLED", False):
        return {"ok": True, "skipped": True, "reason": "disabled"}

    spread = getattr(settings, "GOOGLE_SHEETS_SKU_SPREADSHEET_ID", "") or ""
    gid = int(getattr(settings, "GOOGLE_SHEETS_SKU_SHEET_GID", 0) or 0)
    if not spread or gid <= 0:
        return {
            "ok": False,
            "error": "Thiếu GOOGLE_SHEETS_SKU_SPREADSHEET_ID hoặc GOOGLE_SHEETS_SKU_SHEET_GID",
        }

    field = getattr(settings, "GOOGLE_SHEETS_SKU_SYNC_FIELD", "code") or "code"
    header_rows = int(getattr(settings, "GOOGLE_SHEETS_SKU_HEADER_ROWS", 1) or 0)
    n_cols = int(getattr(settings, "GOOGLE_SHEETS_SKU_COLUMN_COUNT", 4) or 4)
    n_cols = max(1, n_cols)

    with _SYNC_LOCK:
        try:
            service = _get_sheets_service()
            title = _sheet_title_for_gid(service, spread, gid)
            t_esc = _escape_sheet_title(title)
            last_col = _column_letters_one_based(n_cols)

            products_by_key = _fetch_products_by_key(db, field)
            db_keys: Set[str] = set(products_by_key.keys())

            sku_to_rows = _parse_column_a(service, spread, title, header_rows)
            sheet_skus = set(sku_to_rows.keys())

            # 1) Xóa hàng orphan (có trong sheet, không còn DB)
            orphan_rows: List[int] = []
            for sku in sorted(sheet_skus - db_keys):
                orphan_rows.extend(sku_to_rows.get(sku, []))
            removed_orphans = len(orphan_rows)
            if orphan_rows:
                _delete_row_ranges(service, spread, gid, orphan_rows)
                sku_to_rows = _parse_column_a(service, spread, title, header_rows)

            # 2) Xóa hàng trùng mã (giữ dòng đầu tiên theo thứ tự Excel)
            dup_rows: List[int] = []
            for sku, rlist in sku_to_rows.items():
                if sku not in db_keys:
                    continue
                if len(rlist) <= 1:
                    continue
                sorted_r = sorted(rlist)
                dup_rows.extend(sorted_r[1:])
            removed_dup = len(dup_rows)
            if dup_rows:
                _delete_row_ranges(service, spread, gid, dup_rows)
                sku_to_rows = _parse_column_a(service, spread, title, header_rows)

            # 3) Chỉ cập nhật hàng khi DB khác sheet (web chuẩn, tránh ghi không cần thiết)
            row_map = _read_data_rows_map(
                service, spread, title, header_rows, n_cols, last_col
            )
            update_data: List[Dict[str, Any]] = []
            updated = 0
            unchanged = 0
            for sku, prod in products_by_key.items():
                rlist = sku_to_rows.get(sku)
                if not rlist:
                    continue
                r = rlist[0]
                new_vals = _row_values_from_product(prod, field, n_cols)
                old_vals = row_map.get(r)
                if old_vals is None:
                    old_vals = [""] * n_cols
                if _row_matches_db(old_vals, new_vals, n_cols):
                    unchanged += 1
                    continue
                rng = f"{t_esc}!A{r}:{last_col}{r}"
                update_data.append({"range": rng, "values": [new_vals]})
                updated += 1

            if update_data:
                _values_batch_update(service, spread, update_data)

            # 4) Thêm hàng cho mã mới
            current_sheet = set(_parse_column_a(service, spread, title, header_rows).keys())
            to_add = sorted(db_keys - current_sheet)
            added = 0
            if to_add:
                body_vals = [_row_values_from_product(products_by_key[s], field, n_cols) for s in to_add]
                # Append một lần với ~30k hàng dễ timeout / vượt giới hạn xử lý — chia lô.
                for a in range(0, len(body_vals), _APPEND_ROWS_PER_REQUEST):
                    chunk = body_vals[a : a + _APPEND_ROWS_PER_REQUEST]
                    service.spreadsheets().values().append(
                        spreadsheetId=spread,
                        range=f"{t_esc}!A:{last_col}",
                        valueInputOption="USER_ENTERED",
                        insertDataOption="INSERT_ROWS",
                        body={"values": chunk},
                    ).execute()
                added = len(to_add)

            logger.info(
                "[SKU_SHEET_SYNC] field=%s tab=%s cols=%s updated=%s unchanged=%s added=%s "
                "removed_orphans=%s removed_dup=%s db=%s",
                field,
                title,
                n_cols,
                updated,
                unchanged,
                added,
                removed_orphans,
                removed_dup,
                len(db_keys),
            )
            invalidate_internal_sku_sheet_cache()
            return {
                "ok": True,
                "field": field,
                "sheet_title": title,
                "column_count": n_cols,
                "updated_rows": updated,
                "unchanged_rows": unchanged,
                "added_rows": added,
                "removed_orphan_rows": removed_orphans,
                "removed_duplicate_rows": removed_dup,
                "db_key_count": len(db_keys),
            }
        except Exception as e:
            logger.exception("[SKU_SHEET_SYNC] Lỗi đồng bộ: %s", e)
            msg = str(e).strip() or e.__class__.__name__
            return {"ok": False, "error": msg}
