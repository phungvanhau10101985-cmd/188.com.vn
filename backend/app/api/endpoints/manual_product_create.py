"""API đăng sản phẩm thủ công + AI (job + upload ảnh + studio duyệt từng ảnh)."""

from __future__ import annotations

import mimetypes
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from app.core.security import require_module_permission
from app.models.admin import AdminUser
from app.services import bunny_storage
from app.services.image_raster_jpeg import raster_bytes_to_jpeg_bytes
from app.core.config import settings
from app.services.manual_product_create_job_store import load_job, list_jobs, persist_job
from app.services.manual_product_create_service import (
    approve_studio_image,
    create_and_start_job,
    enqueue_manual_product_job,
    job_public_view,
    maybe_recover_interrupted_job,
    publish_studio_job,
    regenerate_studio_image,
    set_job_colors,
    start_studio_generate,
    validate_job_payload,
)

router = APIRouter()

_BUNNY_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_BUNNY_UPLOAD_MAX_BYTES = 15 * 1024 * 1024


class ManualProductColorItem(BaseModel):
    """Cấu trúc màu chuẩn catalog: {name, img}."""

    name: str = ""
    img: str = ""


class ManualProductJobCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    mode: str = Field(..., description="manual | ai")
    price: float
    material: str
    product_name: str = Field(
        "",
        description="Tên SP — bắt buộc mode manual; mode AI để trống thì Gemini đọc ảnh gốc đặt tên SEO",
    )
    gender: str = ""
    style: str = ""
    sizes: List[str] = Field(default_factory=list)
    no_size: bool = False
    # Chuẩn: [{name, img}]; vẫn chấp nhận chuỗi tên màu cũ
    colors: List[Union[ManualProductColorItem, str, Dict[str, Any]]] = Field(default_factory=list)
    available: int = 500
    notes: str = ""
    brand_name: Optional[str] = None
    shop_name: Optional[str] = None
    # manual slots
    main_image: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    gallery: List[str] = Field(default_factory=list)
    # AI refs (không đăng lên catalog)
    ref_image_urls: List[str] = Field(default_factory=list)
    gallery_count: int = 5
    detail_count: int = 3
    # AI image model: pro | flash | flash3 (hoặc model id đầy đủ)
    image_model: str = Field(
        "pro",
        description="Model tạo ảnh: pro (chất lượng cao) | flash (rẻ) | flash3",
    )
    aspect_ratio: str = Field(
        "1:1",
        description="Tỷ lệ khung ảnh Gemini: 1:1 | 3:4 | 4:3 | 9:16 | 16:9 …",
    )
    # none | model
    model_presence: str = Field(
        "none",
        description="Ảnh có người mẫu: none | model",
    )
    # Bắt buộc khi model_presence=model: female | male
    model_gender: str = Field(
        "",
        description="Giới tính người mẫu (bắt buộc nếu có người mẫu): female | male",
    )
    # Bắt buộc khi model_presence=model: baby | child | teen | adult | middle_aged
    model_age_group: str = Field(
        "",
        description="Độ tuổi người mẫu (bắt buộc nếu có người mẫu): baby | child | teen | adult | middle_aged",
    )
    # Bắt buộc khi model_presence=model: asian | western
    model_ethnicity: str = Field(
        "",
        description="Quốc tịch/gốc người mẫu (bắt buộc nếu có người mẫu): asian | western",
    )
    # studio | lifestyle | outdoor
    shot_style: str = Field(
        "studio",
        description="Bối cảnh: studio | lifestyle | outdoor",
    )
    # AI: bắt buộc taxonomy thành công (mặc định true)
    require_taxonomy: bool = True


class ManualProductJobOut(BaseModel):
    job_id: str
    status: str
    step: Optional[str] = None
    message: Optional[str] = None
    progress: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    vision_product_name: Optional[str] = None
    vision_colors: Optional[List[str]] = None
    studio: Optional[Dict[str, Any]] = None
    payload: Optional[Dict[str, Any]] = None
    mode: Optional[str] = None


