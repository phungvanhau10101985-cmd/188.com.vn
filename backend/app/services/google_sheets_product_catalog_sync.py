"""
Đồng bộ **toàn bộ** dữ liệu sản phẩm (cùng 41 cột Excel export) lên Google Sheet catalog.

DB/web là chuẩn — mỗi lần chạy ghi đè tab:
- Sản phẩm mới trên web → có trên sheet
- Sản phẩm đã xóa khỏi DB → không còn trên sheet (xóa hàng thừa)
- Sản phẩm cập nhật → ô được ghi lại theo dữ liệu mới nhất

Lịch khuyến nghị: cron 3:30 sáng giờ Việt Nam (giờ thấp điểm).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.product import get_all_products_for_export
from app.services.excel_importer import (
    PRODUCT_EXCEL_EXPORT_COLUMNS,
    PRODUCT_EXCEL_VIETNAMESE_HEADERS,
)
from app.services.google_sheets_sku_sync import (
    _column_letters_one_based,
    _escape_sheet_title,
    _get_sheets_service,
    _sheet_title_for_gid,
)

logger = logging.getLogger(__name__)

_SYNC_LOCK = threading.Lock()

_HEADER_ROWS = 2
_ROWS_PER_REQUEST = 500


def _cell_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, bool):
        return "1" if val else "0"
    if isinstance(val, float) and val == int(val):
        return str(int(val))
    return str(val)


def _product_dict_to_row(product: Dict[str, Any], columns: List[str]) -> List[str]:
    row: List[str] = []
    for col in columns:
        row.append(_cell_str(product.get(col, "")))
    return row


def _build_sheet_matrix(products: List[Dict[str, Any]]) -> List[List[str]]:
    cols = PRODUCT_EXCEL_EXPORT_COLUMNS
    header_en = list(cols)
    header_vi = [PRODUCT_EXCEL_VIETNAMESE_HEADERS.get(c, c) for c in cols]
    data_rows = [_product_dict_to_row(p, cols) for p in products]
    return [header_en, header_vi, *data_rows]


def _ensure_sheet_grid_size(
    service: Any,
    spreadsheet_id: str,
    sheet_gid: int,
    *,
    min_rows: int,
    min_cols: int,
) -> int:
    """Mở rộng tab nếu grid hiện tại nhỏ hơn dữ liệu cần ghi. Trả rowCount sau khi đảm bảo."""
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_props = None
    for sheet in meta.get("sheets", []):
        props = sheet.get("properties") or {}
        if props.get("sheetId") == sheet_gid:
            sheet_props = props
            break
    if sheet_props is None:
        raise ValueError(f"Không tìm thấy tab sheetId={sheet_gid} trong spreadsheet.")

    grid = sheet_props.get("gridProperties") or {}
    cur_rows = int(grid.get("rowCount") or 0)
    cur_cols = int(grid.get("columnCount") or 0)
    need_rows = max(cur_rows, min_rows)
    need_cols = max(cur_cols, min_cols)
    if need_rows == cur_rows and need_cols == cur_cols:
        return need_rows

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet_gid,
                            "gridProperties": {
                                "rowCount": need_rows,
                                "columnCount": need_cols,
                            },
                        },
                        "fields": "gridProperties.rowCount,gridProperties.columnCount",
                    }
                }
            ]
        },
    ).execute()
    logger.info(
        "[PRODUCT_CATALOG_SHEET_SYNC] Mở rộng grid gid=%s: %sx%s → %sx%s",
        sheet_gid,
        cur_rows,
        cur_cols,
        need_rows,
        need_cols,
    )
    return need_rows


def _values_update_chunked(
    service: Any,
    spreadsheet_id: str,
    title_esc: str,
    matrix: List[List[str]],
    last_col: str,
) -> int:
    """Ghi matrix vào sheet từ A1; trả số hàng dữ liệu (không tính header)."""
    n_cols = len(PRODUCT_EXCEL_EXPORT_COLUMNS)
    written = 0
    for start in range(0, len(matrix), _ROWS_PER_REQUEST):
        chunk = matrix[start : start + _ROWS_PER_REQUEST]
        row_start = start + 1
        row_end = row_start + len(chunk) - 1
        rng = f"{title_esc}!A{row_start}:{last_col}{row_end}"
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=rng,
            valueInputOption="USER_ENTERED",
            body={"values": chunk},
        ).execute()
        written += len(chunk)
    return max(0, written - _HEADER_ROWS)


def _clear_trailing_rows(
    service: Any,
    spreadsheet_id: str,
    title_esc: str,
    last_col: str,
    *,
    keep_rows: int,
    grid_row_count: int,
) -> int:
    """Xóa nội dung các hàng sau keep_rows (1-based). Trả số hàng đã xóa."""
    start_clear = keep_rows + 1
    if start_clear > grid_row_count:
        return 0
    rng = f"{title_esc}!A{start_clear}:{last_col}{grid_row_count}"
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=rng, majorDimension="ROWS")
        .execute()
    )
    old_values = result.get("values") or []
    if not old_values:
        return 0
    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=rng,
        body={},
    ).execute()
    return len(old_values)


def sync_product_catalog_to_google_sheet(db: Session) -> Dict[str, Any]:
    """
    Ghi đè toàn bộ tab catalog với dữ liệu sản phẩm hiện có trong DB.
    """
    if not getattr(settings, "GOOGLE_SHEETS_PRODUCT_CATALOG_SYNC_ENABLED", False):
        return {"ok": True, "skipped": True, "reason": "disabled"}

    spread = (getattr(settings, "GOOGLE_SHEETS_PRODUCT_CATALOG_SPREADSHEET_ID", "") or "").strip()
    gid = int(getattr(settings, "GOOGLE_SHEETS_PRODUCT_CATALOG_SHEET_GID", 0) or 0)
    if not spread or gid <= 0:
        return {
            "ok": False,
            "error": "Thiếu GOOGLE_SHEETS_PRODUCT_CATALOG_SPREADSHEET_ID hoặc SHEET_GID.",
        }

    with _SYNC_LOCK:
        try:
            products = get_all_products_for_export(db)
            matrix = _build_sheet_matrix(products)
            n_cols = len(PRODUCT_EXCEL_EXPORT_COLUMNS)
            last_col = _column_letters_one_based(n_cols)

            service = _get_sheets_service()
            title = _sheet_title_for_gid(service, spread, gid)
            title_esc = _escape_sheet_title(title)
            total_rows_needed = _HEADER_ROWS + len(products)
            grid_rows = _ensure_sheet_grid_size(
                service,
                spread,
                gid,
                min_rows=total_rows_needed,
                min_cols=n_cols,
            )

            written_data_rows = _values_update_chunked(
                service, spread, title_esc, matrix, last_col
            )
            cleared_trailing = _clear_trailing_rows(
                service,
                spread,
                title_esc,
                last_col,
                keep_rows=_HEADER_ROWS + written_data_rows,
                grid_row_count=grid_rows,
            )

            synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            logger.info(
                "[PRODUCT_CATALOG_SHEET_SYNC] spread=%s… tab=%s rows=%s cleared_trailing=%s at=%s",
                spread[:8],
                title,
                written_data_rows,
                cleared_trailing,
                synced_at,
            )

            return {
                "ok": True,
                "spreadsheet_id": spread,
                "sheet_gid": gid,
                "sheet_title": title,
                "column_count": n_cols,
                "product_rows": written_data_rows,
                "cleared_trailing_rows": cleared_trailing,
                "synced_at": synced_at,
            }
        except Exception as e:
            logger.exception("[PRODUCT_CATALOG_SHEET_SYNC] Lỗi đồng bộ: %s", e)
            msg = str(e).strip() or e.__class__.__name__
            return {"ok": False, "error": msg}
