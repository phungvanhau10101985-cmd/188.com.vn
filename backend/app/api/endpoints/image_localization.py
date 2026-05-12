import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.security import require_module_permission
from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.models.admin import AdminUser
from app.models.product import Product
from app.services.image_localization_service import (
    GeminiApiImageAdapter,
    GeminiWebImageAdapter,
    ImageLocalizationError,
    OpenAiGptImageAdapter,
    ProductImageLocalizationService,
    is_image_localization_fatal_dependency_error,
    products_pending_localization,
    save_gemini_cookie,
)

router = APIRouter()

_jobs_lock = threading.Lock()
_jobs: Dict[str, Dict[str, Any]] = {}

# Trong một job: SP failed / exception (không phải fatal OCR–DeepSeek) đếm liên tiếp; đủ ngưỡng thì dừng job.
IMAGE_LOCALIZATION_MAX_CONSECUTIVE_PRODUCT_FAILURES = 3

# Giới hạn độ dài danh sách trả về client (tránh JSON job quá lớn).
_JOB_QUEUE_IDS_MAX = 400
_JOB_SKIPPED_REPORT_MAX = 400


class GeminiCookiePayload(BaseModel):
    cookie: str = Field(..., min_length=4)


class StartImageLocalizationPayload(BaseModel):
    language: str = Field("vi", description="vi, en, th, id")
    force: bool = False
    dry_run: bool = False
    product_ids: Optional[List[str]] = None
    limit: Optional[int] = Field(None, ge=1, le=10000)
    gemini_mode: Optional[str] = Field(
        None,
        description="web | api | openai. web = Playwright+cookie; api = GEMINI_API_KEY+Nano Banana; openai = OPENAI_API_KEY+GPT Image edits. Để trống = IMAGE_LOCALIZATION_GEMINI_MODE.",
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
    playwright_headless: Optional[bool] = Field(
        None,
        description=(
            "Gemini Web (Playwright): True = ẩn Chromium, False = hiện cửa sổ. "
            "None = IMAGE_LOCALIZATION_PLAYWRIGHT_HEADLESS (.env)."
        ),
    )


def _resolve_gemini_mode(raw: Optional[str]) -> str:
    m = (raw or getattr(settings, "IMAGE_LOCALIZATION_GEMINI_MODE", "web") or "web").strip().lower()
    return m if m in ("web", "api", "openai") else "web"


def _resolve_inference_tier(raw: Optional[str]) -> str:
    return "standard"


def _effective_payload_playwright_headless(payload: StartImageLocalizationPayload) -> bool:
    """Headless trong job Gemini Web — request ghi đè .env khi playwright_headless khác None."""
    if payload.playwright_headless is not None:
        return bool(payload.playwright_headless)
    return bool(getattr(settings, "IMAGE_LOCALIZATION_PLAYWRIGHT_HEADLESS", True))


def _job_update(job_id: str, **kwargs: Any) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id, {})
        job.update(kwargs)
        job["job_id"] = job_id
        _jobs[job_id] = job


def _job_get(job_id: str) -> Dict[str, Any]:
    with _jobs_lock:
        return dict(_jobs.get(job_id) or {})


