from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import islice
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.product import Product
from app.services.admin_source_stock_batch import _cssbuy_row_shows_variant_matrix, _hibox_row_shows_color_size_catalog
from app.services.import_batch_url_coercion import FETCH_TARGET_CSSBUY, FETCH_TARGET_HIBOX, coerce_url_for_excel_batch_import
from app.services.import_cssbuy_client import (
    ImportCssbuyError,
    cssbuy_html_disclaimer_agreement_without_add_to_cart,
    cssbuy_html_shows_add_to_cart_button,
    fetch_cssbuy_item_json_bundle,
)
from app.services.import_hibox_scraper import (
    ImportHiboxError,
    hibox_canonical_scrape_url,
    hibox_scrape_signals_removed_or_not_found_offer,
    normalize_product_import_url,
    scrape_hibox_for_import,
)
from app.services.hibox_cart_dom_probe import HIBOX_CART_CTA_PROBE_JS

logger = logging.getLogger(__name__)

_queue: deque[int] = deque()
_queued_ids: set[int] = set()
_queue_lock = threading.Lock()
_worker_started = False
_worker_thread_ref: Optional[threading.Thread] = None
_worker_lock = threading.Lock()

SOURCE_STOCK_WORKER_STATE_ROW_ID = 1
_worker_pause_cached_at_mono: float = -1000.0
_worker_pause_cached: bool = False
_worker_pause_updated_at: Optional[datetime] = None
_worker_pause_lock = threading.Lock()
_WORKER_PAUSE_CACHE_SECONDS = 2.5


def invalidate_source_stock_worker_pause_cache() -> None:
    global _worker_pause_cached_at_mono
    with _worker_pause_lock:
        _worker_pause_cached_at_mono = -1000.0


def worker_pause_db_snapshot(*, force_refresh: bool = False) -> Tuple[bool, Optional[datetime]]:
    """Đọc cờ paused từ DB (cache ngắn giữa các lần trong worker)."""
    global _worker_pause_cached_at_mono, _worker_pause_cached, _worker_pause_updated_at
    now_m = time.monotonic()
    with _worker_pause_lock:
        if (
            not force_refresh
            and (now_m - _worker_pause_cached_at_mono) < _WORKER_PAUSE_CACHE_SECONDS
        ):
            return _worker_pause_cached, _worker_pause_updated_at
    from app.models.source_stock_worker_state import SourceStockWorkerState

    db = SessionLocal()
    try:
        row = (
            db.query(SourceStockWorkerState)
            .filter(SourceStockWorkerState.id == SOURCE_STOCK_WORKER_STATE_ROW_ID)
            .first()
        )
        paused = bool(row.paused) if row else False
        upd = row.updated_at if row else None
    finally:
        db.close()

    with _worker_pause_lock:
        _worker_pause_cached = paused
        _worker_pause_updated_at = upd
        _worker_pause_cached_at_mono = time.monotonic()

    return paused, upd


def set_source_stock_worker_paused(db: Session, paused: bool) -> None:
    """Ghi cờ paused (singleton id=1); commit trong session được truyền."""
    from app.models.source_stock_worker_state import SourceStockWorkerState

    row = (
        db.query(SourceStockWorkerState)
        .filter(SourceStockWorkerState.id == SOURCE_STOCK_WORKER_STATE_ROW_ID)
        .first()
    )
    upd = _utcnow()
    if row is None:
        row = SourceStockWorkerState(
            id=SOURCE_STOCK_WORKER_STATE_ROW_ID,
            paused=paused,
            updated_at=upd,
        )
        db.add(row)
    else:
        row.paused = paused
        row.updated_at = upd
    db.commit()
    invalidate_source_stock_worker_pause_cache()


def get_source_stock_worker_memory_queue_depth() -> int:
    with _queue_lock:
        return len(_queue)


def clear_source_stock_in_memory_queue() -> Dict[str, int]:
    """Xóa deque id trong-process (worker của process nhận request). Không xóa hàng chờ/ghi nhận của process khác."""
    with _queue_lock:
        n = len(_queue)
        _queue.clear()
        _queued_ids.clear()
    return {"cleared_count": n}


def _utc_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    u = dt
    if u.tzinfo is None:
        u = u.replace(tzinfo=timezone.utc)
    return u.isoformat()


def _bulk_product_mini_payloads(sess: Session, ids: Sequence[int]) -> Dict[int, Dict[str, Any]]:
    uniq: List[int] = []
    seen_ids: set[int] = set()
    for raw in ids:
        try:
            xi = int(raw)
        except (TypeError, ValueError):
            continue
        if xi <= 0 or xi in seen_ids:
            continue
        seen_ids.add(xi)
        uniq.append(xi)
    if not uniq:
        return {}
    rows = sess.query(Product).filter(Product.id.in_(uniq)).all()
    out: Dict[int, Dict[str, Any]] = {}
    for p in rows:
        pk = int(p.id)
        out[pk] = {
            "product_db_id": pk,
            "product_code": ((p.product_id or "").strip() or None),
            "name": (p.name or "")[:220],
            "link_default": ((p.link_default or "").strip() or None),
        }
    return out


