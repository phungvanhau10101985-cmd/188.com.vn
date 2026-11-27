"""Nhận diện hàng giả bằng một file batch Gemini 3.8 Flash.

OCR Vision chỉ để xóa chữ. Logo đọc ở đây: một file JSONL, một lần tạo batch.
Kết quả về sau (trong vòng 24 giờ) rồi mới ghi cờ, mail và loại khỏi feed.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

_MODEL = "gemini-3.8-flash"
# Một JPEG luôn 1120 token. 3 ảnh: logo còn đủ lớn, vẫn thấy ảnh chính và 2 ảnh kế.
_MAX_IMAGES = 3
_BATCH_CHUNK = 400
_MAX_INFLIGHT = 40
_SWEEP_LIMIT = 2000
_POLL_SECONDS = 180
_ALERT_MODEL = "gemini-3.8-flash"

_PROMPT = (
    "Ảnh là một hoặc nhiều ảnh sản phẩm xếp dọc.\n"
    "Chỉ tìm logo thương hiệu nổi tiếng, kể cả logo bị vẽ méo và không có chữ tên hãng.\n"
    "Bỏ qua chữ mô tả, bảng size và hướng dẫn giặt.\n"
    'Trả JSON duy nhất {"brands":["Nike"]}. Không có logo thì {"brands":[]}.\n'
    "Không giải thích."
)


class _ProcessLock:
    """Một batch tại một thời điểm, kể cả khi API và worker cùng mở file trạng thái."""

    def __init__(self) -> None:
        self._thread = threading.Lock()
        self._fh = None

    def __enter__(self) -> "_ProcessLock":
        self._thread.acquire()
        try:
            path = _state_path().with_suffix(".lock")
            fh = open(path, "a+b")
            if os.name == "nt":
                import msvcrt

                fh.seek(0, os.SEEK_END)
                if fh.tell() == 0:
                    fh.write(b"\0")
                    fh.flush()
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            self._fh = fh
        except Exception:
            self._thread.release()
            raise
        return self

    def __exit__(self, *_args: object) -> None:
        fh = self._fh
        self._fh = None
        try:
            if fh is not None:
                if os.name == "nt":
                    import msvcrt

                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                fh.close()
        finally:
            self._thread.release()


_LOCK = _ProcessLock()


def _state_path() -> Path:
    root = Path(settings.IMAGE_LOCALIZATION_RUNTIME_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root / "counterfeit_gemini_batch.json"


def _load_state() -> Dict[str, Any]:
    path = _state_path()
    if not path.is_file():
        return {"pending": None, "queued_product_ids": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"pending": None, "queued_product_ids": []}
    if not isinstance(data, dict):
        return {"pending": None, "queued_product_ids": []}
    queued = data.get("queued_product_ids")
    data["queued_product_ids"] = [str(x) for x in queued] if isinstance(queued, list) else []
    if not isinstance(data.get("pending"), dict):
        data["pending"] = None
    inflight = data.get("inflight")
    data["inflight"] = [item for item in inflight if isinstance(item, dict)] if isinstance(inflight, list) else []
    return data


def _save_state(state: Dict[str, Any]) -> None:
    path = _state_path()
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def _named_inflight(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    jobs = [item for item in (state.get("inflight") or []) if isinstance(item, dict) and item.get("name")]
    pending = state.get("pending")
    if isinstance(pending, dict) and pending.get("name") and not any(item.get("name") == pending.get("name") for item in jobs):
        jobs.append(pending)
    return jobs


def _is_building(state: Dict[str, Any]) -> bool:
    pending = state.get("pending")
    return isinstance(pending, dict) and pending.get("status") == "building" and not pending.get("name")


def _can_submit(state: Dict[str, Any]) -> bool:
    return not _is_building(state) and len(_named_inflight(state)) < _MAX_INFLIGHT


def _api_key() -> str:
    return (getattr(settings, "GEMINI_API_KEY", "") or "").strip()


def parse_brand_json(text: str) -> Optional[List[str]]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.removeprefix("json").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    brands = data.get("brands")
    if brands is None and data.get("brand"):
        brands = [data.get("brand")]
    if not isinstance(brands, list):
        return None
    return [str(item).strip() for item in brands if str(item).strip()]


def _response_text(line: Dict[str, Any]) -> str:
    response = line.get("response") or {}
    candidates = response.get("candidates") or []
    if not candidates:
        return ""
    parts = ((candidates[0] or {}).get("content") or {}).get("parts") or []
    return "\n".join(str(part.get("text") or "") for part in parts if isinstance(part, dict))


def enqueue_products(product_ids: Iterable[str], *, resume_job_id: str = "") -> None:
    """Xếp sản phẩm để kiểm hàng giả trước khi bản địa hóa. Một file nếu chưa có batch."""
    ids = [str(item).strip() for item in product_ids if str(item).strip()]
    if not ids and not resume_job_id:
        return
    with _LOCK:
        state = _load_state()
        queued = list(state.get("queued_product_ids") or [])
        seen = set(queued)
        for product_id in ids:
            if product_id not in seen:
                queued.append(product_id)
                seen.add(product_id)
        state["queued_product_ids"] = queued
        if resume_job_id:
            waiting = dict(state.get("waiting_by_job") or {})
            current = [str(item) for item in (waiting.get(resume_job_id) or [])]
            for product_id in ids:
                if product_id not in current:
                    current.append(product_id)
            waiting[resume_job_id] = current
            state["waiting_by_job"] = waiting
        _save_state(state)
        should_submit = _can_submit(state) and bool(queued)
    if should_submit:
        threading.Thread(target=submit_queued_batch, daemon=True).start()


def _notify_batch_down(detail: str) -> None:
    try:
        from app.services.ai_run_alert import notify_ai_down

        notify_ai_down(_ALERT_MODEL, detail)
    except Exception:
        logger.exception("counterfeit gemini batch: không gửi được email admin")


def _mark_batch_ok() -> None:
    try:
        from app.services.ai_run_alert import mark_ai_ok

        mark_ai_ok(_ALERT_MODEL)
    except Exception:
        pass


def sweep_unchecked_products() -> None:
    """Xếp sản phẩm đang bán nhưng chưa kiểm tra. Poller gọi khi không có batch đang chạy."""
    with _LOCK:
        state = _load_state()
        queued = [str(item) for item in (state.get("queued_product_ids") or []) if str(item).strip()]
        busy = set(queued)
        for job in _named_inflight(state):
            for item in job.get("sent_ids") or job.get("product_ids") or []:
                busy.add(str(item))
        pending = state.get("pending")
        if isinstance(pending, dict):
            for item in pending.get("product_ids") or []:
                busy.add(str(item))
    room = _SWEEP_LIMIT - len(queued)
    if room <= 0:
        return
    from sqlalchemy import String, cast, func

    from app.db.session import SessionLocal
    from app.models.product import Product
    from app.services.consult_image_text import COUNTERFEIT_IMAGE_KEY

    db = SessionLocal()
    try:
        flag = Product.consult_image_text[COUNTERFEIT_IMAGE_KEY]["checked"]
        checked_text = flag.astext if hasattr(flag, "astext") else cast(flag, String)
        rows = (
            db.query(Product.product_id)
            .filter(Product.is_active.is_(True))
            .filter(Product.main_image.isnot(None))
            .filter(func.trim(Product.main_image) != "")
            .filter(func.coalesce(checked_text, "") != "true")
            .order_by(Product.id.asc())
            .limit(room + min(len(busy), 20000))
            .all()
        )
    except Exception:
        logger.exception("counterfeit sweep")
        return
    finally:
        db.close()
    ids = []
    for row in rows:
        product_id = str(row[0]) if row and row[0] else ""
        if not product_id or product_id in busy:
            continue
        ids.append(product_id)
        if len(ids) >= room:
            break
    if ids:
        enqueue_products(ids)


def _stop_waiting_jobs(detail: str) -> None:
    """Gemini không chạy: job bản địa hóa đang chờ kiểm phải dừng, không gọi tiếp."""
    from app.crud import image_localization_job as job_crud
    from app.db.session import SessionLocal

    with _LOCK:
        waiting = list((_load_state().get("waiting_by_job") or {}).keys())
    if not waiting:
        return
    db = SessionLocal()
    try:
        for job_id in waiting:
            row = job_crud.get_job(db, str(job_id))
            if row is None:
                continue
            status = (row.status or "").strip().lower()
            if status in {"cancelled", "done", "error"} or (row.phase or "") != "counterfeit_check":
                continue
            job_crud.patch_job(
                db,
                str(job_id),
                {
                    "status": "error",
                    "phase": "error",
                    "message": f"Dừng job: Gemini không chạy. {str(detail)[:700]}",
                    "finished_at": datetime.now(timezone.utc),
                },
            )
    finally:
        db.close()
    with _LOCK:
        state = _load_state()
        state["waiting_by_job"] = {}
        _save_state(state)


def submit_queued_batch() -> None:
    from app.services.ai_run_alert import AiApiStopped, ai_is_paused

    if ai_is_paused("gemini"):
        logger.warning("counterfeit batch dừng: Gemini chưa chạy lại")
        _stop_waiting_jobs("Gemini chưa chạy lại")
        return
    with _LOCK:
        state = _load_state()
        if not _can_submit(state):
            return
        queued = [str(item) for item in (state.get("queued_product_ids") or []) if str(item).strip()]
        if not queued:
            return
        product_ids = queued[:_BATCH_CHUNK]
        state["queued_product_ids"] = queued[_BATCH_CHUNK:]
        state["pending"] = {
            "status": "building",
            "product_ids": product_ids,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_state(state)
    try:
        name, sent_ids = _upload_and_create(product_ids)
    except Exception as exc:
        logger.exception("counterfeit gemini batch: gửi file lỗi")
        if isinstance(exc, AiApiStopped):
            _stop_waiting_jobs(str(exc))
        else:
            _notify_batch_down(f"Không gửi được batch kiểm hàng giả: {exc}")
        with _LOCK:
            state = _load_state()
            pending = state.get("pending") or {}
            failed_ids = list(pending.get("product_ids") or product_ids)
            queued = list(state.get("queued_product_ids") or [])
            state["queued_product_ids"] = failed_ids + [item for item in queued if item not in failed_ids]
            state["pending"] = None
            _save_state(state)
        return
    if not name:
        _clear_pending_keep_queue()
        _open_ready_jobs(_release_screened(product_ids))
        return
    with _LOCK:
        state = _load_state()
        state["pending"] = None
        inflight = _named_inflight(state)
        inflight.append(
            {
                "name": name,
                "product_ids": product_ids,
                "sent_ids": sent_ids,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        state["inflight"] = inflight
        _save_state(state)
    unsent = [pid for pid in product_ids if pid not in set(sent_ids)]
    _open_ready_jobs(_release_screened(unsent))
    _mark_batch_ok()
    logger.info("counterfeit gemini batch đã gửi %s (%s sản phẩm)", name, len(sent_ids))


def _drop_inflight(name: str) -> None:
    with _LOCK:
        state = _load_state()
        state["inflight"] = [job for job in _named_inflight(state) if str(job.get("name") or "") != name]
        pending = state.get("pending")
        if isinstance(pending, dict) and str(pending.get("name") or "") == name:
            state["pending"] = None
        _save_state(state)


def _poll_one_batch(job: Dict[str, Any]) -> None:
    name = str(job.get("name") or "")
    if not name:
        return
    try:
        body = _get_batch(name)
    except Exception:
        logger.warning("counterfeit gemini batch: chưa đọc được trạng thái %s", name, exc_info=True)
        return
    status = _batch_status(body)
    if status in {"running", "pending", "unknown"}:
        return
    if status == "failed":
        logger.warning("counterfeit gemini batch lỗi %s: %s", name, str(body)[:400])
        _notify_batch_down(f"Batch {name} lỗi: {str(body)[:300]}")
        sent = [str(item) for item in (job.get("sent_ids") or job.get("product_ids") or [])]
        _drop_inflight(name)
        _requeue_ids(sent)
        return
    try:
        output = _download_output(body)
        checked = _apply_output(output)
    except Exception:
        logger.exception("counterfeit gemini batch: không đọc được kết quả %s", name)
        return
    sent = [str(item) for item in (job.get("sent_ids") or [])]
    _drop_inflight(name)
    _requeue_ids([pid for pid in sent if pid not in set(checked)])
    _open_ready_jobs(_release_screened(checked))


def poll_pending_batch() -> None:
    with _LOCK:
        state = _load_state()
        pending = state.get("pending")
        jobs = list(_named_inflight(state))
    if isinstance(pending, dict) and pending.get("status") == "building" and not pending.get("name"):
        started = str(pending.get("started_at") or "")
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(started)
        except ValueError:
            age = None
        if age is not None and age.total_seconds() >= 1800:
            _clear_pending_keep_queue()
            with _LOCK:
                fresh = _load_state()
                ids = [str(item) for item in (pending.get("product_ids") or [])]
                queued = list(fresh.get("queued_product_ids") or [])
                fresh["queued_product_ids"] = ids + [item for item in queued if item not in set(ids)]
                _save_state(fresh)
    for job in jobs:
        _poll_one_batch(job)
    sweep_unchecked_products()
    if _load_state().get("queued_product_ids"):
        submit_queued_batch()


def _requeue_ids(product_ids: List[str]) -> None:
    ids = [str(item).strip() for item in product_ids if str(item).strip()]
    if not ids:
        return
    with _LOCK:
        state = _load_state()
        queued = list(state.get("queued_product_ids") or [])
        seen = set(queued)
        for product_id in ids:
            if product_id not in seen:
                queued.append(product_id)
                seen.add(product_id)
        state["queued_product_ids"] = queued
        _save_state(state)


def _release_screened(product_ids: List[str]) -> List[str]:
    done = {str(item).strip() for item in product_ids if str(item).strip()}
    if not done:
        return []
    ready: List[str] = []
    with _LOCK:
        state = _load_state()
        waiting = dict(state.get("waiting_by_job") or {})
        for job_id, ids in list(waiting.items()):
            left = [str(item) for item in ids if str(item) not in done]
            if left:
                waiting[job_id] = left
            else:
                waiting.pop(job_id, None)
                ready.append(str(job_id))
        state["waiting_by_job"] = waiting
        _save_state(state)
    return ready


def _open_ready_jobs(job_ids: List[str]) -> None:
    if not job_ids:
        return
    from app.crud import image_localization_job as job_crud
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        for job_id in job_ids:
            row = job_crud.get_job(db, job_id)
            if row is None:
                continue
            status = (row.status or "").strip().lower()
            if status in {"cancelled", "done", "error"} or (row.phase or "") != "counterfeit_check":
                continue
            job_crud.patch_job(
                db,
                job_id,
                {
                    "status": "queued",
                    "phase": "queued",
                    "message": "Đã kiểm hàng giả. Bắt đầu bản địa hóa ảnh.",
                },
            )
    finally:
        db.close()


def split_localization_ids(db: Any, product_ids: List[str]) -> tuple:
    """Chia hàng đợi: đã gắn cờ, đã kiểm sạch, chưa kiểm."""
    from app.models.product import Product
    from app.services.consult_image_text import counterfeit_was_checked, image_counterfeit_risk

    blocked: List[str] = []
    ready: List[str] = []
    waiting: List[str] = []
    rows = (
        db.query(Product.product_id, Product.consult_image_text, Product.main_image, Product.images, Product.gallery)
        .filter(Product.product_id.in_(product_ids or [""]))
        .all()
    )
    by_id = {str(row[0]): row for row in rows if row[0]}
    for product_id in product_ids:
        row = by_id.get(product_id)
        if row is None:
            continue
        stored = row[1]
        if image_counterfeit_risk(stored):
            blocked.append(product_id)
        elif counterfeit_was_checked(stored) or not _row_has_image(row[2], row[3], row[4]):
            ready.append(product_id)
        else:
            waiting.append(product_id)
    return blocked, ready, waiting


def _row_has_image(main: Any, images: Any, gallery: Any) -> bool:
    if str(main or "").strip():
        return True
    for bucket in (images, gallery):
        if not isinstance(bucket, list):
            continue
        for item in bucket:
            url = item.strip() if isinstance(item, str) else ""
            if isinstance(item, dict):
                url = str(item.get("url") or item.get("src") or "").strip()
            if url:
                return True
    return False


def _clear_pending_keep_queue() -> None:
    with _LOCK:
        state = _load_state()
        state["pending"] = None
        _save_state(state)


def _batch_status(body: Dict[str, Any]) -> str:
    raw = ""
    for node in (
        body.get("state"),
        (body.get("metadata") or {}).get("state") if isinstance(body.get("metadata"), dict) else None,
        body.get("status"),
    ):
        if isinstance(node, dict):
            raw = str(node.get("name") or node.get("state") or "")
        elif node:
            raw = str(node)
        if raw:
            break
    token = raw.upper()
    if "SUCCESS" in token or "SUCCEED" in token:
        return "succeeded"
    if "FAIL" in token or "CANCEL" in token or "EXPIR" in token:
        return "failed"
    if "RUNNING" in token or "PROCESSING" in token:
        return "running"
    if "PENDING" in token or "QUEUED" in token:
        return "pending"
    return "unknown"


def _find_output_file(node: Any) -> str:
    if isinstance(node, dict):
        for key in ("responsesFile", "responses_file", "fileName", "file_name", "file"):
            value = node.get(key)
            if isinstance(value, str) and value.startswith("files/"):
                return value
        for value in node.values():
            found = _find_output_file(value)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_output_file(value)
            if found:
                return found
    return ""


def _headers() -> Dict[str, str]:
    return {"x-goog-api-key": _api_key()}


def _upload_and_create(product_ids: List[str]) -> tuple:
    key = _api_key()
    if len(key) < 10:
        from app.services.ai_run_alert import raise_ai_stopped

        raise_ai_stopped(_ALERT_MODEL, "Thiếu GEMINI_API_KEY")
    payload, sent_ids = _build_jsonl(product_ids)
    if not str(payload).strip():
        logger.info("counterfeit gemini batch: %s sản phẩm không có ảnh, bỏ qua", len(product_ids))
        return "", []
    upload = requests.post(
        "https://generativelanguage.googleapis.com/upload/v1beta/files",
        headers={
            **_headers(),
            "X-Goog-Upload-Protocol": "multipart",
        },
        files={
            "metadata": (
                None,
                json.dumps({"file": {"display_name": "vp8-counterfeit.jsonl"}}),
                "application/json",
            ),
            "data": ("counterfeit.jsonl", payload.encode("utf-8"), "application/jsonl"),
        },
        timeout=180,
    )
    upload.raise_for_status()
    file_name = str(((upload.json() or {}).get("file") or {}).get("name") or "")
    if not file_name:
        raise RuntimeError(f"Upload batch không trả tên file: {upload.text[:300]}")
    created = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{_MODEL}:batchGenerateContent",
        headers={**_headers(), "Content-Type": "application/json"},
        json={
            "batch": {
                "display_name": "188-counterfeit",
                "input_config": {"file_name": file_name},
            }
        },
        timeout=60,
    )
    created.raise_for_status()
    body = created.json() or {}
    name = str(body.get("name") or (body.get("batch") or {}).get("name") or "")
    if not name:
        raise RuntimeError(f"Tạo batch không trả name: {created.text[:300]}")
    return name, sent_ids


def _get_batch(name: str) -> Dict[str, Any]:
    path = name if name.startswith("http") else f"https://generativelanguage.googleapis.com/v1beta/{name}"
    response = requests.get(path, headers=_headers(), timeout=45)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


def _download_output(body: Dict[str, Any]) -> str:
    file_name = _find_output_file(body)
    if not file_name:
        raise RuntimeError("Batch xong nhưng không có file kết quả")
    response = requests.get(
        f"https://generativelanguage.googleapis.com/download/v1beta/{file_name}:download",
        headers=_headers(),
        params={"alt": "media"},
        timeout=180,
    )
    response.raise_for_status()
    return response.text


def _apply_output(raw: str) -> List[str]:
    from app.db.session import SessionLocal
    from app.models.product import Product
    from app.services.consult_image_text import (
        counterfeit_hit_fingerprint,
        counterfeit_hit_labels,
        set_gemini_counterfeit,
    )
    from app.services.counterfeit_report import counterfeit_image_rows, schedule_counterfeit_payload

    notices: List[Dict[str, Any]] = []
    checked: List[str] = []
    db = SessionLocal()
    try:
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            product_id = str(item.get("key") or "").strip()
            if not product_id or item.get("error"):
                continue
            brands = parse_brand_json(_response_text(item))
            if brands is None:
                continue
            product = db.query(Product).filter(Product.product_id == product_id).first()
            if product is None:
                continue
            before = counterfeit_hit_fingerprint(product.consult_image_text)
            image_url = str(getattr(product, "main_image", "") or "")
            product.consult_image_text = set_gemini_counterfeit(
                product.consult_image_text,
                brands,
                image_url,
            )
            after = counterfeit_hit_fingerprint(product.consult_image_text)
            checked.append(product_id)
            if after and after != before:
                notices.append(
                    {
                        "product_id": product_id,
                        "name": str(product.name or ""),
                        "code": str(product.code or ""),
                        "hits": counterfeit_hit_labels(product.consult_image_text),
                        "images": counterfeit_image_rows(product.consult_image_text),
                    }
                )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    for notice in notices:
        schedule_counterfeit_payload(notice)
    return checked


def _build_jsonl(product_ids: List[str]) -> tuple:
    from app.db.session import SessionLocal
    from app.models.product import Product

    db = SessionLocal()
    lines: List[str] = []
    sent_ids: List[str] = []
    try:
        for product_id in product_ids:
            product = db.query(Product).filter(Product.product_id == product_id).first()
            if product is None:
                continue
            image = _product_jpeg(product)
            if not image:
                continue
            request = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": _PROMPT},
                            {
                                "inline_data": {
                                    "mime_type": "image/jpeg",
                                    "data": base64.b64encode(image).decode("ascii"),
                                }
                            },
                        ],
                    }
                ],
                "generation_config": {
                    "temperature": 0,
                    "max_output_tokens": 256,
                    "response_mime_type": "application/json",
                },
            }
            lines.append(json.dumps({"key": product_id, "request": request}, ensure_ascii=False))
            sent_ids.append(product_id)
    finally:
        db.close()
    return "\n".join(lines), sent_ids


def _product_urls(product: Any) -> List[str]:
    urls: List[str] = []
    main = str(getattr(product, "main_image", "") or "").strip()
    if main:
        urls.append(main)
    for bucket in (getattr(product, "images", None), getattr(product, "gallery", None)):
        if isinstance(bucket, list):
            for item in bucket:
                url = item.strip() if isinstance(item, str) else ""
                if isinstance(item, dict):
                    url = str(item.get("url") or item.get("src") or "").strip()
                if url and url not in urls:
                    urls.append(url)
                if len(urls) >= _MAX_IMAGES:
                    return urls
    return urls[:_MAX_IMAGES]


def _product_jpeg(product: Any) -> bytes:
    blobs: List[bytes] = []
    for url in _product_urls(product):
        try:
            response = requests.get(url, timeout=25)
            response.raise_for_status()
        except requests.RequestException:
            continue
        data = response.content
        if data:
            blobs.append(data)
        if len(blobs) >= _MAX_IMAGES:
            break
    return _stitch_jpeg(blobs)


def _stitch_jpeg(blobs: List[bytes]) -> bytes:
    if not blobs:
        return b""
    try:
        from PIL import Image
    except ImportError:
        return blobs[0]
    frames = []
    for raw in blobs:
        try:
            image = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception:
            continue
        if image.width > 800:
            height = max(1, int(image.height * 800 / image.width))
            image = image.resize((800, height))
        if image.height > 900:
            image = image.crop((0, 0, image.width, 900))
        frames.append(image)
    if not frames:
        return b""
    if len(frames) == 1:
        buf = io.BytesIO()
        frames[0].save(buf, format="JPEG", quality=75)
        return buf.getvalue()
    width = max(frame.width for frame in frames)
    gap = 8
    height = sum(frame.height for frame in frames) + gap * (len(frames) - 1)
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    top = 0
    for frame in frames:
        canvas.paste(frame, ((width - frame.width) // 2, top))
        top += frame.height + gap
    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=75)
    return buf.getvalue()


def start_counterfeit_batch_poller() -> None:
    def _loop() -> None:
        while True:
            try:
                poll_pending_batch()
            except Exception:
                logger.exception("counterfeit gemini batch poll lỗi")
            time.sleep(_POLL_SECONDS)

    threading.Thread(target=_loop, daemon=True, name="counterfeit-gemini-batch").start()
