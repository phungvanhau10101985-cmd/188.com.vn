"""
Hàng đợi import link từ trang HTML listing (admin): lưu snapshot JSON trong DB.

Trong mỗi đợt (queue_token), xử lý tuần tự từng link; có tạm dừng / tiếp tục / dừng hẳn giữa các job
(không cắt giữa chừng một scrape đang chạy). Mỗi đợt có một luồng ``threading.Thread`` riêng —
nhiều đợt có thể chạy song song, độc lập (không khóa chéo giữa các đợt).

Token bị «xóa khỏi DB» được ghi vào bảng revocation để worker không tái tạo snapshot.
File legacy `static/uploads/listing_import_queues/*.json` vẫn được đọc và tự migrate sang DB khi gặp.
"""

from __future__ import annotations

import json
import logging
import math
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _queues_dir() -> Path:
    root = Path(__file__).resolve().parents[1] / "static" / "uploads" / "listing_import_queues"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _token_ok(token: str) -> bool:
    t = (token or "").strip().lower()
    return bool(re.fullmatch(r"[a-f0-9]{32,64}", t))


def _queue_path(token: str) -> Path:
    return _queues_dir() / f"{token}.json"


def _is_revoked(token: str) -> bool:
    try:
        from app.db.session import SessionLocal
        from app.models.listing_import_queue_snapshot import ListingImportQueueRevocation

        db = SessionLocal()
        try:
            hit = (
                db.query(ListingImportQueueRevocation)
                .filter(ListingImportQueueRevocation.queue_token == token)
                .first()
            )
            return hit is not None
        finally:
            db.close()
    except Exception as exc:
        logger.warning("listing_import_queue revocation check failed: %s", exc)
        return False


def _db_load_snapshot_payload(token: str) -> Optional[Dict[str, Any]]:
    try:
        from app.db.session import SessionLocal
        from app.models.listing_import_queue_snapshot import ListingImportQueueSnapshot

        db = SessionLocal()
        try:
            row = db.query(ListingImportQueueSnapshot).filter_by(queue_token=token).first()
            if not row or row.payload_json is None:
                return None
            pl = row.payload_json
            return dict(pl) if isinstance(pl, dict) else json.loads(pl)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("listing_import_queue DB load failed: %s", exc)
        return None


def _db_persist_snapshot(token: str, payload: Dict[str, Any]) -> bool:
    """True nếu đã commit DB (hoặc không cần vì revoked). False nếu lỗi DB."""
    if _is_revoked(token):
        return True
    try:
        from app.db.session import SessionLocal
        from app.models.listing_import_queue_snapshot import ListingImportQueueSnapshot

        now = datetime.now(timezone.utc)
        body = dict(payload)
        body["updated_at"] = now.isoformat()

        db = SessionLocal()
        try:
            row = db.query(ListingImportQueueSnapshot).filter_by(queue_token=token).first()
            if row is None:
                db.add(
                    ListingImportQueueSnapshot(
                        queue_token=token,
                        payload_json=body,
                        created_by=body.get("created_by"),
                    )
                )
            else:
                row.payload_json = body
                row.updated_at = now
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as exc:
        logger.warning("listing_import_queue DB save failed: %s", exc)
        return False


def _unlink_legacy_file(token: str) -> None:
    p = _queue_path(token)
    if p.is_file():
        try:
            p.unlink()
        except OSError as exc:
            logger.warning("listing_import_queue unlink legacy file %s: %s", p, exc)


def load_queue(token: str) -> Optional[Dict[str, Any]]:
    if not _token_ok(token):
        return None
    if _is_revoked(token):
        return None
    data = _db_load_snapshot_payload(token)
    if data:
        return data
    p = _queue_path(token)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("listing_import_queue legacy load failed: %s", exc)
        return None
    if isinstance(data, dict) and data.get("queue_token") == token:
        if _db_persist_snapshot(token, data):
            _unlink_legacy_file(token)
    return data if isinstance(data, dict) else None


def save_queue(data: Dict[str, Any]) -> None:
    token = data.get("queue_token") or ""
    if not _token_ok(token):
        return
    if _is_revoked(token):
        logger.info("listing_import_queue save skipped (revoked token %s…)", token[:12])
        return
    data = dict(data)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    if not _db_persist_snapshot(token, data):
        _atomic_write_json(_queue_path(token), data)
        return
    _unlink_legacy_file(token)


