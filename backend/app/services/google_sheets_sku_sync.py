"""
Đồng bộ Google Sheet theo **web/DB** (chuẩn). Có thể **hai** spreadsheet/tab (primary + `_2`),
từng bảng có `ROW_MODE`: **full** (khóa + link + shop + giá + stamp) hoặc **key_time** (chỉ khóa A + thời điểm B).

1. Đọc sheet (cột A… theo cấu hình; nếu có cột E — thời điểm đồng bộ UTC) một lần.
   Cột A có thể là mã SKU (`code`), `product_id` đầy đủ, hoặc phần `product_id` trước «a188» (`web_prefix`).
2. So với toàn bộ sản phẩm trong DB — chỉ **batchUpdate** những hàng có ô lệch; hàng trùng dữ liệu bỏ qua.
3. Chỉ **append** hàng mới cho mã chưa có trên sheet; mã orphan / trùng cột A → **xóa nội dung**
   các cột đồng bộ (A–B khi key_time, A–E khi full) — **không xóa cả hàng**, cột C+ giữ nguyên.

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.product import split_product_id_web_prefix_and_internal_sku
from app.models.product import Product

logger = logging.getLogger(__name__)

_SYNC_LOCK = threading.Lock()

SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)

# Cache đọc cột A (SKU sheet) khi cấp mã nội bộ — tránh gọi API mỗi lần thử một mã.
_SHEET_INTERNAL_SKU_CACHE: Tuple[float, frozenset[str]] | None = None
_SHEET_INTERNAL_SKU_CACHE_TTL_SEC = 60.0


def _spread_gid_for_internal_sku_lookup() -> Tuple[str, int]:
    """
    Sheet nào có cột A = mã SKU nội bộ (`code`) — dùng đọc trùng mã khi cấp SKU.
    Ưu tiên target có GOOGLE_SHEETS_SKU_SYNC_FIELD=code, sau đó target _2 nếu field_2=code;
    fallback sheet primary (legacy).
    """
    f1 = getattr(settings, "GOOGLE_SHEETS_SKU_SYNC_FIELD", "code") or "code"
    spread1 = (getattr(settings, "GOOGLE_SHEETS_SKU_SPREADSHEET_ID", "") or "").strip()
    gid1 = int(getattr(settings, "GOOGLE_SHEETS_SKU_SHEET_GID", 0) or 0)
    if f1 == "code" and spread1 and gid1 > 0:
        return spread1, gid1

    spread2 = (getattr(settings, "GOOGLE_SHEETS_SKU_SPREADSHEET_ID_2", "") or "").strip()
    gid2 = int(getattr(settings, "GOOGLE_SHEETS_SKU_SHEET_GID_2", 0) or 0)
    f2 = getattr(settings, "GOOGLE_SHEETS_SKU_SYNC_FIELD_2", "code") or "code"
    if f2 == "code" and spread2 and gid2 > 0:
        return spread2, gid2

    if spread1 and gid1 > 0:
        return spread1, gid1
    return "", 0


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

    spread, gid = _spread_gid_for_internal_sku_lookup()
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


def _sheet_primary_key_from_product(p: Product, field: str) -> str:
    """Giá trị cột A / khóa khớp sheet — trùng với `_row_values_from_product` ô đầu hàng."""
    if field == "product_id":
        return (p.product_id or "").strip()
    if field == "web_prefix":
        seg = split_product_id_web_prefix_and_internal_sku(p.product_id)
        if seg:
            return (seg.get("prefix") or "").strip()
        return (p.product_id or "").strip()
    return (p.code or "").strip()


def _fetch_products_by_key(db: Session, field: str) -> Dict[str, Product]:
    m: Dict[str, Product] = {}
    for p in db.query(Product).all():
        k = _sheet_primary_key_from_product(p, field)
        if not k:
            continue
        if k not in m:
            m[k] = p
    return m


def _sync_stamp_utc_str() -> str:
    """Chuỗi thời điểm đồng bộ phiên (UTC) — cột E khi full 5 cột, hoặc cột B khi ROW_MODE=key_time."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _row_values_from_product(
    p: Product,
    key_field: str,
    n_cols: int,
    *,
    written_at: str = "",
    row_mode: str = "full",
) -> List[str]:
    key = _sheet_primary_key_from_product(p, key_field)
    if row_mode == "key_time":
        return [key, (written_at or "").strip()]

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
    if n_cols >= 5:
        row.append((written_at or "").strip())
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
    """So sánh ô sheet với giá trị chuẩn từ DB (web). Cột giá luôn là cột D (index 3) khi n_cols>=4."""
    s = (sheet_val or "").strip()
    d = (db_val or "").strip()
    if n_cols >= 4 and col_index == 3:
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
    # Cột E trở đi (timestamp / đệm) không dùng để quyết định skip batchUpdate — chỉ so A–D khi có thêm cột.
    compare_cols = min(n_cols, 4) if n_cols >= 5 else n_cols
    for i in range(compare_cols):
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