def _peek_memory_queue_product_ids(limit: int = 8) -> List[int]:
    n = max(0, limit)
    if not n:
        return []
    with _queue_lock:
        return list(islice(_queue, 0, n))


def _worker_progress_mark_started(product_id: int) -> None:
    from app.models.source_stock_worker_state import SourceStockWorkerState

    pid = int(product_id)
    if pid <= 0:
        return
    db = SessionLocal()
    try:
        row = db.query(SourceStockWorkerState).filter(SourceStockWorkerState.id == SOURCE_STOCK_WORKER_STATE_ROW_ID).first()
        now = _utcnow()
        if row is None:
            row = SourceStockWorkerState(
                id=SOURCE_STOCK_WORKER_STATE_ROW_ID,
                paused=False,
                updated_at=now,
                checking_product_db_id=pid,
                checking_started_at=now,
            )
            db.add(row)
        else:
            row.checking_product_db_id = pid
            row.checking_started_at = now
            row.updated_at = now
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("worker progress mark_started failed pid=%s: %s", product_id, exc)
    finally:
        db.close()


def _worker_progress_mark_finished(
    product_id: int,
    status: str,
    *,
    products_commit_ok: Optional[bool] = None,
    products_commit_detail: Optional[str] = None,
) -> None:
    from app.models.source_stock_worker_state import SourceStockWorkerState

    pid = int(product_id)
    if pid <= 0:
        return
    st = (status or "unknown")[:64]
    db = SessionLocal()
    try:
        row = db.query(SourceStockWorkerState).filter(SourceStockWorkerState.id == SOURCE_STOCK_WORKER_STATE_ROW_ID).first()
        now = _utcnow()
        if row is None:
            row = SourceStockWorkerState(
                id=SOURCE_STOCK_WORKER_STATE_ROW_ID,
                paused=False,
                updated_at=now,
                last_done_product_db_id=pid,
                last_done_finished_at=now,
                last_done_source_stock_status=st,
            )
            db.add(row)
        else:
            row.checking_product_db_id = None
            row.checking_started_at = None
            row.last_done_product_db_id = pid
            row.last_done_finished_at = now
            row.last_done_source_stock_status = st
            row.updated_at = now

        if products_commit_ok is not None:
            row.last_products_commit_ok = bool(products_commit_ok)
            row.last_products_commit_at = now
            row.last_products_commit_detail = (products_commit_detail or "")[:920] or (
                "Đã ghi vào worker state (không kèm mô tả)."
            )

        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("worker progress mark_finished failed pid=%s: %s", product_id, exc)
    finally:
        db.close()