class ManualProductJobSummary(BaseModel):
    job_id: str
    status: str
    message: Optional[str] = None
    progress: int = 0
    mode: Optional[str] = None
    product_name: Optional[str] = None
    material: Optional[str] = None
    updated_at: Optional[str] = None
    created_at: Optional[str] = None


class ManualProductColorsBody(BaseModel):
    colors: List[Union[str, ManualProductColorItem, Dict[str, Any]]] = Field(
        ...,
        description="Danh sách màu (tương thích cũ) — lấy màu đầu để tạo",
    )


class ManualProductGenerateBody(BaseModel):
    kind: str = Field(..., description="color | main | gallery | detail | material")
    name: str = Field("", description="Tên màu (tuỳ chọn — để trống thì AI đọc từ ảnh mẫu)")
    prompt: str = Field("", description="Prompt tùy chỉnh (để trống dùng gợi ý)")
    ref_urls: List[str] = Field(default_factory=list, description="Ảnh tham khảo đã chọn (≤3)")
    attach_url: str = Field("", description="Ảnh kèm upload thêm cho lần tạo này")
    image_model: str = Field("", description="pro | flash | flash3 — model Gemini tạo ảnh")
    aspect_ratio: str = Field("", description="1:1 | 3:4 | 4:3 | 9:16 | 16:9 …")


class ManualProductRegenerateBody(BaseModel):
    prompt: Optional[str] = None
    ref_urls: Optional[List[str]] = None
    attach_url: Optional[str] = None
    image_model: Optional[str] = None
    aspect_ratio: Optional[str] = None


class ManualProductUploadOut(BaseModel):
    public_url: str
    remote_path: str
    bytes: int
    purpose: str = "catalog"


def _bunny_safe_subfolder(raw: str) -> str:
    s = (raw or "").strip().strip("/")
    if not s:
        return ""
    s = re.sub(r"[^a-zA-Z0-9/_-]+", "-", s)
    s = re.sub(r"/+", "/", s).strip("/")
    return s[:120]


def _out(state: Dict[str, Any], job_id: Optional[str] = None) -> ManualProductJobOut:
    view = job_public_view(state)
    if job_id and not view.get("job_id"):
        view["job_id"] = job_id
    return ManualProductJobOut(
        job_id=str(view.get("job_id") or job_id or ""),
        status=str(view.get("status") or "unknown"),
        step=view.get("step"),
        message=view.get("message"),
        progress=int(view.get("progress") or 0),
        result=view.get("result"),
        error=view.get("error"),
        created_at=view.get("created_at"),
        updated_at=view.get("updated_at"),
        vision_product_name=view.get("vision_product_name"),
        vision_colors=view.get("vision_colors"),
        studio=view.get("studio"),
        payload=view.get("payload"),
        mode=view.get("mode"),
    )