def _clear_sync_columns(
    service: Any,
    spreadsheet_id: str,
    title_esc: str,
    human_rows: List[int],
    last_col: str,
    n_cols: int,
) -> None:
    """Xóa nội dung cột đồng bộ (A..last_col) — không xóa hàng, không đụng cột sau last_col."""
    if not human_rows:
        return
    empty_row = [[""] * n_cols]
    data_chunks: List[Dict[str, Any]] = []
    for r in sorted(set(human_rows)):
        data_chunks.append({"range": f"{title_esc}!A{r}:{last_col}{r}", "values": empty_row})
    _values_batch_update(service, spreadsheet_id, data_chunks)


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


def _build_sheet_sync_targets() -> List[Tuple[str, int, str, str]]:
    """Danh sách (spreadsheet_id, sheet_gid, sync_field, row_mode); bỏ trùng (spread, gid)."""
    targets: List[Tuple[str, int, str, str]] = []
    seen: Set[Tuple[str, int]] = set()

    def push(spread_raw: str, gid_raw: int, field_raw: str, row_mode_raw: str) -> None:
        spread = (spread_raw or "").strip()
        gid = int(gid_raw or 0)
        field = (field_raw or "code").strip()
        row_mode = (row_mode_raw or "full").strip().lower()
        if row_mode not in ("full", "key_time"):
            row_mode = "full"
        if not spread or gid <= 0:
            return
        key = (spread, gid)
        if key in seen:
            return
        seen.add(key)
        targets.append((spread, gid, field, row_mode))

    push(
        getattr(settings, "GOOGLE_SHEETS_SKU_SPREADSHEET_ID", "") or "",
        int(getattr(settings, "GOOGLE_SHEETS_SKU_SHEET_GID", 0) or 0),
        getattr(settings, "GOOGLE_SHEETS_SKU_SYNC_FIELD", "code") or "code",
        getattr(settings, "GOOGLE_SHEETS_SKU_SYNC_ROW_MODE", "full") or "full",
    )
    push(
        getattr(settings, "GOOGLE_SHEETS_SKU_SPREADSHEET_ID_2", "") or "",
        int(getattr(settings, "GOOGLE_SHEETS_SKU_SHEET_GID_2", 0) or 0),
        getattr(settings, "GOOGLE_SHEETS_SKU_SYNC_FIELD_2", "code") or "code",
        getattr(settings, "GOOGLE_SHEETS_SKU_SYNC_ROW_MODE_2", "full") or "full",
    )
    return targets


def _sync_single_google_sheet(
    db: Session,
    service: Any,
    spread: str,
    gid: int,
    field: str,
    header_rows: int,
    row_mode: str,
) -> Dict[str, Any]:
    """Đồng bộ một tab Sheet với DB (khóa cột A = field). Chỉ ghi/xóa cột đồng bộ (A–B key_time, A–E full); cột sau đó không đụng."""
    row_mode = (row_mode or "full").strip().lower()
    if row_mode not in ("full", "key_time"):
        row_mode = "full"
    n_cols = (
        2
        if row_mode == "key_time"
        else max(1, int(getattr(settings, "GOOGLE_SHEETS_SKU_COLUMN_COUNT", 5) or 5))
    )
    sync_written_at = (
        _sync_stamp_utc_str() if (row_mode == "key_time" or n_cols >= 5) else ""
    )

    title = _sheet_title_for_gid(service, spread, gid)
    t_esc = _escape_sheet_title(title)
    last_col = _column_letters_one_based(n_cols)

    products_by_key = _fetch_products_by_key(db, field)
    db_keys: Set[str] = set(products_by_key.keys())

    sku_to_rows = _parse_column_a(service, spread, title, header_rows)
    sheet_skus = set(sku_to_rows.keys())

    orphan_rows: List[int] = []
    for sku in sorted(sheet_skus - db_keys):
        orphan_rows.extend(sku_to_rows.get(sku, []))
    cleared_orphans = len(orphan_rows)
    if orphan_rows:
        _clear_sync_columns(service, spread, t_esc, orphan_rows, last_col, n_cols)
        sku_to_rows = _parse_column_a(service, spread, title, header_rows)

    dup_rows: List[int] = []
    for sku, rlist in sku_to_rows.items():
        if sku not in db_keys:
            continue
        if len(rlist) <= 1:
            continue
        sorted_r = sorted(rlist)
        dup_rows.extend(sorted_r[1:])
    cleared_dup = len(dup_rows)
    if dup_rows:
        _clear_sync_columns(service, spread, t_esc, dup_rows, last_col, n_cols)
        sku_to_rows = _parse_column_a(service, spread, title, header_rows)

    row_map = _read_data_rows_map(service, spread, title, header_rows, n_cols, last_col)
    update_data: List[Dict[str, Any]] = []
    updated = 0
    unchanged = 0
    for sku, prod in products_by_key.items():
        rlist = sku_to_rows.get(sku)
        if not rlist:
            continue
        r = rlist[0]
        new_vals = _row_values_from_product(
            prod, field, n_cols, written_at=sync_written_at, row_mode=row_mode
        )
        old_vals = row_map.get(r)
        if old_vals is None:
            old_vals = [""] * n_cols
        if row_mode != "key_time" and _row_matches_db(old_vals, new_vals, n_cols):
            unchanged += 1
            continue
        rng = f"{t_esc}!A{r}:{last_col}{r}"
        update_data.append({"range": rng, "values": [new_vals]})
        updated += 1

    if update_data:
        _values_batch_update(service, spread, update_data)

    current_sheet = set(_parse_column_a(service, spread, title, header_rows).keys())
    to_add = sorted(db_keys - current_sheet)
    added = 0
    if to_add:
        body_vals = [
            _row_values_from_product(
                products_by_key[s], field, n_cols, written_at=sync_written_at, row_mode=row_mode
            )
            for s in to_add
        ]
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
        "[SKU_SHEET_SYNC] spread=%s… field=%s row_mode=%s tab=%s cols=%s updated=%s unchanged=%s added=%s "
        "cleared_orphans=%s cleared_dup=%s db=%s",
        spread[:8],
        field,
        row_mode,
        title,
        n_cols,
        updated,
        unchanged,
        added,
        cleared_orphans,
        cleared_dup,
        len(db_keys),
    )

    return {
        "ok": True,
        "spreadsheet_id": spread,
        "sheet_gid": gid,
        "field": field,
        "row_mode": row_mode,
        "sheet_title": title,
        "column_count": n_cols,
        "updated_rows": updated,
        "unchanged_rows": unchanged,
        "added_rows": added,
        "cleared_orphan_rows": cleared_orphans,
        "cleared_duplicate_rows": cleared_dup,
        # Giữ tên cũ để API/admin không vỡ — cùng số hàng, chỉ xóa A..sync thay vì xóa hàng.
        "removed_orphan_rows": cleared_orphans,
        "removed_duplicate_rows": cleared_dup,
        "db_key_count": len(db_keys),
    }