def get_source_stock_worker_admin_snapshot(*, force_refresh_pause: bool = False) -> Dict[str, Any]:
    paused, pause_updated = worker_pause_db_snapshot(force_refresh=force_refresh_pause)
    env_on = bool(getattr(settings, "SOURCE_STOCK_CHECK_ENABLED", True))
    depth = get_source_stock_worker_memory_queue_depth()
    thread_alive = bool(_worker_thread_ref and _worker_thread_ref.is_alive())
    daemon_flag = bool(_worker_started)

    idle: Optional[str]
    reason_vi = ""
    if not env_on:
        idle = "disabled_by_env"
        reason_vi = "Đã tắt SOURCE_STOCK_CHECK_ENABLED — worker không được khởi động."
    elif paused:
        idle = "paused_via_db"
        reason_vi = "Tạm dừng qua DB — mọi process backend có quyền DB đều không scrape trong vòng lặp."
    elif not daemon_flag:
        idle = "daemon_not_started"
        reason_vi = "Daemon chưa bật trong process báo snapshot này."
    elif not thread_alive:
        idle = "thread_not_alive"
        reason_vi = "Luồng worker không còn sống trong process này — nên khởi động lại tiến trình backend."
    else:
        idle = None

    pu_iso = _utc_iso(pause_updated)

    checking: Optional[Dict[str, Any]] = None
    last_completed: Optional[Dict[str, Any]] = None
    upcoming_candidates: List[Dict[str, Any]] = []

    from app.models.source_stock_worker_state import SourceStockWorkerState

    products_commit_audit: Optional[Dict[str, Any]] = None

    dbx = SessionLocal()
    try:
        row_ws = (
            dbx.query(SourceStockWorkerState)
            .filter(SourceStockWorkerState.id == SOURCE_STOCK_WORKER_STATE_ROW_ID)
            .first()
        )
        peek_mem = _peek_memory_queue_product_ids(8)
        db_due_ids: List[int] = []
        try:
            db_due_ids = _preview_upcoming_db_product_ids(dbx, 12)
        except Exception as exc:
            logger.warning("preview upcoming db product ids failed: %s", exc)

        agg_ids: List[int] = []
        if row_ws and row_ws.checking_product_db_id:
            agg_ids.append(int(row_ws.checking_product_db_id))
        if row_ws and row_ws.last_done_product_db_id:
            agg_ids.append(int(row_ws.last_done_product_db_id))
        agg_ids.extend(peek_mem)
        agg_ids.extend(db_due_ids)
        mins = _bulk_product_mini_payloads(dbx, agg_ids)

        if row_ws and row_ws.checking_product_db_id:
            cid = int(row_ws.checking_product_db_id)
            chk = dict(
                mins.get(cid)
                or {"product_db_id": cid, "product_code": None, "name": None, "link_default": None}
            )
            chk["checking_started_at_utc_iso"] = _utc_iso(row_ws.checking_started_at)
            checking = chk

        if row_ws and row_ws.last_done_product_db_id:
            lid = int(row_ws.last_done_product_db_id)
            lc = dict(
                mins.get(lid)
                or {"product_db_id": lid, "product_code": None, "name": None, "link_default": None}
            )
            lc["finished_at_utc_iso"] = _utc_iso(row_ws.last_done_finished_at)
            st_done = (row_ws.last_done_source_stock_status or "").strip()
            lc["source_stock_status"] = st_done or None
            last_completed = lc

        seen_next: set[int] = set()
        for pid in peek_mem:
            if pid in seen_next:
                continue
            seen_next.add(pid)
            m = dict(
                mins.get(pid)
                or {"product_db_id": pid, "product_code": None, "name": None, "link_default": None}
            )
            m["queue_hint"] = "memory_fifo"
            m["queue_hint_vi"] = "Đầu hàng chờ RAM của process báo KPI này (ưu tiên trước scheduler DB)."
            upcoming_candidates.append(m)
        for pid in db_due_ids:
            if pid in seen_next:
                continue
            seen_next.add(pid)
            m = dict(
                mins.get(pid)
                or {"product_db_id": pid, "product_code": None, "name": None, "link_default": None}
            )
            m["queue_hint"] = "db_due_next"
            m["queue_hint_vi"] = "Dự kiến lần «claim» từ DB nếu hàng chờ RAM trống hoặc hết FIFO."
            upcoming_candidates.append(m)

        if row_ws is not None and getattr(row_ws, "last_products_commit_at", None) is not None:
            lid_done = int(row_ws.last_done_product_db_id) if row_ws.last_done_product_db_id else None
            products_commit_audit = {
                "ok": row_ws.last_products_commit_ok,
                "at_utc_iso": _utc_iso(row_ws.last_products_commit_at),
                "detail": ((row_ws.last_products_commit_detail or "").strip() or None),
                "product_db_id": lid_done,
                "consistency_hint_vi": None,
            }
            co_ok = row_ws.last_products_commit_ok
            if co_ok is False:
                products_commit_audit["consistency_hint_vi"] = (
                    "Audit: lần scrape gần nhất không xác nhận được commit bảng products — xem detail."
                )
            elif co_ok is True and lid_done:
                pr = (
                    dbx.query(Product.source_stock_checked_at, Product.source_stock_status)
                    .filter(Product.id == lid_done)
                    .first()
                )
                if pr is None:
                    products_commit_audit["consistency_hint_vi"] = (
                        f"Đối chiếu DB: không còn products.id={lid_done} — không đọc được checked_at."
                    )
                else:
                    ca, stp = pr
                    if ca is None:
                        products_commit_audit["consistency_hint_vi"] = (
                            f"Đối chiếu DB: products.id={lid_done} có source_stock_checked_at = NULL — "
                            "lệch với audit commit OK."
                        )
                    else:
                        done_t = row_ws.last_done_finished_at
                        cax = ca
                        if cax.tzinfo is None:
                            cax = cax.replace(tzinfo=timezone.utc)
                        if done_t is not None:
                            dt = done_t
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            skew_sec = abs((cax - dt).total_seconds())
                        else:
                            skew_sec = 0.0
                        st_match = (stp or "").strip().lower() == (
                            (row_ws.last_done_source_stock_status or "").strip().lower()
                        )
                        if skew_sec > 125 or not st_match:
                            products_commit_audit["consistency_hint_vi"] = (
                                "Đối chiếu DB: worker state và dòng products có thể lệch (thời gian checked_at >2 phút "
                                f"so với last_done_* hoặc khác status). products.status={stp!r}, worker={row_ws.last_done_source_stock_status!r}."
                            )
                        else:
                            products_commit_audit["consistency_hint_vi"] = (
                                f"Đối chiếu DB: khớp products.id={lid_done} "
                                "(status + checked_at gần thời điểm last_done)."
                            )
    finally:
        dbx.close()

    next_primary = upcoming_candidates[0] if upcoming_candidates else None

    return {
        "env_source_stock_check_enabled": env_on,
        "db_paused": paused,
        "db_pause_updated_at_utc_iso": pu_iso,
        "daemon_thread_started_flag": daemon_flag,
        "daemon_thread_alive": thread_alive,
        "process_in_memory_queue_depth": depth,
        "check_interval_seconds": int(settings.SOURCE_STOCK_CHECK_INTERVAL_SECONDS),
        "effective_idle_reason": idle,
        "effective_idle_hint_vi": reason_vi or None,
        "deployment_notes_vi": (
            "Mỗi worker OS (tiến trình Python/Uvicorn) có thread daemon và hàng chờ RAM riêng; "
            "cờ pause lưu DB áp đồng thời cho mọi process. Trên VPS: một process → một luồng "
            "`source-stock-checker`; kiểm tra bằng log «source stock» hoặc `ps`/`pm2 list`."
        ),
        "checking": checking,
        "last_completed": last_completed,
        "next_upcoming_primary": next_primary,
        "upcoming_candidates": upcoming_candidates[:10],
        "products_commit_audit": products_commit_audit,
        "progress_notes_vi": (
            "«Đang scrape» và «Vừa xong» ghi vào DB (chia sẻ giữa mọi process). "
            "«Sắp tới» là ước lượng: SP đầu hàng chờ RAM của process này, rồi SP đến hạn trong DB "
            "(cùng thứ tự claim) — không đảm bảo từng-bytes nếu có nhiều replica khác chiếm claim."
        ),
    }


