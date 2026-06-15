import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.security import require_module_permission
from app.core.config import settings
from app.crud import image_localization_job as image_loc_job_crud
from app.db.retry import is_transient_db_error, release_db_session, run_db_write
from app.db.session import SessionLocal, get_db
from app.models.admin import AdminUser
from app.models.product import Product
from app.services.image_localization_job_abort import (
    force_abort_running_service,
    register_running_service,
    unregister_running_service,
)
from app.services.image_localization_job_runtime import (
    payload_from_stored,
    start_job_process,
    start_resume_daemon,
)
from app.services.image_localization_service import (
    GeminiApiImageAdapter,
    ImageLocalizationError,
    OpenAiGptImageAdapter,
    ProductImageLocalizationService,
    is_image_localization_fatal_dependency_error,
    products_for_job_resume,
    products_pending_localization,
    reset_stale_processing_before_fresh_job,
    reset_stale_processing_in_queue,
)
from app.services.image_localization_temp_cleanup import cleanup_runtime_temp_now
from app.services.image_localization_temp_cleanup import cleanup_stale_image_localization_temp
from app.services.image_localization_temp_cleanup import guard_runtime_disk_space

logger = logging.getLogger(__name__)

router = APIRouter()

_jobs_lock = threading.Lock()
_jobs: Dict[str, Dict[str, Any]] = {}

_TERMINAL_JOB_STATUSES = frozenset({"done", "error", "cancelled"})
_RESUMABLE_JOB_STATUSES = frozenset({"queued", "running"})

# Trong một job: SP failed / exception (không phải fatal OCR–DeepSeek) đếm liên tiếp; đủ ngưỡng thì dừng job.
IMAGE_LOCALIZATION_MAX_CONSECUTIVE_PRODUCT_FAILURES = 3

# Giới hạn độ dài danh sách trả về client (tránh JSON job quá lớn).
_JOB_QUEUE_IDS_MAX = 400
_JOB_SKIPPED_REPORT_MAX = 120
_JOB_RECENT_RESULTS_MAX = 40