_lock_registry: Dict[str, threading.Lock] = {}
_worker_registry: Dict[str, threading.Thread] = {}


def _lock_for(token: str) -> threading.Lock:
    with threading.Lock():
        if token not in _lock_registry:
            _lock_registry[token] = threading.Lock()
        return _lock_registry[token]


def _atomic_write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def new_queue_skeleton(admin_id: Optional[int] = None) -> Dict[str, Any]:
    token = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    return {
        "queue_token": token,
        "created_at": now,
        "updated_at": now,
        "created_by": admin_id,
        "run_status": "idle",
        "pause_requested": False,
        "stop_requested": False,
        "current_item_id": None,
        "worker_error": None,
        "items": [],
    }


def _worker_is_alive(token: str) -> bool:
    th = _worker_registry.get(token)
    return th is not None and th.is_alive()


def _reconcile_queue_after_worker_loss(q: Dict[str, Any], token: str) -> bool:
    """
    Sau restart/deploy: thread worker mất nhưng snapshot vẫn ``running`` / item ``running``.
    Đưa link kẹt về ``pending`` và ``run_status`` → ``paused`` để admin bấm Tiếp tục.
    """
    if _worker_is_alive(token):
        return False
    if q.get("run_status") == "stopped" or q.get("stop_requested"):
        return False

    items: List[Dict[str, Any]] = list(q.get("items") or [])
    changed = False
    stale_note = "Link dừng giữa chừng (restart server) — chờ chạy lại."
    for it in items:
        if it.get("state") != "running":
            continue
        it["state"] = "pending"
        prev = (it.get("message") or "").strip()
        if prev and "restart server" not in prev.casefold():
            it["message"] = f"{prev} · {stale_note}"
        else:
            it["message"] = stale_note
        changed = True

    if q.get("current_item_id"):
        q["current_item_id"] = None
        changed = True

    has_pending = any(it.get("state") == "pending" for it in items)
    has_running = any(it.get("state") == "running" for it in items)
    rs = str(q.get("run_status") or "")
    if has_pending and not has_running and rs in {"running", "pausing"}:
        q["run_status"] = "paused"
        if not (q.get("worker_error") or "").strip():
            q["worker_error"] = "Worker dừng (restart server). Bấm «Tiếp tục» trên admin."
        changed = True

    return changed


def reconcile_all_queues_on_startup() -> None:
    """Gọi khi khởi động API — dọn snapshot listing queue bị kẹt sau deploy."""
    try:
        from app.db.session import SessionLocal
        from app.models.listing_import_queue_snapshot import ListingImportQueueSnapshot

        db = SessionLocal()
        try:
            rows = db.query(ListingImportQueueSnapshot.queue_token).all()
            for (tok,) in rows:
                if not tok or _is_revoked(tok):
                    continue
                lock = _lock_for(tok)
                with lock:
                    q = load_queue(tok)
                    if not q:
                        continue
                    if _reconcile_queue_after_worker_loss(q, tok):
                        save_queue(q)
                        logger.info("listing queue %s… reconciled on startup", tok[:12])
        finally:
            db.close()
    except Exception as exc:
        logger.warning("listing_import_queue startup reconcile failed: %s", exc)