@dataclass
class SourceStockCheckResult:
    status: str
    error: Optional[str] = None


_CSSBUY_BLOCK_MSG_FRAGMENTS = (
    "captcha",
    "验证码",
    "verify",
    "cloudflare",
    "cf-ray",
    "blocked",
    "forbidden",
    "access denied",
    "rate limit",
    "too many",
    "csrf",
)


def _cssbuy_api_nonzero_suggests_block(payload: Dict[str, Any]) -> bool:
    """``code≠0``: đôi khi là chặn/captcha chứ không phải «hết offer» — nhánh đó fallback Hibox."""
    parts: List[str] = []
    try:
        for k in ("message", "msg", "detail", "data"):
            v = payload.get(k)
            if isinstance(v, str):
                parts.append(v)
            elif isinstance(v, dict):
                for nested in ("message", "msg", "detail", "reason"):
                    nv = v.get(nested)
                    if isinstance(nv, str):
                        parts.append(nv)
            elif isinstance(v, list):
                for el in v[:6]:
                    if isinstance(el, str):
                        parts.append(el)
                    elif isinstance(el, dict):
                        for nk in ("message", "msg"):
                            ee = el.get(nk)
                            if isinstance(ee, str):
                                parts.append(ee)
    except Exception:
        pass
    blob = " ".join(parts).strip().lower()
    if not blob:
        return False
    return any(s in blob for s in _CSSBUY_BLOCK_MSG_FRAGMENTS)