@router.post("/upload-image", response_model=ManualProductUploadOut)
async def upload_manual_product_image(
    file: UploadFile = File(...),
    purpose: str = Form("catalog"),
    current_admin: AdminUser = Depends(require_module_permission("products")),
):
    """
    Upload ảnh lên Bunny.
    purpose=catalog — ảnh đăng SP (thủ công).
    purpose=ref — ảnh gốc tham chiếu AI (không dùng làm ảnh catalog).
    """
    _ = current_admin
    zone = (settings.BUNNY_STORAGE_ZONE_NAME or "").strip()
    key = (settings.BUNNY_STORAGE_ACCESS_KEY or "").strip()
    cdn_base = (settings.BUNNY_CDN_PUBLIC_BASE or "").strip()
    if not zone or not key or not cdn_base:
        raise HTTPException(
            status_code=503,
            detail="Chưa cấu hình Bunny CDN.",
        )
    raw = await file.read()
    if len(raw) > _BUNNY_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Ảnh quá lớn (tối đa 15MB)")
    orig_name = file.filename or "image.png"
    ext = Path(orig_name).suffix.lower()
    if ext not in _BUNNY_IMAGE_EXT:
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận JPG, PNG, GIF, WEBP")
    if ext == ".webp":
        conv = raster_bytes_to_jpeg_bytes(raw)
        if not conv:
            raise HTTPException(status_code=400, detail="Không chuyển WebP sang JPEG được")
        raw = conv
        ext = ".jpg"
        orig_name = f"{Path(orig_name).stem}.jpg"

    purpose_norm = (purpose or "catalog").strip().lower()
    if purpose_norm not in ("catalog", "ref"):
        purpose_norm = "catalog"
    folder = _bunny_safe_subfolder(
        f"manual-products/{'refs' if purpose_norm == 'ref' else 'uploads'}"
    )
    prefix = (settings.BUNNY_UPLOAD_PATH_PREFIX or "site").strip().strip("/") or "site"
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    unique = uuid.uuid4().hex[:12]
    stem = Path(orig_name).stem.lower()
    stem_safe = re.sub(r"[^a-z0-9._-]", "_", stem)[:80] or "image"
    fname = f"{stem_safe}_{unique}{ext}"
    remote = "/".join([prefix, folder, day, fname]) if folder else "/".join([prefix, day, fname])
    if ext in (".jpg", ".jpeg"):
        ct = "image/jpeg"
    else:
        ct = file.content_type or mimetypes.guess_type(fname)[0] or "application/octet-stream"
    try:
        bunny_storage.upload_file_to_zone(
            zone_name=zone,
            access_key=key,
            remote_path=remote,
            data=raw,
            content_type=ct,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    url = bunny_storage.build_public_object_url(cdn_base, remote)
    if not url:
        raise HTTPException(status_code=500, detail="Không tạo được URL public")
    return ManualProductUploadOut(
        public_url=url, remote_path=remote, bytes=len(raw), purpose=purpose_norm
    )


@router.post("/jobs", response_model=ManualProductJobOut)
def create_manual_product_job(
    body: ManualProductJobCreate,
    current_admin: AdminUser = Depends(require_module_permission("products")),
):
    payload = body.model_dump()
    try:
        validate_job_payload(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    state = create_and_start_job(payload, created_by=getattr(current_admin, "id", None))
    return _out(state)


@router.get("/jobs", response_model=List[ManualProductJobSummary])
def list_manual_product_jobs(
    active: bool = True,
    limit: int = 20,
    current_admin: AdminUser = Depends(require_module_permission("products")),
):
    """Phiên đang dở trên server (survive mất điện / restart backend)."""
    admin_id = getattr(current_admin, "id", None)
    rows = list_jobs(active_only=active, limit=min(max(1, limit), 50), created_by=admin_id)
    out: List[ManualProductJobSummary] = []
    for state in rows:
        payload = dict(state.get("payload") or {})
        pname = (
            (state.get("vision_product_name") or "").strip()
            or (payload.get("product_name") or "").strip()
        )
        out.append(
            ManualProductJobSummary(
                job_id=str(state.get("job_id") or ""),
                status=str(state.get("status") or "unknown"),
                message=state.get("message"),
                progress=int(state.get("progress") or 0),
                mode=str(payload.get("mode") or "").strip() or None,
                product_name=pname or None,
                material=(payload.get("material") or "").strip() or None,
                updated_at=state.get("updated_at"),
                created_at=state.get("created_at"),
            )
        )
    return out


@router.get("/jobs/{job_id}", response_model=ManualProductJobOut)
def get_manual_product_job(
    job_id: str,
    current_admin: AdminUser = Depends(require_module_permission("products")),
):
    _ = current_admin
    state = load_job(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Không tìm thấy job")
    state = maybe_recover_interrupted_job(state)
    return _out(state, job_id)


@router.post("/jobs/{job_id}/colors", response_model=ManualProductJobOut)
def submit_manual_product_colors(
    job_id: str,
    body: ManualProductColorsBody,
    current_admin: AdminUser = Depends(require_module_permission("products")),
):
    """Tương thích cũ: lấy màu đầu + ảnh gốc → generate color."""
    _ = current_admin
    try:
        state = set_job_colors(job_id, body.colors)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _out(state, job_id)


@router.post("/jobs/{job_id}/images/generate", response_model=ManualProductJobOut)
def generate_manual_product_image(
    job_id: str,
    body: ManualProductGenerateBody,
    current_admin: AdminUser = Depends(require_module_permission("products")),
):
    """Tạo 1 ảnh theo mốc — kèm prompt + chọn ảnh tham khảo + ảnh kèm."""
    _ = current_admin
    try:
        state = start_studio_generate(
            job_id,
            kind=body.kind,
            name=body.name,
            prompt=body.prompt,
            ref_urls=body.ref_urls,
            attach_url=body.attach_url,
            image_model=body.image_model or None,
            aspect_ratio=body.aspect_ratio or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _out(state, job_id)


@router.post("/jobs/{job_id}/images/approve", response_model=ManualProductJobOut)
def approve_manual_product_image(
    job_id: str,
    current_admin: AdminUser = Depends(require_module_permission("products")),
):
    """OK ảnh hiện tại → lưu + thêm vào pool ref → form mốc tiếp."""
    _ = current_admin
    try:
        state = approve_studio_image(job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _out(state, job_id)


@router.post("/jobs/{job_id}/images/regenerate", response_model=ManualProductJobOut)
def regenerate_manual_product_image(
    job_id: str,
    body: ManualProductRegenerateBody = ManualProductRegenerateBody(),
    current_admin: AdminUser = Depends(require_module_permission("products")),
):
    """Chưa OK → tạo lại (có thể sửa prompt / ref / ảnh kèm)."""
    _ = current_admin
    try:
        state = regenerate_studio_image(
            job_id,
            prompt=body.prompt,
            ref_urls=body.ref_urls,
            attach_url=body.attach_url,
            image_model=body.image_model,
            aspect_ratio=body.aspect_ratio,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _out(state, job_id)


@router.post("/jobs/{job_id}/publish", response_model=ManualProductJobOut)
def publish_manual_product_job(
    job_id: str,
    current_admin: AdminUser = Depends(require_module_permission("products")),
):
    """Đăng SP khi đã có ≥1 ảnh (dừng sớm được): DeepSeek + taxonomy + Ladipage."""
    _ = current_admin
    try:
        state = publish_studio_job(job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _out(state, job_id)


@router.post("/jobs/{job_id}/retry", response_model=ManualProductJobOut)
def retry_manual_product_job(
    job_id: str,
    current_admin: AdminUser = Depends(require_module_permission("products")),
):
    _ = current_admin
    state = load_job(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Không tìm thấy job")
    status = (state.get("status") or "").strip()
    if status not in ("failed", "queued"):
        raise HTTPException(status_code=400, detail="Chỉ retry job failed/queued")
    payload = dict(state.get("payload") or {})
    mode = (payload.get("mode") or "").strip().lower()
    # AI: nếu đã có studio/colors thì regenerate slot; chưa thì bootstrap lại
    studio = dict(state.get("studio") or {})
    if mode == "ai" and (studio.get("current_slot") or {}).get("kind"):
        state["status"] = "generating"
        state["step"] = "queued"
        state["message"] = "Đang tạo lại ảnh…"
        state["error"] = None
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        persist_job(job_id, state)
        enqueue_manual_product_job(job_id, worker_action="generate_slot")
    elif mode == "ai":
        state["status"] = "queued"
        state["step"] = "queued"
        state["message"] = "Đang chạy lại (đặt tên SEO)…"
        state["error"] = None
        state["progress"] = 0
        state["result"] = None
        state["worker_action"] = "bootstrap"
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        persist_job(job_id, state)
        enqueue_manual_product_job(job_id, worker_action="bootstrap")
    else:
        state["status"] = "queued"
        state["step"] = "queued"
        state["message"] = "Đang chạy lại…"
        state["error"] = None
        state["progress"] = 0
        state["result"] = None
        state["worker_action"] = "full"
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        persist_job(job_id, state)
        enqueue_manual_product_job(job_id, worker_action="full")
    fresh = load_job(job_id) or state
    return _out(fresh, job_id)