def _run_job(job_id: str, payload: StartImageLocalizationPayload) -> None:
    db = SessionLocal()
    try:
        _job_update(
            job_id,
            status="running",
            phase="selecting",
            message="Đang chọn sản phẩm chưa bản địa hóa...",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        limit = payload.limit or int(getattr(settings, "IMAGE_LOCALIZATION_BATCH_LIMIT", 0) or 0)
        products = products_pending_localization(db, payload.product_ids, payload.force, limit)
        total = len(products)
        queue_ids = [p.product_id for p in products]
        queue_truncated = len(queue_ids) > _JOB_QUEUE_IDS_MAX
        queue_preview = queue_ids[:_JOB_QUEUE_IDS_MAX]
        _job_update(
            job_id,
            total=total,
            current=0,
            percent=0.0,
            job_queue_product_ids=queue_preview,
            job_queue_truncated=queue_truncated,
            skipped_product_reports=[],
        )
        if total == 0:
            _job_update(
                job_id,
                status="done",
                phase="done",
                message="Không còn sản phẩm cần bản địa hóa ảnh.",
                finished_at=datetime.now(timezone.utc).isoformat(),
                percent=100.0,
                current_product_id=None,
                job_queue_product_ids=[],
                job_queue_truncated=False,
                skipped_product_reports=[],
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
            playwright_headless=payload.playwright_headless,
        )
        done = 0
        failed = 0
        skipped = 0
        consecutive_product_failures = 0
        results: List[Dict[str, Any]] = []
        skipped_reports: List[Dict[str, Any]] = []

        def should_cancel() -> bool:
            return bool(_job_get(job_id).get("cancel_requested"))

        for idx, product in enumerate(products, 1):
            if should_cancel():
                _job_update(
                    job_id,
                    status="cancelled",
                    phase="cancelled",
                    current=idx - 1,
                    percent=round(100.0 * (idx - 1) / total, 1),
                    message="Đã hủy job bản địa hóa ảnh.",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    current_product_id=None,
                    skipped_product_reports=skipped_reports[-_JOB_SKIPPED_REPORT_MAX:],
                    recent_results=results[-100:],
                )
                return
            _job_update(
                job_id,
                phase="processing",
                current=idx,
                percent=round(100.0 * (idx - 1) / total, 1),
                message=f"Đang xử lý {idx}/{total}: {product.product_id}",
                current_product_id=product.product_id,
            )
            try:
                result = service.process_product(db, product, should_cancel=should_cancel)
                status = result.get("status")
                row = {
                    "product_id": product.product_id,
                    "status": status,
                    "message": result.get("message"),
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
                        _job_update(
                            job_id,
                            status="error",
                            phase="error",
                            current=idx,
                            done=done,
                            failed=failed,
                            skipped=skipped,
                            percent=round(100.0 * idx / total, 1),
                            message=(
                                f"Dừng job: {IMAGE_LOCALIZATION_MAX_CONSECUTIVE_PRODUCT_FAILURES} "
                                f"sản phẩm lỗi liên tiếp (đến {product.product_id}, {idx}/{total}). "
                                f"{last_msgs[:750]}"
                            ),
                            finished_at=datetime.now(timezone.utc).isoformat(),
                            recent_results=results[-100:],
                            current_product_id=None,
                            skipped_product_reports=skipped_reports[-_JOB_SKIPPED_REPORT_MAX:],
                        )
                        return
                elif status == "skipped":
                    skipped += 1
                    consecutive_product_failures = 0
                    skipped_reports.append(
                        {
                            "product_id": product.product_id,
                            "message": (
                                ((result.get("message") or "").strip()[:480] or None)
                            ),
                        }
                    )
                else:
                    done += 1
                    consecutive_product_failures = 0
            except Exception as exc:
                failed += 1
                db.rollback()
                fresh = db.query(Product).filter(Product.id == product.id).first()
                if fresh is not None:
                    fresh.image_localization_status = "failed"
                    fresh.image_localization_language = payload.language
                    fresh.image_localization_error = str(exc)[:2000]
                    db.commit()
                results.append({"product_id": product.product_id, "status": "failed", "message": str(exc)})
                err_tail = str(exc)[:1000]
                if is_image_localization_fatal_dependency_error(exc):
                    _job_update(
                        job_id,
                        status="error",
                        phase="error",
                        current=idx,
                        done=done,
                        failed=failed,
                        skipped=skipped,
                        percent=round(100.0 * idx / total, 1),
                        message=(
                            "Dừng bản địa hóa ảnh vì OCR/DeepSeek lỗi bắt buộc "
                            f"(hết quota/tiền, thiếu key hoặc billing lỗi): {err_tail}"
                        ),
                        finished_at=datetime.now(timezone.utc).isoformat(),
                        recent_results=results[-100:],
                        current_product_id=None,
                        skipped_product_reports=skipped_reports[-_JOB_SKIPPED_REPORT_MAX:],
                    )
                    return
                consecutive_product_failures += 1
                if consecutive_product_failures >= IMAGE_LOCALIZATION_MAX_CONSECUTIVE_PRODUCT_FAILURES:
                    _job_update(
                        job_id,
                        status="error",
                        phase="error",
                        current=idx,
                        done=done,
                        failed=failed,
                        skipped=skipped,
                        percent=round(100.0 * idx / total, 1),
                        message=(
                            f"Dừng job: {IMAGE_LOCALIZATION_MAX_CONSECUTIVE_PRODUCT_FAILURES} "
                            f"sản phẩm lỗi liên tiếp (exception tại {product.product_id}, {idx}/{total}). {err_tail}"
                        ),
                        finished_at=datetime.now(timezone.utc).isoformat(),
                        recent_results=results[-100:],
                        current_product_id=None,
                        skipped_product_reports=skipped_reports[-_JOB_SKIPPED_REPORT_MAX:],
                    )
                    return

            _job_update(
                job_id,
                done=done,
                failed=failed,
                skipped=skipped,
                recent_results=results[-30:],
                percent=round(100.0 * idx / total, 1),
                skipped_product_reports=skipped_reports[-_JOB_SKIPPED_REPORT_MAX:],
            )

        _job_update(
            job_id,
            status="done",
            phase="done",
            current=total,
            done=done,
            failed=failed,
            skipped=skipped,
            percent=100.0,
            message=f"Hoàn tất: {done} xong, {failed} lỗi, {skipped} bỏ qua.",
            finished_at=datetime.now(timezone.utc).isoformat(),
            recent_results=results[-100:],
            current_product_id=None,
            skipped_product_reports=skipped_reports[-_JOB_SKIPPED_REPORT_MAX:],
        )
    except Exception as exc:
        _job_update(
            job_id,
            status="error",
            phase="error",
            message=str(exc),
            finished_at=datetime.now(timezone.utc).isoformat(),
            current_product_id=None,
        )
    finally:
        try:
            if "service" in locals():
                service.close()
        except Exception:
            pass
        db.close()


@router.post("/settings/gemini-cookie")
def save_cookie(
    payload: GeminiCookiePayload,
    _: AdminUser = Depends(require_module_permission("products")),
):
    count = save_gemini_cookie(payload.cookie)
    return {"success": True, "cookie_count": count}


@router.get("/settings/gemini-auth")
def check_gemini_auth(
    language: str = "vi",
    _: AdminUser = Depends(require_module_permission("products")),
):
    _pw_h = bool(getattr(settings, "IMAGE_LOCALIZATION_PLAYWRIGHT_HEADLESS", True))
    return {
        "default_gemini_mode": getattr(settings, "IMAGE_LOCALIZATION_GEMINI_MODE", "web"),
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
        # Hai cài đặt triển khai Gemini Web (Playwright trên backend)
        "playwright_headless": _pw_h,
        "playwright_browser_visible": not _pw_h,
        "deploy_browser_help": (
            "Mặc định server: IMAGE_LOCALIZATION_PLAYWRIGHT_HEADLESS=true (ẩn) hoặc false (hiện cửa sổ, cần DISPLAY/RDP). "
            "Admin có thể chọn ẩn/hiện theo từng job Gemini Web để ghi đè .env trong lần chạy đó."
        ),
        "web": GeminiWebImageAdapter(language).check_auth(),
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
        | (Product.image_localization_status.in_(["", "pending", "failed"]))
    ).count()
    localized = db.query(Product).filter(Product.image_localization_status == "localized").count()
    failed = db.query(Product).filter(Product.image_localization_status == "failed").count()
    processing = db.query(Product).filter(Product.image_localization_status == "processing").count()
    return {"pending": pending, "localized": localized, "failed": failed, "processing": processing}


@router.post("/jobs")
def start_job(
    payload: StartImageLocalizationPayload,
    _: AdminUser = Depends(require_module_permission("products")),
):
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
        else:
            web = GeminiWebImageAdapter(payload.language).check_auth()
            if not web.get("ready"):
                reason = web.get("cookie_deploy_block_reason")
                tail = (
                    " Có thể chọn ẩn/hiện Chromium ngay trong job admin (Gemini Web) hoặc dùng .env "
                    "IMAGE_LOCALIZATION_PLAYWRIGHT_HEADLESS (true = ẩn, false = hiện cửa sổ khi có DISPLAY/RDP)."
                )
                if reason:
                    detail = "[Triển khai Gemini Web] " + reason + tail
                else:
                    detail = (
                        "Chưa cấu hình cookie Gemini hoặc Chrome profile đăng nhập." + tail
                    )
                raise HTTPException(status_code=400, detail=detail)
    job_id = uuid.uuid4().hex
    _pw_eff = _effective_payload_playwright_headless(payload)
    _job_update(
        job_id,
        status="queued",
        phase="queued",
        message="Đã xếp hàng bản địa hóa ảnh.",
        created_at=datetime.now(timezone.utc).isoformat(),
        current=0,
        total=None,
        done=0,
        failed=0,
        skipped=0,
        percent=None,
        language=payload.language,
        force=payload.force,
        dry_run=payload.dry_run,
        gemini_mode=mode,
        gemini_image_model=payload.gemini_image_model,
        gemini_image_size=payload.gemini_image_size,
        openai_image_model=payload.openai_image_model,
        openai_image_quality=payload.openai_image_quality,
        openai_image_size=payload.openai_image_size,
        inference_tier=_resolve_inference_tier(payload.inference_tier),
        allow_ai_image_models=payload.allow_ai_image_models,
        local_image_only=bool(payload.allow_ai_image_models is False),
        ai_image_explicit_only=bool(getattr(settings, "IMAGE_LOCALIZATION_AI_IMAGE_EXPLICIT_ONLY", False)),
        playwright_headless_requested=payload.playwright_headless,
        playwright_headless_effective=_pw_eff,
    )
    thread = threading.Thread(target=_run_job, args=(job_id, payload), daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "queued"}


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
    _: AdminUser = Depends(require_module_permission("products")),
):
    job = _job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy job bản địa hóa ảnh")
    if job.get("status") in {"done", "error", "cancelled"}:
        return job
    _job_update(job_id, cancel_requested=True, message="Đang hủy job sau ảnh hiện tại...")
    return _job_get(job_id)


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