def _css_buy_result_signals_hibox_fallback(css: SourceStockCheckResult) -> bool:
    """CSSBuy không đọc được (blocked/captcha/mạng) hoặc lỗi quy đổi — chỉ khi đó gọi Hibox."""
    return (css.status or "").strip().lower() in {"blocked", "error"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _link_eligible_for_hibox_stock_check(url: str) -> bool:
    u = (url or "").strip().lower()
    if len(u) < 12:
        return False
    return any(
        marker in u
        for marker in (
            "hibox.mn",
            "taobao1688.kz",
            "1688.com",
            "offer.1688",
            "detail.1688",
            "taobao.com",
            "tmall.com",
        )
    )


def _eligible_due_products_query(sess: Session):
    """Truy vấn SP đến hạn TTL / next_check — thứ tự giống _claim_due_product_id (không sửa DB)."""
    now = _utcnow()
    stale_cutoff = now - timedelta(minutes=settings.SOURCE_STOCK_CHECK_STALE_MINUTES)
    return (
        sess.query(Product)
            .filter(Product.is_active == True)  # noqa: E712
            .filter(Product.link_default.isnot(None))
            .filter(
                or_(
                    Product.link_default.ilike("%hibox.mn%"),
                    Product.link_default.ilike("%taobao1688.kz%"),
                    Product.link_default.ilike("%1688.com%"),
                    Product.link_default.ilike("%offer.1688%"),
                    Product.link_default.ilike("%detail.1688%"),
                    Product.link_default.ilike("%taobao.com%"),
                    Product.link_default.ilike("%tmall.com%"),
                )
            )
            .filter(
                or_(
                    Product.source_stock_next_check_at.is_(None),
                    Product.source_stock_next_check_at <= now,
                    Product.source_stock_checked_at.is_(None),
                    Product.source_stock_checked_at <= stale_cutoff,
                )
            )
            .order_by(Product.source_stock_next_check_at.isnot(None), Product.source_stock_next_check_at.asc(), Product.id.asc())
    )


def _preview_upcoming_db_product_ids(sess: Session, limit: int = 8) -> List[int]:
    q = _eligible_due_products_query(sess)
    out: List[int] = []
    lim = max(1, limit)
    for p in q.limit(200).all():
        if not _link_eligible_for_hibox_stock_check(p.link_default or ""):
            continue
        out.append(int(p.id))
        if len(out) >= lim:
            break
    return out


def _evaluate_stock_via_cssbuy(raw_url: str) -> SourceStockCheckResult:
    """Đọc tình trạng qua CSSBuy (/web/item + PDP HTML); worker chỉ gọi Hibox khi kết quả CSS là blocked/error."""
    canonical_url = (normalize_product_import_url((raw_url or "").strip()) or (raw_url or "").strip()).strip()
    cssbuy_page, coercion_err = coerce_url_for_excel_batch_import(canonical_url, FETCH_TARGET_CSSBUY)
    if coercion_err:
        return SourceStockCheckResult(
            status="error",
            error=f"Không quy đổi được sang URL CSSBuy hợp lệ: {coercion_err}"[:1000],
        )
    canonical_url = (cssbuy_page or "").strip() or canonical_url
    try:
        payload, page_html = fetch_cssbuy_item_json_bundle(canonical_url)
        code = payload.get("code")
        if code != 0:
            msg_tail = str(payload.get("message") or payload.get("msg") or f"code={code}")[:780]
            compact = ("CSSBuy /web/item không trả OK — " + msg_tail)[:1000]
            if _cssbuy_api_nonzero_suggests_block(payload):
                return SourceStockCheckResult(
                    status="blocked",
                    error=(compact + " — có dấu hiệu chặn/CAPTCHA, fallback Hibox.")[:1000],
                )
            return SourceStockCheckResult(
                status="out_of_stock",
                error=(
                    "CSSBuy /web/item không trả OK (dead offer hoặc API nghiệp vụ từ chối) — " + msg_tail
                )[:1000],
            )
        rows = payload.get("data")
        row0 = rows[0] if isinstance(rows, list) and rows else None
        if not isinstance(row0, dict):
            return SourceStockCheckResult(
                status="out_of_stock",
                error="CSSBuy trả payload không có dòng data hợp lệ — thường gặp khi PDP không load / offer đã mất.",
            )
        ph = (page_html or "").strip()
        if cssbuy_html_disclaimer_agreement_without_add_to_cart(ph):
            return SourceStockCheckResult(
                status="out_of_stock",
                error=(
                    "CSSBuy: HTML PDP có đoạn disclaimer đồng ý («I have read… terms of service…») nhưng "
                    "không thấy nút «Add To Cart» — coi PDP hết hàng / không còn bán được."
                )[:1000],
            )
        try:
            price = float(row0.get("price") or 0)
        except (TypeError, ValueError):
            price = 0.0
        title = (row0.get("title") or row0.get("title_cn") or "").strip()
        variant_matrix = _cssbuy_row_shows_variant_matrix(row0)
        has_signal = bool(title) and (price > 0 or variant_matrix)
        if has_signal:
            if not cssbuy_html_shows_add_to_cart_button(page_html):
                return SourceStockCheckResult(
                    status="out_of_stock",
                    error=(
                        "CSSBuy: API có dữ liệu nhưng HTML PDP không có nút «Add To Cart» "
                        "(khoanh đỏ) — coi offer không còn bán được / hết hàng."
                    )[:1000],
                )
            return SourceStockCheckResult(status="in_stock")
        return SourceStockCheckResult(
            status="out_of_stock",
            error=(
                "CSSBuy: thiếu tiêu đề hoặc không có (giá > 0 / ma trận SKU thuộc tính) — không khẳng định được offer còn."
            ),
        )
    except ImportCssbuyError as exc:
        es = str(exc)
        return SourceStockCheckResult(
            status="blocked",
            error=(
                "CSSBuy không tải/lấy được (PDP skeleton, không CSRF/HTML, `/web/item` không JSON…) — có thể bị "
                + "Cloudflare/WAF hoặc mạng — "
                + es
            )[:1000],
        )
    except Exception as exc:
        logger.warning("cssbuy source stock evaluate failed: %s", exc)
        return SourceStockCheckResult(
            status="error",
            error=((str(exc) or "unexpected_error")[:920] + " — chưa kiểm tra được.")[:1000],
        )


def _evaluate_stock_primary_cssbuy_with_hibox_fallback(raw_url: str) -> SourceStockCheckResult:
    """
    PDP worker — **ưu tiên một trang cho kết luận nghiệp vụ**:
    đọc **CSSBuy (/web/item + PDP HTML)** trước; nếu ``in_stock`` / ``out_of_stock`` rõ từ CSS thì không scrape Hibox.

    Fallback **scrape Hibox** chỉ khi CSS trả ``blocked`` / ``error`` (không CSRF/HTML, không JSON, có dấu hiệu CAPTCHA/chặn
    trên thông báo API, không quy đổi URL…).

    Hai nguồn **không gộp lời giải** trong cùng lượt: Hibox thay hoàn toàn khi CSS trả blocked/error.
    """
    css = _evaluate_stock_via_cssbuy(raw_url)
    if css.status == "in_stock":
        return css
    if _css_buy_result_signals_hibox_fallback(css):
        return _evaluate_stock_via_hibox(raw_url)
    return css


def admin_preview_source_stock_by_url(raw_url: str) -> Dict[str, Any]:
    """
    Admin thử PDP giống worker (**một PDP có kết luận nghiệp vụ**; CSS ``blocked``/``error`` → Hibox) **không ghi DB**.
    """
    stripped = (raw_url or "").strip()
    canon = (normalize_product_import_url(stripped) or stripped).strip()

    cssbuy_page, coercion_css_err = coerce_url_for_excel_batch_import(canon, FETCH_TARGET_CSSBUY)
    hibox_page, coercion_hb_err = coerce_url_for_excel_batch_import(canon, FETCH_TARGET_HIBOX)

    def _bubble(r: SourceStockCheckResult) -> Dict[str, Any]:
        return {"status": (r.status or "").strip(), "error": r.error}

    coercion = {
        "cssbuy_url": (cssbuy_page or "").strip(),
        "cssbuy_coercion_error": (coercion_css_err or "").strip(),
        "hibox_url": (hibox_page or "").strip(),
        "hibox_coercion_error": (coercion_hb_err or "").strip(),
    }

    markers = ("hibox.mn", "1688.com", "detail.1688", "offer.1688", "taobao", "tmall")
    eligible = _link_eligible_for_hibox_stock_check(canon)
    if not eligible:
        note = (
            "Link không thuộc miền được worker PDP kiểm tra — cần chứa một trong: "
            + ", ".join(markers)
        )
        err_r = SourceStockCheckResult(status="error", error=note[:1000])
        skipped = SourceStockCheckResult(status="skipped", error=None)
        return {
            "ok": True,
            "canonical_input": canon,
            "link_eligible": False,
            "coercion": coercion,
            "cssbuy": _bubble(skipped),
            "hibox": _bubble(skipped),
            "merged": _bubble(err_r),
        }

    css = _evaluate_stock_via_cssbuy(canon)
    if css.status == "in_stock":
        skip_r = SourceStockCheckResult(status="skipped", error="Không scrape Hibox — CSSBuy đã in_stock.")
        return {
            "ok": True,
            "canonical_input": canon,
            "link_eligible": True,
            "coercion": coercion,
            "cssbuy": _bubble(css),
            "hibox": _bubble(skip_r),
            "merged": _bubble(css),
        }

    if _css_buy_result_signals_hibox_fallback(css):
        hb = _evaluate_stock_via_hibox(canon)
        return {
            "ok": True,
            "canonical_input": canon,
            "link_eligible": True,
            "coercion": coercion,
            "cssbuy": _bubble(css),
            "hibox": _bubble(hb),
            "merged": _bubble(hb),
        }

    skip_hibox_r = SourceStockCheckResult(
        status="skipped",
        error=(
            "Không scrape Hibox — CSS đã có kết quả nghiệp vụ (in_stock/out_of_stock). "
            "Chỉ fallback Hibox khi nhánh CSS `blocked` hoặc `error`."
        ),
    )
    return {
        "ok": True,
        "canonical_input": canon,
        "link_eligible": True,
        "coercion": coercion,
        "cssbuy": _bubble(css),
        "hibox": _bubble(skip_hibox_r),
        "merged": _bubble(css),
    }


def _hibox_quick_cart_cta_via_playwright(page_url: str) -> Optional[bool]:
    """
    PDP Hibox: có nút «САГСЛАХ» (thêm vào giỏ) không — fallback khi scrape đầy đủ lỗi.
    Trả None nếu Playwright không chạy/navigate không xong (không kết luận cứng).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    opened = (page_url or "").strip()
    if len(opened) < 14:
        return None

    ua = getattr(settings, "IMPORT_1688_USER_AGENT", None) or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    headless_raw = getattr(settings, "SOURCE_STOCK_CHECK_HEADLESS", True)
    headless = str(headless_raw).strip().lower() not in {"0", "false", "no"}

    needle_js = HIBOX_CART_CTA_PROBE_JS

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="mn-MN",
                timezone_id="Asia/Ulaanbaatar",
                user_agent=ua,
            )
            page = ctx.new_page()
            try:
                page.goto(opened, wait_until="domcontentloaded", timeout=90_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=40_000)
                except Exception:
                    pass
                page.wait_for_timeout(1800)
                return bool(page.evaluate(needle_js))
            finally:
                try:
                    ctx.close()
                except Exception:
                    pass
                try:
                    browser.close()
                except Exception:
                    pass
    except Exception:
        return None


def _evaluate_stock_via_hibox(raw_url: str) -> SourceStockCheckResult:
    """Đọc tình trạng qua scrape Hibox (quy đổi URL nguồn như luồng nhập Excel)."""
    canonical_url = (normalize_product_import_url((raw_url or "").strip()) or (raw_url or "").strip()).strip()
    hibox_url, coercion_err = coerce_url_for_excel_batch_import(canonical_url, FETCH_TARGET_HIBOX)
    if coercion_err:
        return SourceStockCheckResult(
            status="error",
            error=f"Không quy đổi được sang link Hibox hợp lệ: {coercion_err}"[:1000],
        )
    coerced = (hibox_url or "").strip()
    canonical_url = hibox_canonical_scrape_url(coerced) if coerced else canonical_url
    try:
        _raw_row, product_data, warns = scrape_hibox_for_import(canonical_url)
        rr = dict(_raw_row) if isinstance(_raw_row, dict) else {}
        pd = dict(product_data) if isinstance(product_data, dict) else {}
        if hibox_scrape_signals_removed_or_not_found_offer(rr):
            return SourceStockCheckResult(
                status="out_of_stock",
                error=(
                    "Hibox: trang báo không tìm thấy sản theo mã / đã xóa khỏi Taobao (hoặc tương đương) — coi hết hàng nguồn."
                )[:1000],
            )
        title_like = rr.get("title")
        sku_like = rr.get("sku")
        pname = pd.get("name")
        basics = bool((title_like or "").strip() or (sku_like or "").strip() or (pname or "").strip())
        has_signal = basics or _hibox_row_shows_color_size_catalog(rr, pd)
        if has_signal:
            cart_probe = rr.get("hibox_dom_cart_cta")
            if cart_probe is False:
                return SourceStockCheckResult(
                    status="out_of_stock",
                    error=(
                        "Hibox: không thấy nút «САГСЛАХ» (thêm giỏ — khoanh đỏ) trên PDP — coi hết hàng nguồn."
                    ),
                )
            warn_txt = "; ".join(list(warns or [])[:6]).strip()
            return SourceStockCheckResult(status="in_stock", error=warn_txt or None)
        return SourceStockCheckResult(
            status="out_of_stock",
            error=(
                "Hibox không trả đủ dữ liệu PDP (thiếu tiêu đề/SKU và không có màu–size có nội dung)."
            ),
        )
    except ImportHiboxError as exc:
        fb_cart = _hibox_quick_cart_cta_via_playwright(canonical_url)
        if fb_cart is False:
            return SourceStockCheckResult(
                status="out_of_stock",
                error=(
                    "Hibox: không thấy nút «САГСЛАХ» (thêm giỏ) sau khi tải PDP — coi hết hàng. "
                    f"(scrape báo lỗi tạm: {str(exc)[:420]})"
                )[:1000],
            )
        return SourceStockCheckResult(status="error", error=str(exc)[:1000])
    except Exception as exc:
        logger.warning("hibox source stock evaluate failed: %s", exc)
        return SourceStockCheckResult(
            status="error",
            error=((str(exc) or "unexpected_error")[:920] + " — chưa kiểm tra được.")[:1000],
        )


def _datetime_is_recent(value: Optional[datetime], seconds: int) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value > _utcnow() - timedelta(seconds=seconds)


def product_stock_cache_is_stale(product: Product) -> bool:
    checked_at = product.source_stock_checked_at
    if checked_at is None:
        return True
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    return checked_at <= _utcnow() - timedelta(minutes=settings.SOURCE_STOCK_CHECK_STALE_MINUTES)


def enqueue_source_stock_check(product_id: int, *, reason: str = "manual", force: bool = False) -> bool:
    """Đưa sản phẩm vào queue in-process. Trả False nếu bị bỏ qua hoặc đã có trong queue."""
    if not getattr(settings, "SOURCE_STOCK_CHECK_ENABLED", True) and not force:
        return False

    with _queue_lock:
        if product_id in _queued_ids:
            return False
        _queued_ids.add(product_id)
        _queue.append(product_id)

    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product or not _link_eligible_for_hibox_stock_check(product.link_default or ""):
            with _queue_lock:
                _queued_ids.discard(product_id)
                try:
                    _queue.remove(product_id)
                except ValueError:
                    pass
            return False
        product.source_stock_status = "queued"
        product.source_stock_error = None
        product.source_stock_next_check_at = _utcnow()
        db.commit()
        logger.info("source stock check queued: product_id=%s reason=%s", product_id, reason)
        return True
    except Exception as exc:
        db.rollback()
        logger.warning("source stock enqueue failed: product_id=%s reason=%s error=%s", product_id, reason, exc)
        return False
    finally:
        db.close()


def enqueue_product_view_stock_check_if_needed(product: Product) -> bool:
    """Gọi khi khách mở PDP: chỉ enqueue nếu cache thiếu/cũ và không spam cùng một sản phẩm."""
    if not product or not _link_eligible_for_hibox_stock_check(product.link_default or ""):
        return False
    status = (product.source_stock_status or "").strip().lower()
    if status in {"queued", "checking"} and _datetime_is_recent(
        product.source_stock_next_check_at or product.source_stock_checked_at,
        settings.SOURCE_STOCK_CHECK_PAGEVIEW_MIN_INTERVAL_SECONDS,
    ):
        return False
    if not product_stock_cache_is_stale(product):
        return False
    return enqueue_source_stock_check(product.id, reason="product_view")


def _pop_queued_id() -> Optional[int]:
    with _queue_lock:
        if not _queue:
            return None
        product_id = _queue.popleft()
        _queued_ids.discard(product_id)
        return product_id


def _claim_due_product_id() -> Optional[int]:
    db = SessionLocal()
    try:
        now = _utcnow()
        product = _eligible_due_products_query(db).first()
        if not product or not _link_eligible_for_hibox_stock_check(product.link_default or ""):
            return None
        product.source_stock_status = "queued"
        product.source_stock_next_check_at = now
        db.commit()
        return product.id
    except Exception as exc:
        db.rollback()
        logger.warning("source stock claim due product failed: %s", exc)
        return None
    finally:
        db.close()


def check_product_source_stock(product_id: int) -> Optional[SourceStockCheckResult]:
    db = SessionLocal()
    progressed = False
    final_st: Optional[str] = None
    products_commit_ok = False
    products_commit_detail = "Chưa xác nhận commit bảng products."
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product or not _link_eligible_for_hibox_stock_check(product.link_default or ""):
            return None

        previous_status = (product.source_stock_status or "").strip().lower()
        product.source_stock_status = "checking"
        product.source_stock_error = None
        product.source_stock_next_check_at = _utcnow()
        db.commit()

        _worker_progress_mark_started(product_id)
        progressed = True

        result = _evaluate_stock_primary_cssbuy_with_hibox_fallback(product.link_default or "")
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            final_st = getattr(result, "status", None) or "error"
            products_commit_ok = False
            products_commit_detail = (
                "Không tìm thấy products sau khi scrape — không thể COMMIT kết quả lên dòng products."
            )
            return result

        now = _utcnow()
        product.source_stock_status = result.status
        product.source_stock_checked_at = now
        product.source_stock_error = result.error
        retry_minutes = (
            settings.SOURCE_STOCK_CHECK_ERROR_RETRY_MINUTES
            if result.status in {"error", "unknown", "blocked"}
            else settings.SOURCE_STOCK_CHECK_STALE_MINUTES
        )
        product.source_stock_next_check_at = now + timedelta(minutes=retry_minutes)
        if result.status == "out_of_stock":
            product.available = 0
        elif result.status == "in_stock" and (product.available or 0) <= 0 and previous_status == "out_of_stock":
            product.available = 500
        db.commit()
        if result.status in {"error", "unknown", "blocked"}:
            logger.warning(
                "source stock check issue: product_id=%s status=%s error=%s",
                product_id,
                result.status,
                result.error,
            )
        else:
            logger.info("source stock checked: product_id=%s status=%s", product_id, result.status)

        final_st = result.status
        products_commit_ok = True
        products_commit_detail = (
            f"Đã COMMIT products.id={product_id} status={result.status}; "
            "cập nhật source_stock_checked_at, next_check_at và (nếu có) available."
        )
        return result

    except Exception as exc:
        db.rollback()
        logger.exception("source stock check failed: product_id=%s", product_id)
        committed_fallback = False
        try:
            product = db.query(Product).filter(Product.id == product_id).first()
            if product:
                now = _utcnow()
                product.source_stock_status = "error"
                product.source_stock_checked_at = now
                product.source_stock_error = str(exc)[:1000]
                product.source_stock_next_check_at = now + timedelta(minutes=settings.SOURCE_STOCK_CHECK_ERROR_RETRY_MINUTES)
                db.commit()
                committed_fallback = True
        except Exception:
            db.rollback()
        final_st = final_st or "error"
        if committed_fallback:
            products_commit_ok = True
            products_commit_detail = (
                f"Đã COMMIT products.id={product_id} status=error sau exception (ghi source_stock_error)."
            )
        else:
            products_commit_ok = False
            products_commit_detail = f"Không COMMIT được bảng products sau lỗi: {(str(exc) or 'unknown')[:800]}"
        return SourceStockCheckResult(status="error", error=str(exc)[:1000])
    finally:
        if progressed:
            _worker_progress_mark_finished(
                product_id,
                final_st or "error",
                products_commit_ok=products_commit_ok,
                products_commit_detail=products_commit_detail,
            )
        db.close()


def _worker_loop() -> None:
    logger.info(
        "source stock checker started: interval=%ss stale=%sm (cssbuy first; hibox only when css blocked/error)",
        settings.SOURCE_STOCK_CHECK_INTERVAL_SECONDS,
        settings.SOURCE_STOCK_CHECK_STALE_MINUTES,
    )
    idle_sleep = max(1, min(15, int(settings.SOURCE_STOCK_CHECK_INTERVAL_SECONDS)))
    while True:
        try:
            paused, _ = worker_pause_db_snapshot(force_refresh=False)
        except Exception:
            paused = False
        if paused:
            time.sleep(idle_sleep)
            continue
        product_id = _pop_queued_id() or _claim_due_product_id()
        if product_id is None:
            time.sleep(idle_sleep)
            continue
        check_product_source_stock(product_id)
        time.sleep(settings.SOURCE_STOCK_CHECK_INTERVAL_SECONDS)


def start_source_stock_checker_daemon_if_enabled() -> None:
    if not getattr(settings, "SOURCE_STOCK_CHECK_ENABLED", True):
        return
    global _worker_started, _worker_thread_ref
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True
        thread = threading.Thread(target=_worker_loop, name="source-stock-checker", daemon=True)
        _worker_thread_ref = thread
        thread.start()