def _clip_job_message(v: Any, max_len: int = 600) -> str:
    s = str(v or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"


def _unique_product_ids(ids: Optional[Iterable[str]]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for raw in ids or []:
        pid = str(raw).strip()
        if not pid or pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
    return out


def _completed_product_count(done: int, failed: int, skipped: int) -> int:
    return int(done or 0) + int(failed or 0) + int(skipped or 0)


def _job_progress(
    *,
    done: int,
    failed: int,
    skipped: int,
    total: int,
    in_flight: bool = False,
) -> tuple[int, float]:
    completed = _completed_product_count(done, failed, skipped)
    current = completed + (1 if in_flight else 0)
    if total and total > 0:
        current = min(current, total)
        percent = round(100.0 * min(completed, total) / total, 1)
    else:
        percent = 0.0
    return current, percent


def _mark_processed_product(processed_ids: List[str], processed_set: set[str], product_id: str) -> bool:
    pid = str(product_id).strip()
    if not pid or pid in processed_set:
        return False
    processed_set.add(pid)
    processed_ids.append(pid)
    return True


def _account_localized_queue_skips(
    db: Session,
    queue_ids: List[str],
    processed_ids: List[str],
    processed_set: set[str],
    skipped: int,
    skipped_reports: List[Dict[str, Any]],
) -> int:
    """SP trong hàng đợi đã localized (không force) → bỏ qua và cộng tiến độ."""
    remaining = [pid for pid in _unique_product_ids(queue_ids) if pid not in processed_set]
    if not remaining:
        return skipped
    rows = (
        db.query(Product.product_id)
        .filter(
            Product.product_id.in_(remaining),
            Product.image_localization_status == "localized",
        )
        .all()
    )
    for (pid,) in rows:
        if not _mark_processed_product(processed_ids, processed_set, pid):
            continue
        skipped += 1
        skipped_reports.append(
            {
                "product_id": pid,
                "message": "Bỏ qua vì sản phẩm đã bản địa hóa trước đó.",
            }
        )
    return skipped


class StartImageLocalizationPayload(BaseModel):
    language: str = Field("vi", description="vi, en, th, id")
    force: bool = False
    dry_run: bool = False
    product_ids: Optional[List[str]] = None
    limit: Optional[int] = Field(None, ge=1, le=10000)
    gemini_mode: Optional[str] = Field(
        None,
        description="api | openai. api = GEMINI_API_KEY+Nano Banana; openai = OPENAI_API_KEY+GPT Image edits. Để trống = IMAGE_LOCALIZATION_GEMINI_MODE.",
    )
    gemini_image_model: Optional[str] = Field(None, max_length=120)
    gemini_image_size: Optional[str] = Field(
        None,
        max_length=16,
        description="2K hoặc 4K — Gemini API imageConfig.imageSize. Để trống = .env IMAGE_LOCALIZATION_GEMINI_API_DEFAULT_IMAGE_SIZE (mặc định 2K). Giá trị cũ 512/1K được nâng lên 2K.",
    )
    openai_image_model: Optional[str] = Field(None, max_length=120)
    openai_image_quality: Optional[str] = Field(
        None,
        max_length=16,
        description="high hoặc auto — GPT Image. low/medium bị ép thành high. Để trống = .env IMAGE_LOCALIZATION_OPENAI_DEFAULT_IMAGE_QUALITY (mặc định high).",
    )
    openai_image_size: Optional[str] = Field(
        None,
        max_length=32,
        description="auto | preset lớn (1024x1792, 1792x1024, 1536x1024, 1024x1536). Không cho 1024×1024/512 để khớp chất lượng pipeline Gemini.",
    )
    inference_tier: Optional[str] = Field(
        None,
        description="Đã deprecated — luôn standard (Flex / preset rẻ đã bỏ; chỉ pipeline chất lượng đầy đủ).",
    )
    allow_ai_image_models: Optional[bool] = Field(
        None,
        description=(
            "false = cấm hẳn Gemini/GPT ảnh trong batch (chỉ OCR + DeepSeek + vẽ local), bất kể IMAGE_LOCALIZATION_AI_IMAGE_EXPLICIT_ONLY. "
            "true = luôn cho phép gọi AI ảnh khi pipeline cần. "
            "null = mặc định: nếu explicit_only bật thì chỉ AI khi SP có product_info.image_localization.allow_ai_models; "
            "nếu explicit_only tắt thì cho phép AI như cũ."
        ),
    )
def _resolve_gemini_mode(raw: Optional[str]) -> str:
    m = (raw or getattr(settings, "IMAGE_LOCALIZATION_GEMINI_MODE", "api") or "api").strip().lower()
    if m == "web":
        m = "api"
    return m if m in ("api", "openai") else "api"


def _resolve_inference_tier(raw: Optional[str]) -> str:
    return "standard"


def _persist_job_to_db(job_id: str) -> None:
    with _jobs_lock:
        snapshot = dict(_jobs.get(job_id) or {})
    if not snapshot:
        return
    db = SessionLocal()
    try:
        image_loc_job_crud.sync_dict_to_row(db, job_id, snapshot)
    except Exception:
        logger.exception("persist image localization job %s failed", job_id)
        db.rollback()
    finally:
        db.close()


def _job_update(job_id: str, **kwargs: Any) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id, {})
        cur = (job.get("status") or "").strip().lower()
        new_status = (kwargs.get("status") or "").strip().lower() if "status" in kwargs else ""
        if cur in _TERMINAL_JOB_STATUSES and new_status and new_status not in _TERMINAL_JOB_STATUSES:
            kwargs = dict(kwargs)
            kwargs.pop("status", None)
            kwargs.pop("phase", None)
        job.update(kwargs)
        job["job_id"] = job_id
        _jobs[job_id] = job
    _persist_job_to_db(job_id)


def _job_cancel_signal(job_id: str) -> bool:
    """Đọc DB — worker subprocess thấy hủy ngay dù bộ nhớ process con cũ."""
    j = _job_get(job_id)
    if (j.get("status") or "").strip().lower() == "cancelled":
        return True
    if bool(j.get("cancel_requested")):
        return True
    db = SessionLocal()
    try:
        row = image_loc_job_crud.get_job(db, job_id)
        if not row:
            return False
        if (row.status or "").strip().lower() == "cancelled":
            return True
        return bool(row.cancel_requested)
    finally:
        db.close()


def _job_get(job_id: str) -> Dict[str, Any]:
    """DB là nguồn đúng (worker chạy subprocess ghi DB; bộ nhớ parent dễ cũ)."""
    db_data: Dict[str, Any] = {}
    db = SessionLocal()
    try:
        row = image_loc_job_crud.get_job(db, job_id)
        if row:
            db_data = image_loc_job_crud.row_to_job_dict(row)
            db_data["processed_product_ids"] = _unique_product_ids(row.processed_product_ids or [])
    finally:
        db.close()

    with _jobs_lock:
        mem = dict(_jobs.get(job_id) or {})

    if not db_data:
        # DB không còn dòng — snapshot RAM là job ma (đã xóa/hủy trực tiếp trên DB).
        with _jobs_lock:
            _jobs.pop(job_id, None)
        return {}

    db_st = (db_data.get("status") or "").strip().lower()
    if db_st in _TERMINAL_JOB_STATUSES:
        merged = {**db_data}
    else:
        merged = {**mem, **db_data}
    merged["job_id"] = job_id
    with _jobs_lock:
        _jobs[job_id] = merged
    return dict(merged)


def _payload_snapshot(payload: StartImageLocalizationPayload) -> Dict[str, Any]:
    return payload.model_dump()


def _create_db_job_row(
    job_id: str,
    payload: StartImageLocalizationPayload,
    *,
    extra: Dict[str, Any],
) -> None:
    db = SessionLocal()
    try:
        image_loc_job_crud.create_job(
            db,
            job_id,
            {
                "status": extra.get("status", "queued"),
                "phase": extra.get("phase", "queued"),
                "message": extra.get("message"),
                "payload": _payload_snapshot(payload),
                "language": payload.language,
                "force": bool(payload.force),
                "dry_run": bool(payload.dry_run),
                "gemini_mode": extra.get("gemini_mode"),
                "local_image_only": bool(extra.get("local_image_only", False)),
                "current": extra.get("current", 0),
                "total": extra.get("total"),
                "done": extra.get("done", 0),
                "failed": extra.get("failed", 0),
                "skipped": extra.get("skipped", 0),
                "percent": extra.get("percent"),
                "queue_product_ids": list(extra.get("queue_product_ids") or []),
                "processed_product_ids": list(extra.get("processed_product_ids") or []),
                "job_queue_truncated": bool(extra.get("job_queue_truncated", False)),
                "recent_results": list(extra.get("recent_results") or []),
                "skipped_product_reports": list(extra.get("skipped_product_reports") or []),
            },
        )
    finally:
        db.close()


def _finalize_job_cancelled(
    job_id: str,
    *,
    done: int,
    failed: int,
    skipped: int,
    total: int,
    processed_ids: List[str],
    results: List[Dict[str, Any]],
    skipped_reports: List[Dict[str, Any]],
    message: str = "Đã hủy job bản địa hóa ảnh.",
) -> None:
    current, percent = _job_progress(done=done, failed=failed, skipped=skipped, total=total)
    _job_update(
        job_id,
        status="cancelled",
        phase="cancelled",
        current=current,
        percent=percent,
        done=done,
        failed=failed,
        skipped=skipped,
        message=message,
        finished_at=datetime.now(timezone.utc).isoformat(),
        current_product_id=None,
        cancel_requested=True,
        skipped_product_reports=skipped_reports[-_JOB_SKIPPED_REPORT_MAX:],
        recent_results=results[-_JOB_RECENT_RESULTS_MAX:],
        processed_product_ids=processed_ids,
    )


def _is_job_cancel_exception(exc: BaseException) -> bool:
    if isinstance(exc, ImageLocalizationError):
        return "hủy" in str(exc).lower()
    return False


def _reset_product_after_cancel(db: Session, product: Product) -> None:
    fresh = db.query(Product).filter(Product.id == product.id).first()
    if fresh is None:
        return
    if (fresh.image_localization_status or "").strip() == "processing":
        fresh.image_localization_status = "pending"
        fresh.image_localization_error = None
        db.commit()


def _reset_product_after_cancel_by_pk(product_db_id: int) -> None:
    def write(sess: Session) -> None:
        fresh = sess.query(Product).filter(Product.id == product_db_id).first()
        if fresh is None:
            return
        if (fresh.image_localization_status or "").strip() == "processing":
            fresh.image_localization_status = "pending"
            fresh.image_localization_error = None

    try:
        run_db_write(SessionLocal, write)
    except Exception:
        logger.exception("Không reset pending sau hủy product_db_id=%s", product_db_id)


def _reset_product_processing_by_product_id(db: Session, product_id: str) -> None:
    pid = (product_id or "").strip()
    if not pid:
        return
    p = db.query(Product).filter(Product.product_id == pid).first()
    if p is None:
        return
    if (p.image_localization_status or "").strip() == "processing":
        p.image_localization_status = "pending"
        p.image_localization_error = None
        db.commit()


def _reset_job_processing_products(db: Session, job: Dict[str, Any]) -> int:
    """Trả SP trong hàng đợi job đang `processing` về `pending` (sau hủy ngay)."""
    ids = _unique_product_ids(
        list(job.get("queue_product_ids") or [])
        + list(job.get("job_queue_product_ids") or [])
    )
    current = (job.get("current_product_id") or "").strip()
    if current:
        ids = _unique_product_ids([*ids, current])
    if not ids:
        return 0
    rows = (
        db.query(Product)
        .filter(
            Product.product_id.in_(ids),
            Product.image_localization_status == "processing",
        )
        .all()
    )
    for p in rows:
        p.image_localization_status = "pending"
        p.image_localization_error = None
    if rows:
        db.commit()
    return len(rows)


def _force_cancel_job_in_db(db: Session, job_id: str, job: Dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    image_loc_job_crud.patch_job(
        db,
        job_id,
        {
            "status": "cancelled",
            "phase": "cancelled",
            "cancel_requested": True,
            "current_product_id": None,
            "message": "Đã hủy ngay — worker đã dừng.",
            "finished_at": now,
        },
    )
    _reset_job_processing_products(db, job)
    with _jobs_lock:
        _jobs.pop(job_id, None)


def _job_is_cancelled(job_id: str) -> bool:
    return (_job_get(job_id).get("status") or "").strip().lower() == "cancelled"


def _finalize_job_cancelled_from_snapshot(
    job_id: str,
    job: Dict[str, Any],
    *,
    message: str,
) -> None:
    _finalize_job_cancelled(
        job_id,
        done=int(job.get("done") or 0),
        failed=int(job.get("failed") or 0),
        skipped=int(job.get("skipped") or 0),
        total=int(job.get("total") or 0),
        processed_ids=_unique_product_ids(job.get("processed_product_ids") or []),
        results=list(job.get("recent_results") or []),
        skipped_reports=list(job.get("skipped_product_reports") or []),
        message=message,
    )


def _run_job(job_id: str, payload: StartImageLocalizationPayload, *, resume: bool = False) -> None:
    db = SessionLocal()
    processed_ids: List[str] = []
    processed_set: set[str] = set()
    done = 0
    failed = 0
    skipped = 0
    results: List[Dict[str, Any]] = []
    skipped_reports: List[Dict[str, Any]] = []
    try:
        # Kiểm tra dung lượng ngay đầu job để tránh đơ server khi ổ gần đầy.
        guard_runtime_disk_space()
        cleanup_stale_image_localization_temp()
        if resume:
            row = image_loc_job_crud.get_job(db, job_id)
            if not row:
                return
            stored = payload_from_stored(row.payload, StartImageLocalizationPayload)
            if stored is not None:
                payload = stored
            processed_ids = _unique_product_ids(row.processed_product_ids or [])
            processed_set = set(processed_ids)
            done = int(row.done or 0)
            failed = int(row.failed or 0)
            skipped = int(row.skipped or 0)
            results = list(row.recent_results or [])[-100:]
            skipped_reports = list(row.skipped_product_reports or [])[-_JOB_SKIPPED_REPORT_MAX:]
            queue_ids = _unique_product_ids(row.queue_product_ids or [])
            total = len(queue_ids)
            reset_stale_processing_in_queue(db, queue_ids, processed_ids)
            if not payload.force:
                skipped = _account_localized_queue_skips(
                    db, queue_ids, processed_ids, processed_set, skipped, skipped_reports
                )
            products = products_for_job_resume(db, queue_ids, processed_ids, payload.force)
            completed = _completed_product_count(done, failed, skipped)
            _job_update(
                job_id,
                status="running",
                phase="resuming",
                message=f"Tiếp tục job — đã xử lý {completed}/{total} sản phẩm…",
                started_at=row.started_at.isoformat() if row.started_at else datetime.now(timezone.utc).isoformat(),
            )
        else:
            stale_n = reset_stale_processing_before_fresh_job(db)
            _job_update(
                job_id,
                status="running",
                phase="selecting",
                message=(
                    "Đang chọn sản phẩm chưa bản địa hóa..."
                    + (f" (đã mở khóa {stale_n} SP kẹt processing)" if stale_n else "")
                ),
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            limit = payload.limit or int(getattr(settings, "IMAGE_LOCALIZATION_BATCH_LIMIT", 0) or 0)
            products = products_pending_localization(db, payload.product_ids, payload.force, limit)
            queue_ids = _unique_product_ids([p.product_id for p in products])
            total = len(queue_ids)

        queue_truncated = len(queue_ids) > _JOB_QUEUE_IDS_MAX
        queue_preview = queue_ids[:_JOB_QUEUE_IDS_MAX]
        current, percent = _job_progress(done=done, failed=failed, skipped=skipped, total=total)
        _job_update(
            job_id,
            total=total,
            current=current,
            percent=percent,
            job_queue_product_ids=queue_preview,
            job_queue_truncated=queue_truncated,
            queue_product_ids=queue_ids,
            processed_product_ids=processed_ids,
            done=done,
            failed=failed,
            skipped=skipped,
            skipped_product_reports=skipped_reports,
        )
        completed = _completed_product_count(done, failed, skipped)
        if total == 0 or (resume and not products):
            if resume and total > 0 and completed >= total:
                done_msg = f"Đã hoàn tất ({completed}/{total} sản phẩm trong hàng đợi)."
            elif resume and not products:
                done_msg = "Không còn sản phẩm cần xử lý trong hàng đợi resume."
            else:
                done_msg = "Không còn sản phẩm cần bản địa hóa ảnh."
            current, percent = _job_progress(done=done, failed=failed, skipped=skipped, total=total)
            _job_update(
                job_id,
                status="done",
                phase="done",
                message=done_msg,
                finished_at=datetime.now(timezone.utc).isoformat(),
                percent=100.0 if total else percent,
                current=current if total else 0,
                done=done,
                failed=failed,
                skipped=skipped,
                current_product_id=None,
                job_queue_product_ids=queue_preview if total else [],
                job_queue_truncated=queue_truncated if total else False,
                processed_product_ids=processed_ids,
                skipped_product_reports=skipped_reports,
            )
            return

        service = ProductImageLocalizationService(
            language=payload.language,
            force=payload.force,
            dry_run=payload.dry_run,
            gemini_mode=_resolve_gemini_mode(payload.gemini_mode),
            gemini_image_model=payload.gemini_image_model,
            gemini_image_size=payload.gemini_image_size,
            openai_image_model=payload.openai_image_model,
            openai_image_quality=payload.openai_image_quality,
            openai_image_size=payload.openai_image_size,
            inference_tier=_resolve_inference_tier(payload.inference_tier),
            allow_ai_image_models=payload.allow_ai_image_models,
        )
        register_running_service(job_id, service)
        consecutive_product_failures = 0
        transient_db_retries: Dict[str, int] = {}

        def should_cancel() -> bool:
            return _job_cancel_signal(job_id)

        product_ids_to_run = [str(p.product_id).strip() for p in products if str(getattr(p, "product_id", "")).strip()]
        for product_id in product_ids_to_run:
            # Mỗi sản phẩm kiểm tra lại dung lượng, dừng sớm nếu ổ đĩa xuống ngưỡng nguy hiểm.
            guard_runtime_disk_space()
            if _job_is_cancelled(job_id):
                return
            if should_cancel():
                _finalize_job_cancelled(
                    job_id,
                    done=done,
                    failed=failed,
                    skipped=skipped,
                    total=total,
                    processed_ids=processed_ids,
                    results=results,
                    skipped_reports=skipped_reports,
                    message="Đã hủy job sau khi xong bước hiện tại.",
                )
                return
            # Dùng session ngắn cho từng sản phẩm:
            # - tránh giữ 1 PostgreSQL connection quá lâu trong job lớn
            # - giúp pool_pre_ping hoạt động hiệu quả hơn (checkout lại mỗi vòng)
            db.close()
            db = SessionLocal()
            product = db.query(Product).filter(Product.product_id == product_id).first()
            product_db_id: Optional[int] = product.id if product is not None else None
            if product is None:
                skipped += 1
                _mark_processed_product(processed_ids, processed_set, product_id)
                skipped_reports.append(
                    {
                        "product_id": product_id,
                        "message": "Bỏ qua vì không còn sản phẩm trong DB.",
                    }
                )
                current, percent = _job_progress(done=done, failed=failed, skipped=skipped, total=total)
                _job_update(
                    job_id,
                    done=done,
                    failed=failed,
                    skipped=skipped,
                    current=current,
                    processed_product_ids=processed_ids,
                    percent=percent,
                    skipped_product_reports=skipped_reports[-_JOB_SKIPPED_REPORT_MAX:],
                )
                continue

            current, percent = _job_progress(
                done=done, failed=failed, skipped=skipped, total=total, in_flight=True
            )
            _job_update(
                job_id,
                phase="processing",
                current=current,
                percent=percent,
                message=f"Đang xử lý {current}/{total}: {product_id}",
                current_product_id=product_id,
            )
            try:
                result = service.process_product(db, product, should_cancel=should_cancel)
                if _job_is_cancelled(job_id):
                    return
                status = result.get("status")
                row = {
                    "product_id": product_id,
                    "status": status,
                    "message": _clip_job_message(result.get("message"), 320),
                    "processed_images": result.get("processed_images", 0),
                }
                results.append(row)
                if status == "failed":
                    failed += 1
                    consecutive_product_failures += 1
                    if consecutive_product_failures >= IMAGE_LOCALIZATION_MAX_CONSECUTIVE_PRODUCT_FAILURES:
                        last_msgs = " | ".join(
                            (r.get("message") or "")[:200]
                            for r in results[-IMAGE_LOCALIZATION_MAX_CONSECUTIVE_PRODUCT_FAILURES:]
                            if r.get("status") == "failed"
                        )
                        _mark_processed_product(processed_ids, processed_set, product.product_id)
                        current, percent = _job_progress(
                            done=done, failed=failed, skipped=skipped, total=total
                        )
                        _job_update(
                            job_id,
                            status="error",
                            phase="error",
                            current=current,
                            done=done,
                            failed=failed,
                            skipped=skipped,
                            processed_product_ids=processed_ids,
                            percent=percent,
                            message=(
                                f"Dừng job: {IMAGE_LOCALIZATION_MAX_CONSECUTIVE_PRODUCT_FAILURES} "
                                f"sản phẩm lỗi liên tiếp (đến {product_id}, {current}/{total}). "
                                f"{last_msgs[:750]}"
                            ),
                            finished_at=datetime.now(timezone.utc).isoformat(),
                            recent_results=results[-_JOB_RECENT_RESULTS_MAX:],
                            current_product_id=None,
                            skipped_product_reports=skipped_reports[-_JOB_SKIPPED_REPORT_MAX:],
                        )
                        return
                elif status == "skipped":
                    skipped += 1
                    consecutive_product_failures = 0
                    skipped_reports.append(
                        {
                            "product_id": product_id,
                            "message": (
                                ((result.get("message") or "").strip()[:480] or None)
                            ),
                        }
                    )
                else:
                    done += 1
                    consecutive_product_failures = 0
            except Exception as exc:
                if _job_is_cancelled(job_id):
                    release_db_session(db)
                    if product_db_id is not None:
                        _reset_product_after_cancel_by_pk(product_db_id)
                    return
                if should_cancel() or _is_job_cancel_exception(exc):
                    release_db_session(db)
                    if product_db_id is not None:
                        _reset_product_after_cancel_by_pk(product_db_id)
                    _finalize_job_cancelled(
                        job_id,
                        done=done,
                        failed=failed,
                        skipped=skipped,
                        total=total,
                        processed_ids=processed_ids,
                        results=results,
                        skipped_reports=skipped_reports,
                    )
                    return
                err_tail = str(exc)[:1000]
                release_db_session(db)

                if is_transient_db_error(exc):
                    retry_n = transient_db_retries.get(product_id, 0) + 1
                    transient_db_retries[product_id] = retry_n
                    if retry_n < 3:
                        def _reset_pending(sess: Session) -> None:
                            if product_db_id is None:
                                return
                            fresh = sess.query(Product).filter(Product.id == product_db_id).first()
                            if fresh is None:
                                return
                            if (fresh.image_localization_status or "").strip() == "processing":
                                fresh.image_localization_status = "pending"
                                fresh.image_localization_error = (
                                    f"Lỗi kết nối DB tạm thời (lần {retry_n}/3): {err_tail}"[:2000]
                                )

                        try:
                            run_db_write(SessionLocal, _reset_pending)
                        except Exception:
                            logger.exception(
                                "Không reset pending sau lỗi DB tạm thời product_id=%s",
                                product_id,
                            )
                        results.append(
                            {
                                "product_id": product_id,
                                "status": "retry",
                                "message": _clip_job_message(
                                    f"Lỗi kết nối DB tạm thời — thử lại ({retry_n}/3): {exc}",
                                    600,
                                ),
                            }
                        )
                        current, percent = _job_progress(
                            done=done, failed=failed, skipped=skipped, total=total
                        )
                        _job_update(
                            job_id,
                            phase="processing",
                            current=current,
                            percent=percent,
                            message=(
                                f"Lỗi DB tạm thời tại {product_id} — chờ {retry_n * 2}s rồi thử lại "
                                f"({current}/{total})"
                            ),
                            current_product_id=product_id,
                            recent_results=results[-_JOB_RECENT_RESULTS_MAX:],
                        )
                        time.sleep(min(retry_n * 2, 8))
                        continue

                failed += 1

                def _mark_failed(sess: Session) -> None:
                    if product_db_id is None:
                        return
                    fresh = sess.query(Product).filter(Product.id == product_db_id).first()
                    if fresh is None:
                        return
                    fresh.image_localization_status = "failed"
                    fresh.image_localization_language = payload.language
                    fresh.image_localization_error = str(exc)[:2000]

                try:
                    run_db_write(SessionLocal, _mark_failed)
                except Exception:
                    logger.exception("Không ghi trạng thái failed product_id=%s", product_id)

                results.append(
                    {
                        "product_id": product_id,
                        "status": "failed",
                        "message": _clip_job_message(exc, 600),
                    }
                )
                if is_image_localization_fatal_dependency_error(exc):
                    _mark_processed_product(processed_ids, processed_set, product_id)
                    current, percent = _job_progress(
                        done=done, failed=failed, skipped=skipped, total=total
                    )
                    _job_update(
                        job_id,
                        status="error",
                        phase="error",
                        current=current,
                        done=done,
                        failed=failed,
                        skipped=skipped,
                        processed_product_ids=processed_ids,
                        percent=percent,
                        message=(
                            "Dừng bản địa hóa ảnh vì OCR/DeepSeek lỗi bắt buộc "
                            f"(hết quota/tiền, thiếu key hoặc billing lỗi): {err_tail}"
                        ),
                        finished_at=datetime.now(timezone.utc).isoformat(),
                        recent_results=results[-_JOB_RECENT_RESULTS_MAX:],
                        current_product_id=None,
                        skipped_product_reports=skipped_reports[-_JOB_SKIPPED_REPORT_MAX:],
                    )
                    return
                consecutive_product_failures += 1
                if consecutive_product_failures >= IMAGE_LOCALIZATION_MAX_CONSECUTIVE_PRODUCT_FAILURES:
                    _mark_processed_product(processed_ids, processed_set, product_id)
                    current, percent = _job_progress(
                        done=done, failed=failed, skipped=skipped, total=total
                    )
                    _job_update(
                        job_id,
                        status="error",
                        phase="error",
                        current=current,
                        done=done,
                        failed=failed,
                        skipped=skipped,
                        processed_product_ids=processed_ids,
                        percent=percent,
                        message=(
                            f"Dừng job: {IMAGE_LOCALIZATION_MAX_CONSECUTIVE_PRODUCT_FAILURES} "
                            f"sản phẩm lỗi liên tiếp (exception tại {product_id}, {current}/{total}). {err_tail}"
                        ),
                        finished_at=datetime.now(timezone.utc).isoformat(),
                        recent_results=results[-_JOB_RECENT_RESULTS_MAX:],
                        current_product_id=None,
                        skipped_product_reports=skipped_reports[-_JOB_SKIPPED_REPORT_MAX:],
                    )
                    return
            finally:
                # Dọn ngay temp sau mỗi sản phẩm để tránh tích tụ đầy ổ trong job dài.
                try:
                    cleanup_runtime_temp_now()
                except Exception:
                    logger.exception("cleanup_runtime_temp_now failed product_id=%s", product_id)

            if _job_is_cancelled(job_id):
                return

            _mark_processed_product(processed_ids, processed_set, product_id)
            current, percent = _job_progress(done=done, failed=failed, skipped=skipped, total=total)
            _job_update(
                job_id,
                done=done,
                failed=failed,
                skipped=skipped,
                current=current,
                processed_product_ids=processed_ids,
                recent_results=results[-_JOB_RECENT_RESULTS_MAX:],
                percent=percent,
                skipped_product_reports=skipped_reports[-_JOB_SKIPPED_REPORT_MAX:],
            )

        if _job_is_cancelled(job_id):
            return

        current, _percent = _job_progress(done=done, failed=failed, skipped=skipped, total=total)
        _job_update(
            job_id,
            status="done",
            phase="done",
            current=current,
            done=done,
            failed=failed,
            skipped=skipped,
            percent=100.0,
            message=f"Hoàn tất: {done} xong, {failed} lỗi, {skipped} bỏ qua.",
            finished_at=datetime.now(timezone.utc).isoformat(),
            recent_results=results[-_JOB_RECENT_RESULTS_MAX:],
            current_product_id=None,
            skipped_product_reports=skipped_reports[-_JOB_SKIPPED_REPORT_MAX:],
            processed_product_ids=processed_ids,
        )
    except Exception as exc:
        if not _job_is_cancelled(job_id):
            _job_update(
                job_id,
                status="error",
                phase="error",
                message=_clip_job_message(exc, 700),
                finished_at=datetime.now(timezone.utc).isoformat(),
                current_product_id=None,
            )
    finally:
        try:
            unregister_running_service(job_id)
        except Exception:
            pass
        try:
            if "service" in locals():
                service.close()
        except Exception:
            pass
        try:
            cleanup_stale_image_localization_temp()
        except Exception:
            logger.exception("Dọn temp image localization sau job lỗi")
        db.close()


@router.get("/settings/gemini-auth")
def check_gemini_auth(
    language: str = "vi",
    _: AdminUser = Depends(require_module_permission("products")),
):
    _ai_jobs_ok = bool(getattr(settings, "IMAGE_LOCALIZATION_AI_IMAGE_JOBS_ALLOWED", False))
    return {
        "ai_image_jobs_allowed": _ai_jobs_ok,
        "default_gemini_mode": _resolve_gemini_mode(None),
        "image_model": getattr(settings, "IMAGE_LOCALIZATION_GEMINI_IMAGE_MODEL", "gemini-3-pro-image-preview"),
        "gemini_api_default_image_size": getattr(
            settings, "IMAGE_LOCALIZATION_GEMINI_API_DEFAULT_IMAGE_SIZE", ""
        ).strip(),
        "openai_image_model": getattr(settings, "IMAGE_LOCALIZATION_OPENAI_IMAGE_MODEL", "gpt-image-2"),
        "openai_default_image_quality": getattr(
            settings, "IMAGE_LOCALIZATION_OPENAI_DEFAULT_IMAGE_QUALITY", "high"
        ),
        "ai_image_explicit_only": bool(getattr(settings, "IMAGE_LOCALIZATION_AI_IMAGE_EXPLICIT_ONLY", False)),
        "ai_image_explicit_help": "Khi ai_image_explicit_only: chỉ gọi Gemini/GPT ảnh nếu job gửi allow_ai_image_models=true hoặc product_info.image_localization.allow_ai_models=true.",
        "gemini_api_image_sizes": ["2K", "4K"],
        "openai_image_qualities": ["high", "auto"],
        "openai_image_sizes": ["auto", "1024x1792", "1792x1024", "1536x1024", "1024x1536"],
        "inference_tier_options": ["standard"],
        "inference_tier_notes": {
            "quality_policy": (
                "Chỉ Gemini Pro Image + độ phân giải 2K/4K; GPT Image chỉ quality high/auto và size lớn. Flex / preset nhanh — rẻ đã gỡ."
            ),
            "batch": "Gemini Batch API (async, ~24h) không dùng trong job bản địa hóa tức thì.",
        },
        "api": GeminiApiImageAdapter(language).check_auth(),
        "openai": OpenAiGptImageAdapter(language).check_auth(),
    }


@router.get("/summary")
def summary(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    pending = db.query(Product).filter(
        (Product.image_localization_status.is_(None))
        | (Product.image_localization_status.in_(["", "pending"]))
    ).count()
    localized = db.query(Product).filter(Product.image_localization_status == "localized").count()
    failed = db.query(Product).filter(Product.image_localization_status == "failed").count()
    processing = db.query(Product).filter(Product.image_localization_status == "processing").count()
    skipped = db.query(Product).filter(Product.image_localization_status == "skipped").count()
    return {
        "pending": pending,
        "localized": localized,
        "failed": failed,
        "processing": processing,
        "skipped": skipped,
    }


@router.post("/jobs")
def start_job(
    payload: StartImageLocalizationPayload,
    _: AdminUser = Depends(require_module_permission("products")),
):
    _ai_jobs_ok = bool(getattr(settings, "IMAGE_LOCALIZATION_AI_IMAGE_JOBS_ALLOWED", False))
    if not _ai_jobs_ok and payload.allow_ai_image_models is not False:
        raise HTTPException(
            status_code=400,
            detail=(
                "Server đang giới hạn chỉ pipeline OCR + DeepSeek + vẽ local — gửi allow_ai_image_models=false. "
                "Bật lại Gemini/GPT ảnh: IMAGE_LOCALIZATION_AI_IMAGE_JOBS_ALLOWED=true trong .env."
            ),
        )
    mode = _resolve_gemini_mode(payload.gemini_mode)
    tier = _resolve_inference_tier(payload.inference_tier)
    skip_ai_image = payload.allow_ai_image_models is False
    if not skip_ai_image:
        if mode == "api":
            if not GeminiApiImageAdapter(
                payload.language,
                image_model=payload.gemini_image_model,
                image_size=payload.gemini_image_size,
                inference_tier=tier,
            ).check_auth().get("ready"):
                raise HTTPException(
                    status_code=400,
                    detail="Chế độ Gemini API: thiếu GEMINI_API_KEY trong cấu hình backend.",
                )
        elif mode == "openai":
            if not OpenAiGptImageAdapter(
                payload.language,
                image_model=payload.openai_image_model,
                image_quality=payload.openai_image_quality,
                image_size=payload.openai_image_size,
                inference_tier=tier,
            ).check_auth().get("ready"):
                raise HTTPException(
                    status_code=400,
                    detail="Chế độ OpenAI GPT Image: thiếu OPENAI_API_KEY trong cấu hình backend.",
                )
    job_id = uuid.uuid4().hex
    initial: Dict[str, Any] = {
        "status": "queued",
        "phase": "queued",
        "message": "Đã xếp hàng bản địa hóa ảnh.",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "current": 0,
        "total": None,
        "done": 0,
        "failed": 0,
        "skipped": 0,
        "percent": None,
        "language": payload.language,
        "force": payload.force,
        "dry_run": payload.dry_run,
        "gemini_mode": mode,
        "gemini_image_model": payload.gemini_image_model,
        "gemini_image_size": payload.gemini_image_size,
        "openai_image_model": payload.openai_image_model,
        "openai_image_quality": payload.openai_image_quality,
        "openai_image_size": payload.openai_image_size,
        "inference_tier": _resolve_inference_tier(payload.inference_tier),
        "allow_ai_image_models": payload.allow_ai_image_models,
        "local_image_only": bool(payload.allow_ai_image_models is False),
        "ai_image_explicit_only": bool(getattr(settings, "IMAGE_LOCALIZATION_AI_IMAGE_EXPLICIT_ONLY", False)),
        "processed_product_ids": [],
        "queue_product_ids": [],
    }
    with _jobs_lock:
        _jobs[job_id] = {**initial, "job_id": job_id}
    _create_db_job_row(job_id, payload, extra=initial)
    start_job_process(job_id, payload.model_dump(), resume=False)
    return {"job_id": job_id, "status": "queued"}


def start_image_localization_job_resume_daemon_if_enabled() -> None:
    """Quét job queued/running trong DB và chạy tiếp sau restart backend."""
    from app.core.config import settings

    if not getattr(settings, "IMAGE_LOCALIZATION_JOB_RESUME_ON_STARTUP", True):
        return
    start_resume_daemon(_run_job, StartImageLocalizationPayload)


@router.get("/jobs")
def list_jobs(
    limit: int = Query(20, ge=1, le=50),
    active_only: bool = Query(False, description="Chỉ job queued/running"),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Danh sách job trên server — khôi phục khung Tiến trình sau khi đóng/mở trình duyệt."""
    rows = image_loc_job_crud.list_jobs_for_admin_track(db, limit=limit, active_only=active_only)
    seen: set[str] = set()
    items: List[Dict[str, Any]] = []

    with _jobs_lock:
        mem_jobs = [dict(j) for j in _jobs.values()]
    for mem in sorted(mem_jobs, key=lambda j: j.get("created_at") or "", reverse=True):
        status = (mem.get("status") or "").strip().lower()
        if active_only and status not in _RESUMABLE_JOB_STATUSES:
            continue
        jid = (mem.get("job_id") or "").strip()
        if not jid or jid in seen:
            continue
        seen.add(jid)
        got = _job_get(jid)
        if got:
            items.append(got)

    for row in rows:
        if row.job_id in seen:
            continue
        seen.add(row.job_id)
        got = _job_get(row.job_id)
        if got:
            items.append(got)

    items.sort(key=lambda j: j.get("created_at") or "", reverse=True)
    items.sort(
        key=lambda j: 0
        if (j.get("status") or "").strip().lower() in _RESUMABLE_JOB_STATUSES
        else 1
    )
    items = items[:limit]
    active_count = sum(
        1
        for j in items
        if (j.get("status") or "").strip().lower() in _RESUMABLE_JOB_STATUSES
        and not bool(j.get("cancel_requested"))
    )
    return {"items": items, "active_count": active_count}


@router.delete("/jobs/terminal")
def delete_terminal_jobs(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Xóa job đã dừng / lỗi / hoàn tất khỏi DB và bộ nhớ server."""
    deleted_count, deleted_ids = image_loc_job_crud.delete_terminal_jobs(db)
    deleted_id_set = set(deleted_ids)
    with _jobs_lock:
        for jid in list(_jobs.keys()):
            status = (_jobs[jid].get("status") or "").strip().lower()
            if jid in deleted_id_set or status in _TERMINAL_JOB_STATUSES:
                _jobs.pop(jid, None)
    return {"deleted_count": deleted_count, "deleted_job_ids": deleted_ids}


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    _: AdminUser = Depends(require_module_permission("products")),
):
    job = _job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy job bản địa hóa ảnh")
    return job


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: str,
    mode: Literal["graceful", "force"] = Query(
        "graceful",
        description="graceful = chờ xong SP/ảnh hiện tại; force = dừng ngay (đóng adapter AI ảnh/session, SP dở → pending).",
    ),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    job = _job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy job bản địa hóa ảnh")
    if job.get("status") in {"done", "error", "cancelled"}:
        return job

    if mode == "force":
        _force_cancel_job_in_db(db, job_id, job)
        force_abort_running_service(job_id)
        return _job_get(job_id)

    if job.get("cancel_requested"):
        return _job_get(job_id)
    image_loc_job_crud.patch_job(
        db,
        job_id,
        {
            "cancel_requested": True,
            "message": "Đang hủy job sau ảnh hiện tại...",
        },
    )
    _job_update(job_id, cancel_requested=True, message="Đang hủy job sau ảnh hiện tại...")
    return _job_get(job_id)


@router.delete("/jobs/{job_id}")
def delete_job(
    job_id: str,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Xóa một job đã dừng / lỗi / hoàn tất khỏi DB và bộ nhớ server."""
    jid = (job_id or "").strip()
    if not jid:
        raise HTTPException(status_code=400, detail="Thiếu job_id")
    job = _job_get(jid)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy job bản địa hóa ảnh")
    status = (job.get("status") or "").strip().lower()
    if status in _RESUMABLE_JOB_STATUSES:
        raise HTTPException(status_code=409, detail="Job đang chạy — hãy hủy trước khi xóa.")
    deleted = image_loc_job_crud.delete_job(db, jid)
    if not deleted and status not in _TERMINAL_JOB_STATUSES:
        raise HTTPException(status_code=409, detail="Chỉ xóa được job đã dừng, lỗi hoặc hoàn tất.")
    with _jobs_lock:
        _jobs.pop(jid, None)
    return {"deleted": True, "job_id": jid}


@router.get("/products/{product_id}/report")
def product_image_localization_report(
    product_id: str,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Báo cáo chi tiết theo ảnh: xóa / AI / vẽ local / giữ — từ product_info.image_localization."""
    from app.services.image_localization_report import build_image_localization_report

    pid = (product_id or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="Thiếu product_id")
    p = db.query(Product).filter(or_(Product.product_id == pid, Product.code == pid)).first()
    if not p:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    return build_image_localization_report(p)

