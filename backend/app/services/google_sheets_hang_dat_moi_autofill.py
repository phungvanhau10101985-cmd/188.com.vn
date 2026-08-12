"""
Autofill sheet «Hàng Đặt Mới»: khi cột Q (Mã đặt) khớp dạng SKU nội bộ
(C0156/, C0156/XL, C0156/XL/2) → ghi:
  S = tên sản phẩm,
  T = mã đơn hàng gần nhất (orders.order_code),
  U = giá, W = link TQ, AB = tên shop TQ.

Mã khác dạng → không đụng S/T/U/W/AB.
Worker nền poll cột Q (mặc định 2s); chỉ đọc/ghi hàng khi Q đổi hoặc lần đầu backfill.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.product import get_product_by_code
from app.models.order import Order, OrderItem
from app.models.product import Product

logger = logging.getLogger(__name__)

# C0156/ | C0156/XL | C0156/XL/2 | H9287/39/1 … (bắt buộc có dấu / sau mã gốc)
_ORDER_SKU_RE = re.compile(r"^([A-Za-z][0-9]{4})/.*$")

_COL_Q = "Q"  # Mã đặt
_COL_S = "S"  # Tên sản phẩm
_COL_T = "T"  # Mã đơn hàng (đơn gần nhất)
_COL_U = "U"  # GIÁ
_COL_W = "W"  # Link TQ
_COL_AB = "AB"  # TÊN TQ

_daemon_started = False
_daemon_lock = threading.Lock()
_run_lock = threading.Lock()

# Giá trị cột Q theo số hàng lần poll trước — chỉ overwrite khi Q đổi.
_last_q_by_row: Dict[int, str] = {}
_cached_title: Optional[str] = None
_cached_service: Any = None
_cached_service_at: float = 0.0
_SERVICE_TTL_SEC = 600.0


def parse_order_sku_base(raw: str) -> Optional[str]:
    """
    Trả mã gốc (vd C0156) nếu ô khớp dạng cho phép autofill; ngược lại None.
    Chấp nhận: C0156/, C0156/XL, C0156/XL/2 (bắt buộc có `/` sau 5 ký tự mã).
    Không chấp nhận chỉ C0156 (không có `/`).
    """
    s = (raw or "").strip()
    if not s:
        return None
    m = _ORDER_SKU_RE.fullmatch(s)
    if not m:
        return None
    return m.group(1).upper()


def _price_cell(price: Any) -> str:
    if price is None:
        return ""
    try:
        x = float(price)
        if abs(x - int(x)) < 1e-9:
            return str(int(x))
        return str(x)
    except (TypeError, ValueError):
        return str(price).strip()


def _shop_cell(p: Product) -> str:
    return ((p.shop_name_chinese or p.shop_name or "") or "").strip()


def _link_cell(p: Product) -> str:
    return ((p.link_default or "") or "").strip()


def _name_cell(p: Product) -> str:
    return ((p.name or "") or "").strip()


def _cell_is_blank_or_error(val: str) -> bool:
    s = (val or "").strip()
    if not s:
        return True
    u = s.upper()
    return u in ("#N/A", "#NA", "#REF!", "#VALUE!", "#NULL!", "#DIV/0!", "#NAME?", "N/A")


def _cells_equal(a: str, b: str) -> bool:
    return (a or "").strip() == (b or "").strip()


def lookup_latest_order_code_for_sku(db: Session, base_sku: str) -> str:
    """Mã đơn web gần nhất (order_code) có mua SP với products.code = base_sku (bỏ đơn hủy)."""
    from app.models.order import OrderStatus

    code = (base_sku or "").strip().upper()
    if not code:
        return ""
    row = (
        db.query(Order.order_code)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .join(Product, Product.id == OrderItem.product_id)
        .filter(
            func.upper(Product.code) == code,
            Order.status != OrderStatus.CANCELLED.value,
        )
        .order_by(Order.created_at.desc(), Order.id.desc())
        .first()
    )
    if not row:
        return ""
    return str(row[0] or "").strip()


def prefetch_latest_order_codes(db: Session, base_skus: List[str]) -> Dict[str, str]:
    """Tra một lần nhiều mã gốc → order_code gần nhất (PostgreSQL DISTINCT ON)."""
    from app.models.order import OrderStatus

    codes = sorted({(c or "").strip().upper() for c in base_skus if (c or "").strip()})
    out: Dict[str, str] = {c: "" for c in codes}
    if not codes:
        return out
    try:
        from sqlalchemy import text

        rows = db.execute(
            text(
                """
                SELECT DISTINCT ON (upper(p.code))
                       upper(p.code) AS sku,
                       o.order_code
                FROM products p
                JOIN order_items oi ON oi.product_id = p.id
                JOIN orders o ON o.id = oi.order_id
                WHERE upper(p.code) = ANY(:codes)
                  AND o.status <> :cancelled
                ORDER BY upper(p.code), o.created_at DESC NULLS LAST, o.id DESC
                """
            ),
            {"codes": codes, "cancelled": OrderStatus.CANCELLED.value},
        ).fetchall()
        for sku, order_code in rows:
            k = str(sku or "").strip().upper()
            if k:
                out[k] = str(order_code or "").strip()
        return out
    except Exception:
        logger.warning(
            "[HANG_DAT_MOI_AUTOFILL] prefetch latest orders failed — fallback từng mã",
            exc_info=True,
        )
        for c in codes:
            out[c] = lookup_latest_order_code_for_sku(db, c)
        return out


def _ensure_headers(
    service: Any, spread: str, t_esc: str, header_rows: int
) -> None:
    """Đảm bảo header S/T đúng nhãn (không đụng hàng dữ liệu)."""
    if header_rows < 1:
        return
    wanted = {
        _COL_S: "Tên sản phẩm",
        _COL_T: "Đơn hàng gần nhất",
    }
    try:
        cur = (
            service.spreadsheets()
            .values()
            .batchGet(
                spreadsheetId=spread,
                ranges=[f"{t_esc}!{c}1" for c in wanted.keys()],
                majorDimension="ROWS",
            )
            .execute()
        )
        have_map: Dict[str, str] = {}
        for col, vr in zip(wanted.keys(), cur.get("valueRanges") or []):
            vals = vr.get("values") or []
            have_map[col] = str(vals[0][0]).strip() if vals and vals[0] else ""
        data = []
        for col, label in wanted.items():
            if have_map.get(col) != label:
                data.append({"range": f"{t_esc}!{col}1", "values": [[label]]})
        if data:
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=spread,
                body={"valueInputOption": "USER_ENTERED", "data": data},
            ).execute()
    except Exception:
        logger.warning(
            "[HANG_DAT_MOI_AUTOFILL] Không cập nhật được header cột S/T",
            exc_info=True,
        )


def lookup_product_for_order_sku(db: Session, raw_q: str) -> Optional[Product]:
    base = parse_order_sku_base(raw_q)
    if not base:
        return None
    return get_product_by_code(db, code=base)


def _target_config() -> Tuple[str, int, int, float]:
    spread = (
        getattr(settings, "GOOGLE_SHEETS_HANG_DAT_MOI_SPREADSHEET_ID", "") or ""
    ).strip()
    gid = int(getattr(settings, "GOOGLE_SHEETS_HANG_DAT_MOI_SHEET_GID", 0) or 0)
    header_rows = int(getattr(settings, "GOOGLE_SHEETS_HANG_DAT_MOI_HEADER_ROWS", 1) or 0)
    poll = float(getattr(settings, "GOOGLE_SHEETS_HANG_DAT_MOI_POLL_SECONDS", 2) or 2)
    return spread, gid, max(0, header_rows), max(1.0, poll)


def _enabled() -> bool:
    return bool(getattr(settings, "GOOGLE_SHEETS_HANG_DAT_MOI_AUTOFILL_ENABLED", False))


def _get_service_cached():
    global _cached_service, _cached_service_at
    now = time.monotonic()
    if _cached_service is not None and (now - _cached_service_at) < _SERVICE_TTL_SEC:
        return _cached_service
    from app.services.google_sheets_client import _get_sheets_service

    _cached_service = _get_sheets_service()
    _cached_service_at = now
    return _cached_service


def _resolve_title(service: Any, spread: str, gid: int) -> str:
    global _cached_title
    if _cached_title:
        return _cached_title
    from app.services.google_sheets_client import _sheet_title_for_gid

    _cached_title = _sheet_title_for_gid(service, spread, gid)
    return _cached_title


def _read_q_column(
    service: Any, spread: str, t_esc: str, start_row: int
) -> Dict[int, str]:
    rng = f"{t_esc}!{_COL_Q}{start_row}:{_COL_Q}"
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spread, range=rng, majorDimension="ROWS")
        .execute()
    )
    values = result.get("values") or []
    out: Dict[int, str] = {}
    for i, row in enumerate(values):
        rnum = start_row + i
        out[rnum] = str((row[0] if row else "") or "").strip()
    return out


def _read_rows_q_ab(
    service: Any, spread: str, t_esc: str, row_nums: List[int]
) -> Dict[int, List[str]]:
    """Đọc Q:AB cho danh sách hàng (gom range liên tục khi có thể)."""
    if not row_nums:
        return {}
    rows_sorted = sorted(set(row_nums))
    ranges: List[str] = []
    seg_start = rows_sorted[0]
    prev = rows_sorted[0]
    for r in rows_sorted[1:]:
        if r == prev + 1:
            prev = r
            continue
        ranges.append(f"{t_esc}!{_COL_Q}{seg_start}:{_COL_AB}{prev}")
        seg_start = prev = r
    ranges.append(f"{t_esc}!{_COL_Q}{seg_start}:{_COL_AB}{prev}")

    out: Dict[int, List[str]] = {}
    resp = (
        service.spreadsheets()
        .values()
        .batchGet(spreadsheetId=spread, ranges=ranges, majorDimension="ROWS")
        .execute()
    )
    for vr in resp.get("valueRanges") or []:
        rng = str(vr.get("range") or "")
        m = re.search(r"![A-Z]+(\d+):", rng)
        if not m:
            continue
        start = int(m.group(1))
        for i, row in enumerate(vr.get("values") or []):
            cells = [str(c) if c is not None else "" for c in row]
            while len(cells) < 12:
                cells.append("")
            out[start + i] = cells
    return out


def _apply_row_update(
    *,
    t_esc: str,
    rnum: int,
    q_raw: str,
    cur_s: str,
    cur_t: str,
    cur_u: str,
    cur_w: str,
    cur_ab: str,
    backfill_only: bool,
    product_cache: Dict[str, Optional[Product]],
    order_cache: Dict[str, str],
    db: Session,
    updates: List[Dict[str, Any]],
    stats: Dict[str, int],
) -> None:
    base = parse_order_sku_base(q_raw)
    if not base:
        stats["skipped_format"] += 1
        return
    stats["matched"] += 1

    if base not in product_cache:
        product_cache[base] = get_product_by_code(db, code=base)
    prod = product_cache[base]

    if prod is None:
        stats["not_found"] += 1
        if backfill_only:
            return
        need_clear = any(
            not _cell_is_blank_or_error(x)
            for x in (cur_s, cur_t, cur_u, cur_w, cur_ab)
        )
        if not need_clear:
            stats["unchanged"] += 1
            return
        updates.append({"range": f"{t_esc}!{_COL_S}{rnum}", "values": [[""]]})
        updates.append({"range": f"{t_esc}!{_COL_T}{rnum}", "values": [[""]]})
        updates.append({"range": f"{t_esc}!{_COL_U}{rnum}", "values": [[""]]})
        updates.append({"range": f"{t_esc}!{_COL_W}{rnum}", "values": [[""]]})
        updates.append({"range": f"{t_esc}!{_COL_AB}{rnum}", "values": [[""]]})
        stats["cleared"] += 1
        return

    if base not in order_cache:
        order_cache[base] = lookup_latest_order_code_for_sku(db, base)
    new_s = _name_cell(prod)
    new_t = order_cache.get(base) or ""
    new_u = _price_cell(prod.price)
    new_w = _link_cell(prod)
    new_ab = _shop_cell(prod)

    if backfill_only:
        will_s = _cell_is_blank_or_error(str(cur_s)) and bool(new_s)
        will_t = _cell_is_blank_or_error(str(cur_t)) and bool(new_t)
        will_u = _cell_is_blank_or_error(str(cur_u)) and bool(new_u)
        will_w = _cell_is_blank_or_error(str(cur_w)) and bool(new_w)
        will_ab = _cell_is_blank_or_error(str(cur_ab)) and bool(new_ab)
        if not (will_s or will_t or will_u or will_w or will_ab):
            stats["unchanged"] += 1
            return
        if will_s:
            updates.append({"range": f"{t_esc}!{_COL_S}{rnum}", "values": [[new_s]]})
        if will_t:
            updates.append({"range": f"{t_esc}!{_COL_T}{rnum}", "values": [[new_t]]})
        if will_u:
            updates.append({"range": f"{t_esc}!{_COL_U}{rnum}", "values": [[new_u]]})
        if will_w:
            updates.append({"range": f"{t_esc}!{_COL_W}{rnum}", "values": [[new_w]]})
        if will_ab:
            updates.append({"range": f"{t_esc}!{_COL_AB}{rnum}", "values": [[new_ab]]})
        stats["filled"] += 1
        return

    same = (
        _cells_equal(str(cur_s), new_s)
        and _cells_equal(str(cur_t), new_t)
        and _cells_equal(str(cur_u), new_u)
        and _cells_equal(str(cur_w), new_w)
        and _cells_equal(str(cur_ab), new_ab)
    )
    if same:
        stats["unchanged"] += 1
        return
    updates.append({"range": f"{t_esc}!{_COL_S}{rnum}", "values": [[new_s]]})
    updates.append({"range": f"{t_esc}!{_COL_T}{rnum}", "values": [[new_t]]})
    updates.append({"range": f"{t_esc}!{_COL_U}{rnum}", "values": [[new_u]]})
    updates.append({"range": f"{t_esc}!{_COL_W}{rnum}", "values": [[new_w]]})
    updates.append({"range": f"{t_esc}!{_COL_AB}{rnum}", "values": [[new_ab]]})
    stats["filled"] += 1


def process_hang_dat_moi_autofill(db: Session) -> Dict[str, Any]:
    """
    Một vòng nhanh:
    - Đọc cột Q
    - Lần đầu: đọc Q:AB toàn tab, backfill ô trống/#N/A
    - Sau đó: nếu Q không đổi → bỏ qua; nếu đổi → chỉ xử lý hàng Q mới/đổi
    """
    if not _enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    spread, gid, header_rows, _poll = _target_config()
    if not spread or gid <= 0:
        return {
            "ok": False,
            "error": "Thiếu GOOGLE_SHEETS_HANG_DAT_MOI_SPREADSHEET_ID / SHEET_GID",
        }

    from app.services.google_sheets_client import (
        _escape_sheet_title,
        _values_batch_update,
    )

    global _last_q_by_row

    with _run_lock:
        service = _get_service_cached()
        title = _resolve_title(service, spread, gid)
        t_esc = _escape_sheet_title(title)
        start_row = header_rows + 1
        _ensure_headers(service, spread, t_esc, header_rows)

        q_map = _read_q_column(service, spread, t_esc, start_row)
        first_pass = not _last_q_by_row

        changed_rows: List[int] = []
        if first_pass:
            changed_rows = list(q_map.keys())
        else:
            all_rows = set(q_map.keys()) | set(_last_q_by_row.keys())
            for rnum in sorted(all_rows):
                if q_map.get(rnum, "") != _last_q_by_row.get(rnum, ""):
                    changed_rows.append(rnum)

        if not first_pass and not changed_rows:
            return {
                "ok": True,
                "spreadsheet_id": spread,
                "sheet_gid": gid,
                "sheet_title": title,
                "rows_scanned": len(q_map),
                "matched_sku_rows": 0,
                "skipped_format_rows": 0,
                "filled_rows": 0,
                "cleared_rows": 0,
                "unchanged_rows": 0,
                "not_found_rows": 0,
                "cells_updated": 0,
                "q_changed_rows": 0,
                "first_pass": False,
                "idle": True,
            }

        if first_pass:
            rng = f"{t_esc}!{_COL_Q}{start_row}:{_COL_AB}"
            result = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=spread, range=rng, majorDimension="ROWS")
                .execute()
            )
            row_data: Dict[int, List[str]] = {}
            for i, row in enumerate(result.get("values") or []):
                cells = [str(c) if c is not None else "" for c in row]
                while len(cells) < 12:
                    cells.append("")
                row_data[start_row + i] = cells
        else:
            row_data = _read_rows_q_ab(service, spread, t_esc, changed_rows)

        updates: List[Dict[str, Any]] = []
        stats = {
            "matched": 0,
            "skipped_format": 0,
            "filled": 0,
            "cleared": 0,
            "unchanged": 0,
            "not_found": 0,
        }
        product_cache: Dict[str, Optional[Product]] = {}
        # Q=0, R=1, S=2, T=3, U=4, W=6, AB=11 trong range Q:AB
        idx_s, idx_t, idx_u, idx_w, idx_ab = 2, 3, 4, 6, 11

        target_rows = changed_rows if not first_pass else sorted(row_data.keys())
        bases_needed: List[str] = []
        for rnum in target_rows:
            cells = row_data.get(rnum) or [""] * 12
            q_raw = q_map.get(rnum, "") or str(cells[0] or "").strip()
            b = parse_order_sku_base(q_raw)
            if b:
                bases_needed.append(b)
        order_cache = prefetch_latest_order_codes(db, bases_needed)

        for rnum in target_rows:
            cells = row_data.get(rnum) or [""] * 12
            q_raw = q_map.get(rnum, "")
            if not q_raw and cells:
                q_raw = str(cells[0] or "").strip()
            cur_s = cells[idx_s] if len(cells) > idx_s else ""
            cur_t = cells[idx_t] if len(cells) > idx_t else ""
            cur_u = cells[idx_u] if len(cells) > idx_u else ""
            cur_w = cells[idx_w] if len(cells) > idx_w else ""
            cur_ab = cells[idx_ab] if len(cells) > idx_ab else ""
            backfill_only = first_pass
            _apply_row_update(
                t_esc=t_esc,
                rnum=rnum,
                q_raw=q_raw,
                cur_s=cur_s,
                cur_t=cur_t,
                cur_u=cur_u,
                cur_w=cur_w,
                cur_ab=cur_ab,
                backfill_only=backfill_only,
                product_cache=product_cache,
                order_cache=order_cache,
                db=db,
                updates=updates,
                stats=stats,
            )

        if updates:
            _values_batch_update(service, spread, updates)

        _last_q_by_row = dict(q_map)

        out = {
            "ok": True,
            "spreadsheet_id": spread,
            "sheet_gid": gid,
            "sheet_title": title,
            "rows_scanned": len(q_map),
            "matched_sku_rows": stats["matched"],
            "skipped_format_rows": stats["skipped_format"],
            "filled_rows": stats["filled"],
            "cleared_rows": stats["cleared"],
            "unchanged_rows": stats["unchanged"],
            "not_found_rows": stats["not_found"],
            "cells_updated": len(updates),
            "q_changed_rows": 0 if first_pass else len(changed_rows),
            "first_pass": first_pass,
            "idle": False,
        }
        if stats["filled"] or stats["cleared"]:
            logger.info(
                "[HANG_DAT_MOI_AUTOFILL] tab=%s filled=%s cleared=%s not_found=%s cells=%s",
                title,
                stats["filled"],
                stats["cleared"],
                stats["not_found"],
                len(updates),
            )
        return out


def _daemon_loop() -> None:
    from app.db.session import SessionLocal

    _, _, _, poll = _target_config()
    time.sleep(5.0)
    logger.info(
        "[HANG_DAT_MOI_AUTOFILL] daemon started poll=%ss spread=%s…",
        poll,
        (_target_config()[0] or "")[:8],
    )
    while True:
        if not _enabled():
            time.sleep(poll)
            continue
        t0 = time.monotonic()
        db = SessionLocal()
        try:
            process_hang_dat_moi_autofill(db)
        except Exception:
            logger.exception("[HANG_DAT_MOI_AUTOFILL] tick failed")
            global _cached_service, _cached_title
            _cached_service = None
            _cached_title = None
        finally:
            db.close()
        elapsed = time.monotonic() - t0
        time.sleep(max(0.5, poll - elapsed))


def start_hang_dat_moi_autofill_daemon_if_enabled() -> None:
    global _daemon_started
    if not _enabled():
        return
    spread, gid, _, poll = _target_config()
    if not spread or gid <= 0:
        logger.warning(
            "[HANG_DAT_MOI_AUTOFILL] bật nhưng thiếu spreadsheet_id/gid — không start daemon"
        )
        return
    with _daemon_lock:
        if _daemon_started:
            return
        t = threading.Thread(
            target=_daemon_loop,
            name="hang-dat-moi-autofill",
            daemon=True,
        )
        t.start()
        _daemon_started = True
        logger.info(
            "[HANG_DAT_MOI_AUTOFILL] daemon queued poll=%ss gid=%s",
            poll,
            gid,
        )