def _execute_one_import(
    url: str,
    source: Optional[str],
    admin_id: Optional[int],
    overlay: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Chạy một job import đồng bộ (như POST /jobs nhưng không BackgroundTasks)."""
    from app.crud import product_import_draft as draft_crud
    from app.db.session import SessionLocal
    from app.api.endpoints.import_1688 import (  # noqa: PLC0415
        _infer_import_source_for_url,
        _run_import_1688_job,
    )
    from app.services.import_hibox_scraper import normalize_product_import_url

    source_url = normalize_product_import_url((url or "").strip())
    if len(source_url) < 10:
        return {"ok": False, "error": "URL quá ngắn sau khi chuẩn hoá."}
    try:
        ext_id, src = _infer_import_source_for_url(source_url, source)
    except ValueError:
        return {"ok": False, "error": "Link không nhận dạng được Hibox/taobao1688.kz/Vipomall."}

    job_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        draft = draft_crud.create_draft(
            db,
            job_id=job_id,
            source_url=source_url,
            source_offer_id=ext_id,
            created_by=admin_id,
            source=src,
        )
        draft_id = draft.id
        db.commit()
    except Exception as exc:
        db.rollback()
        return {"ok": False, "error": str(exc)}
    finally:
        db.close()

    _run_import_1688_job(job_id, False)

    db2 = SessionLocal()
    try:
        d = draft_crud.get_by_job_id(db2, job_id)
        if not d:
            return {"ok": False, "job_id": job_id, "error": "Không đọc lại draft sau import."}
        from app.services.import_link_excel_batch import merge_import_excel_overlay_into_product_data

        overlay_keys = (
            "chinese_name",
            "shop_name_chinese",
            "price",
            "pro_lower_price",
            "pro_high_price",
        )
        clean_overlay: Dict[str, Any] = {}
        for k in overlay_keys:
            v = (overlay or {}).get(k)
            if v is None:
                continue
            if k == "price":
                try:
                    num = float(v)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(num) or num <= 0:
                    continue
                clean_overlay[k] = num
            elif str(v).strip():
                clean_overlay[k] = str(v).strip()
        if clean_overlay:
            pdata = dict(d.product_data or {})
            merge_import_excel_overlay_into_product_data(pdata, clean_overlay)
            d.product_data = pdata
            db2.add(d)
            db2.commit()
        return {
            "ok": d.status != "error",
            "job_id": job_id,
            "draft_id": d.id,
            "draft_status": d.status,
            "message": d.message or "",
            "errors": list(d.errors or []) if d.errors else [],
        }
    finally:
        db2.close()


def _worker_loop(token: str) -> None:
    lock = _lock_for(token)
    while True:
        with lock:
            q = load_queue(token)
            if not q:
                return
            if q.get("stop_requested"):
                q["run_status"] = "stopped"
                q["current_item_id"] = None
                save_queue(q)
                logger.info("listing queue %s… stopped", token[:12])
                return
            if q.get("pause_requested"):
                q["run_status"] = "paused"
                q["current_item_id"] = None
                save_queue(q)
                logger.info("listing queue %s… paused", token[:12])
                return

            items: List[Dict[str, Any]] = q.get("items") or []
            pending = next((it for it in items if it.get("state") == "pending"), None)
            if not pending:
                q["run_status"] = "completed"
                q["current_item_id"] = None
                save_queue(q)
                logger.info("listing queue %s… completed", token[:12])
                return

            pending["state"] = "running"
            q["run_status"] = "running"
            q["current_item_id"] = pending.get("id")
            q["worker_error"] = None
            save_queue(q)
            item_id = pending.get("id")
            url = pending.get("url") or ""
            source = pending.get("source")
            label = pending.get("label") or ""
            overlay = {
                k: pending.get(k)
                for k in (
                    "chinese_name",
                    "shop_name_chinese",
                    "price",
                    "pro_lower_price",
                    "pro_high_price",
                )
                if pending.get(k) is not None
            }

        try:
            out = _execute_one_import(url, source, q.get("created_by"), overlay)
        except Exception as exc:
            logger.exception("listing queue item failed")
            out = {"ok": False, "error": str(exc)}

        with lock:
            q = load_queue(token)
            if not q:
                return
            items = q.get("items") or []
            target = next((it for it in items if it.get("id") == item_id), None)
            if target:
                if out.get("ok"):
                    target["state"] = "done"
                    target["job_id"] = out.get("job_id")
                    target["draft_id"] = out.get("draft_id")
                    target["message"] = out.get("message") or "OK"
                    target["finished_at"] = datetime.now(timezone.utc).isoformat()
                else:
                    target["state"] = "error"
                    target["message"] = out.get("error") or out.get("message") or "Lỗi"
                    target["job_id"] = out.get("job_id")
                    target["draft_id"] = out.get("draft_id")
                    target["finished_at"] = datetime.now(timezone.utc).isoformat()
            q["current_item_id"] = None
            save_queue(q)

        with lock:
            q = load_queue(token)
            if q and q.get("stop_requested"):
                q["run_status"] = "stopped"
                save_queue(q)
                return
            if q and q.get("pause_requested"):
                q["run_status"] = "paused"
                save_queue(q)
                return


def _ensure_worker_started(token: str) -> bool:
    if not _token_ok(token):
        return False
    t = _worker_registry.get(token)
    if t is not None and t.is_alive():
        return True

    def runner() -> None:
        try:
            _worker_loop(token)
        finally:
            _worker_registry.pop(token, None)

    th = threading.Thread(
        target=runner,
        name=f"listing-import-queue-{token[:12]}",
        daemon=True,
    )
    _worker_registry[token] = th
    th.start()
    return True


def enqueue(
    queue_token: Optional[str],
    tasks: List[Dict[str, Any]],
    admin_id: Optional[int],
) -> Tuple[str, int, str]:
    """
    Ghi thêm tasks; tạo queue mới nếu không có token hoặc queue cũ đã stopped.

    Mỗi ``queue_token`` có một worker ``threading.Thread`` riêng (``_ensure_worker_started``).
    Nhiều đợt có thể chạy song song, độc lập — không có khóa toàn cục giữa các đợt.

    tasks: [{url, source: hibox|vipomall, label?: str}]
    """
    if not tasks:
        raise ValueError("Không có link nào để thêm.")

    token: Optional[str] = None
    if queue_token and _token_ok(queue_token):
        ex = load_queue(queue_token)
        if ex and ex.get("run_status") != "stopped" and not ex.get("stop_requested"):
            token = queue_token

    added = 0
    msg = ""
    while True:
        pending_sk: Optional[Dict[str, Any]] = None
        if token is None:
            pending_sk = new_queue_skeleton(admin_id)
            token = pending_sk["queue_token"]

        lock = _lock_for(token)
        with lock:
            q = load_queue(token)
            if not q:
                if pending_sk is None:
                    pending_sk = new_queue_skeleton(admin_id)
                    token = pending_sk["queue_token"]
                    continue
                q = pending_sk

            if q.get("run_status") == "stopped" or q.get("stop_requested"):
                token = None
                continue

            added = 0
            for raw in tasks:
                url = (raw.get("url") or "").strip()
                src = (raw.get("source") or "hibox").strip().lower()
                if src in {"vipo", "vipomail", "vipo_mall", "vipo-mall"}:
                    src = "vipomall"
                if src not in {"hibox", "vipomall"}:
                    src = "hibox"
                label = (raw.get("label") or "").strip() or None
                if len(url) < 10:
                    continue
                chinese_name = str(raw.get("chinese_name") or "").strip() or None
                shop_name_chinese = str(raw.get("shop_name_chinese") or "").strip() or None
                price_raw = raw.get("price")
                price: Optional[float] = None
                if price_raw is not None:
                    try:
                        p = float(price_raw)
                        if math.isfinite(p) and p > 0:
                            price = p
                    except (TypeError, ValueError):
                        pass
                pro_lower_price = str(raw.get("pro_lower_price") or "").strip() or None
                pro_high_price = str(raw.get("pro_high_price") or "").strip() or None
                q["items"].append(
                    {
                        "id": uuid.uuid4().hex,
                        "url": url,
                        "source": src,
                        "label": label,
                        "chinese_name": chinese_name,
                        "shop_name_chinese": shop_name_chinese,
                        "price": price,
                        "pro_lower_price": pro_lower_price,
                        "pro_high_price": pro_high_price,
                        "state": "pending",
                        "job_id": None,
                        "draft_id": None,
                        "message": None,
                        "finished_at": None,
                    }
                )
                added += 1

            if added == 0:
                raise ValueError("Không có link hợp lệ (URL quá ngắn).")

            save_queue(q)
            msg = f"Đã thêm {added} link vào hàng đợi."
            final_token = token
            break

    try:
        resume(final_token, admin_id)
    except ValueError as exc:
        logger.warning("listing enqueue resume skipped: %s", exc)

    return final_token, added, msg


def pause(token: str, admin_id: Optional[int]) -> Dict[str, Any]:
    if not _token_ok(token):
        raise ValueError("queue_token không hợp lệ.")
    lock = _lock_for(token)
    with lock:
        q = load_queue(token)
        if not q:
            raise ValueError("Không tìm thấy hàng đợi.")
        q["pause_requested"] = True
        save_queue(q)
    return {"queue_token": token, "run_status": "pausing", "message": "Đã yêu cầu tạm dừng sau job hiện tại."}


def resume(token: str, admin_id: Optional[int]) -> Dict[str, Any]:
    if not _token_ok(token):
        raise ValueError("queue_token không hợp lệ.")
    lock = _lock_for(token)
    with lock:
        q = load_queue(token)
        if not q:
            raise ValueError("Không tìm thấy hàng đợi.")
        if q.get("run_status") == "stopped" or q.get("stop_requested"):
            raise ValueError("Hàng đợi đã dừng hẳn — không thể chạy lại. Hãy thêm link để tạo hàng đợi mới.")
        _reconcile_queue_after_worker_loss(q, token)
        q["pause_requested"] = False
        q["worker_error"] = None
        has_pending = any(it.get("state") == "pending" for it in (q.get("items") or []))
        if has_pending and q.get("run_status") in {"paused", "idle", "completed", "running", "pausing"}:
            q["run_status"] = "running"
        save_queue(q)

    _ensure_worker_started(token)
    return {"queue_token": token, "message": "Đã tiếp tục / khởi chạy worker."}


def stop_permanent(token: str, admin_id: Optional[int]) -> Dict[str, Any]:
    if not _token_ok(token):
        raise ValueError("queue_token không hợp lệ.")
    lock = _lock_for(token)
    with lock:
        q = load_queue(token)
        if not q:
            raise ValueError("Không tìm thấy hàng đợi.")
        q["stop_requested"] = True
        q["pause_requested"] = False
        if q.get("run_status") in {"idle", "paused", "completed"}:
            q["run_status"] = "stopped"
            q["current_item_id"] = None
        save_queue(q)
    return {"queue_token": token, "message": "Đã yêu cầu dừng hẳn sau job hiện tại — không thể resume."}


def get_status_dict(token: str) -> Dict[str, Any]:
    if not _token_ok(token):
        raise ValueError("queue_token không hợp lệ.")
    lock = _lock_for(token)
    with lock:
        q = load_queue(token)
        if not q:
            raise ValueError("Không tìm thấy hàng đợi.")
        if _reconcile_queue_after_worker_loss(q, token):
            save_queue(q)
    q = load_queue(token)
    if not q:
        raise ValueError("Không tìm thấy hàng đợi.")
    items = q.get("items") or []
    total = len(items)
    done = sum(1 for it in items if it.get("state") == "done")
    err = sum(1 for it in items if it.get("state") == "error")
    pending = sum(1 for it in items if it.get("state") == "pending")
    running = sum(1 for it in items if it.get("state") == "running")

    worker_alive = _worker_is_alive(token)
    run_status = q.get("run_status")
    has_pending = pending > 0

    return {
        "queue_token": q.get("queue_token"),
        "created_at": q.get("created_at"),
        "updated_at": q.get("updated_at"),
        "run_status": run_status,
        "pause_requested": bool(q.get("pause_requested")),
        "stop_requested": bool(q.get("stop_requested")),
        "worker_alive": worker_alive,
        "worker_error": q.get("worker_error"),
        "current_item_id": q.get("current_item_id"),
        "counts": {
            "total": total,
            "done": done,
            "error": err,
            "pending": pending,
            "running": running,
        },
        "items": items,
        "can_resume": bool(
            not q.get("stop_requested")
            and has_pending
            and run_status != "stopped"
            and (
                run_status == "paused"
                or (not worker_alive and run_status in {"running", "pausing", "idle"})
            )
        ),
        "can_pause": run_status == "running"
        and worker_alive
        and not q.get("pause_requested")
        and not q.get("stop_requested"),
        "can_stop": not q.get("stop_requested") and run_status != "stopped",
    }


def _counts_from_items(items: List[Dict[str, Any]]) -> Dict[str, int]:
    total = len(items)
    done = sum(1 for it in items if it.get("state") == "done")
    err = sum(1 for it in items if it.get("state") == "error")
    pending = sum(1 for it in items if it.get("state") == "pending")
    running = sum(1 for it in items if it.get("state") == "running")
    return {"total": total, "done": done, "error": err, "pending": pending, "running": running}


def list_saved_queue_summaries(*, limit: int = 50, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    """Đợt có snapshot trong DB, `updated_at` mới nhất trước."""
    lim = max(1, min(int(limit), 200))
    off = max(0, int(offset))
    try:
        from app.db.session import SessionLocal
        from app.models.listing_import_queue_snapshot import ListingImportQueueSnapshot

        db = SessionLocal()
        try:
            qry = db.query(ListingImportQueueSnapshot)
            total = int(qry.count())
            rows = (
                qry.order_by(ListingImportQueueSnapshot.updated_at.desc())
                .offset(off)
                .limit(lim)
                .all()
            )
            out: List[Dict[str, Any]] = []
            for row in rows:
                pl = row.payload_json if isinstance(row.payload_json, dict) else {}
                items_raw = pl.get("items") or []
                items = items_raw if isinstance(items_raw, list) else []
                item_dicts = [x for x in items if isinstance(x, dict)]
                counts = _counts_from_items(item_dicts)
                ua = row.updated_at.isoformat() if getattr(row, "updated_at", None) else pl.get("updated_at")
                ca = row.created_at.isoformat() if getattr(row, "created_at", None) else pl.get("created_at")
                tok = row.queue_token
                alive = _worker_is_alive(tok)
                out.append(
                    {
                        "queue_token": tok,
                        "created_at": ca,
                        "updated_at": ua,
                        "run_status": str(pl.get("run_status") or ""),
                        "pause_requested": bool(pl.get("pause_requested")),
                        "stop_requested": bool(pl.get("stop_requested")),
                        "counts": counts,
                        "worker_alive": alive,
                    }
                )
            return out, total
        finally:
            db.close()
    except Exception as exc:
        logger.warning("listing_import_queue list_saved_queue_summaries failed: %s", exc)
        return [], 0


def delete_saved_queue(token: str, admin_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Thu hồi token (chặn worker/ghi lại), xóa snapshot và file legacy JSON.
    Không xóa product_import_drafts đã tạo.
    """
    del admin_id  # reserved cho audit / RBAC mở rộng
    if not _token_ok(token):
        raise ValueError("queue_token không hợp lệ.")
    lock = _lock_for(token)
    with lock:
        try:
            from app.db.session import SessionLocal
            from app.models.listing_import_queue_snapshot import (
                ListingImportQueueRevocation,
                ListingImportQueueSnapshot,
            )

            db = SessionLocal()
            try:
                if db.query(ListingImportQueueRevocation).filter_by(queue_token=token).first() is None:
                    db.add(ListingImportQueueRevocation(queue_token=token))
                db.query(ListingImportQueueSnapshot).filter_by(queue_token=token).delete()
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        except Exception as exc:
            logger.warning("listing_import_queue delete_saved_queue failed: %s", exc)
            raise ValueError("Không xóa được hàng đợi trên DB.") from exc
        _unlink_legacy_file(token)
    return {"queue_token": token, "deleted": True}


def collect_terminal_draft_ids_from_queue(token: str) -> List[int]:
    """
    Theo thứ tự item trong snapshot: các draft_id của dòng đã kết thúc (done | error),
    bỏ trùng lặp giữ nguyên thứ tự lần đầu gặp.
    """
    if not _token_ok(token):
        raise ValueError("queue_token không hợp lệ.")
    q = load_queue(token)
    if not q:
        raise ValueError("Không tìm thấy hàng đợi.")
    out: List[int] = []
    seen: set[int] = set()
    for it in q.get("items") or []:
        if it.get("state") not in {"done", "error"}:
            continue
        raw = it.get("draft_id")
        if raw is None:
            continue
        try:
            did = int(raw)
        except (TypeError, ValueError):
            continue
        if did in seen:
            continue
        seen.add(did)
        out.append(did)
    return out


def export_snapshot_csv(token: str, *, finished_only: bool = False) -> str:
    """
    CSV snapshot hàng đợi.
    finished_only=True: chỉ các dòng đã kết thúc xử lý (state done | error) — dữ liệu kết quả.
    """
    st = get_status_dict(token)
    items: List[Dict[str, Any]] = list(st.get("items") or [])
    if finished_only:
        items = [it for it in items if it.get("state") in {"done", "error"}]
    lines = ["label,url,source,state,job_id,draft_id,finished_at,message"]
    for it in items:
        label = (it.get("label") or "").replace('"', '""')
        url = (it.get("url") or "").replace('"', '""')
        source = it.get("source") or ""
        state = it.get("state") or ""
        job_id = it.get("job_id") or ""
        draft_id = it.get("draft_id") if it.get("draft_id") is not None else ""
        finished_at = (it.get("finished_at") or "").replace('"', '""')
        msg = (str(it.get("message") or "")).replace('"', '""')
        lines.append(
            f'"{label}","{url}","{source}","{state}","{job_id}","{draft_id}","{finished_at}","{msg}"'
        )
    return "\r\n".join(lines) + "\r\n"