def sync_product_skus_to_google_sheet(db: Session) -> Dict[str, Any]:
    """
    DB/web là chuẩn: một hoặc hai bảng Sheet (GOOGLE_SHEETS_SKU_* và tuỳ chọn *_2).

    - Mã không còn trong DB → xóa nội dung cột đồng bộ (A–B / A–E), giữ hàng và cột khác.
    - Trùng mã (cột A) → giữ một hàng, gỡ A–sync ở hàng trùng.
    - Mã có ở cả hai: đối chiếu với DB (full: A–D; key_time: luôn làm mới cột B thời gian).
    - Mã mới trong DB → append.

    GOOGLE_SHEETS_SKU_SYNC_ROW_MODE=key_time → chỉ ghi cột A (khóa) + B (thời điểm UTC); full → A–E theo COLUMN_COUNT.
    """
    if not getattr(settings, "GOOGLE_SHEETS_SKU_SYNC_ENABLED", False):
        return {"ok": True, "skipped": True, "reason": "disabled"}

    targets = _build_sheet_sync_targets()
    if not targets:
        return {
            "ok": False,
            "error": "Thiếu GOOGLE_SHEETS_SKU_SPREADSHEET_ID/SHEET_GID (chưa cấu hình bảng phụ _2 thì vẫn cần primary).",
        }

    header_rows = int(getattr(settings, "GOOGLE_SHEETS_SKU_HEADER_ROWS", 1) or 0)

    with _SYNC_LOCK:
        try:
            service = _get_sheets_service()
            results: List[Dict[str, Any]] = []
            first_err: str | None = None
            for spread, gid, field, row_mode in targets:
                try:
                    one = _sync_single_google_sheet(
                        db, service, spread, gid, field, header_rows, row_mode
                    )
                    results.append(one)
                except Exception as e:
                    logger.exception("[SKU_SHEET_SYNC] Lỗi đồng bộ spread=%s gid=%s: %s", spread, gid, e)
                    msg = str(e).strip() or e.__class__.__name__
                    first_err = first_err or msg
                    results.append(
                        {
                            "ok": False,
                            "spreadsheet_id": spread,
                            "sheet_gid": gid,
                            "field": field,
                            "row_mode": row_mode,
                            "error": msg,
                        }
                    )

            invalidate_internal_sku_sheet_cache()

            any_ok = any(r.get("ok") for r in results)
            all_ok = all(r.get("ok") for r in results)
            out: Dict[str, Any] = {
                "ok": all_ok,
                "partial": any_ok and not all_ok,
                "targets": results,
            }
            if first_err and not all_ok:
                out["error"] = first_err

            if results:
                # Thống kê top-level: lấy từ target thành công đầu tiên (target 1 lỗi / target 2 ok vẫn có số liệu).
                src = next((r for r in results if r.get("ok")), results[0])
                for k in (
                    "field",
                    "sheet_title",
                    "column_count",
                    "updated_rows",
                    "unchanged_rows",
                    "added_rows",
                    "removed_orphan_rows",
                    "removed_duplicate_rows",
                    "db_key_count",
                ):
                    if k in src and src.get("ok"):
                        out[k] = src[k]

            return out
        except Exception as e:
            logger.exception("[SKU_SHEET_SYNC] Lỗi đồng bộ: %s", e)
            msg = str(e).strip() or e.__class__.__name__
            return {"ok": False, "error": msg}
