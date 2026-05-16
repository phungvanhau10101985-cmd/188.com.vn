from __future__ import annotations

import json
import logging
import re
from io import BytesIO
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.core.config import settings
from app.core.security import require_module_permission, require_privileged_admin
from app.crud import product as product_crud
from app.crud import product_import_draft as draft_crud
from app.db.session import SessionLocal, get_db
from app.models.admin import AdminUser
from app.models.product_import_draft import ProductImportDraft
from app.schemas.import_1688 import (
    Import1688BatchResumeOut,
    Import1688BatchStatusItem,
    Import1688BatchStatusOut,
    Import1688DraftIdsBody,
    Import1688DraftListOut,
    Import1688ExcelBatchDeleteOut,
    Import1688ExcelBatchListOut,
    Import1688ExcelBatchOut,
    Import1688ExcelBatchSummaryOut,
    Import1688JobCreate,
    Import1688JobOut,
    ListingImportQueueActionMessage,
    ListingImportQueueDeleteOut,
    ListingImportQueueEnqueueIn,
    ListingImportQueueEnqueueOut,
    ListingImportQueueRunsOut,
    ProductImportDraftOut,
    ProductImportDraftUpdate,
)
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.import_link_deepseek_taxonomy import apply_deepseek_taxonomy_to_product_data
from app.services.product_rating_question_groups import apply_import_rating_question_groups_to_product_data
from app.services.product_info_web_compact import compact_product_info_for_web
from app.services.product_internal_sku import (
    ensure_import_link_internal_product_code,
    internal_sku_conflicts_global_inventory,
    internal_sku_is_valid_format,
    sync_internal_code_into_product_info,
)
from app.services.import_1688_images import ingest_1688_images
from app.services.import_hibox_scraper import (
    ImportHiboxError,
    build_canonical_product_id_from_hibox_slug,
    canonicalize_hibox_placeholder_product_id,
    extract_hibox_1688_offer_digits,
    extract_hibox_slug,
    hibox_canonical_scrape_url,
    hibox_slug_is_1688_offer,
    is_hibox_import_url,
    normalize_product_import_url,
    scrape_hibox_for_import,
)
from app.services.import_1688_scraper import (
    Import1688Error,
    build_canonical_1688_product_id,
    extract_1688_numeric_offer_id,
    extract_offer_id,
    scrape_1688_product,
)
from app.services.import_batch_url_coercion import (
    FETCH_TARGET_AUTO,
    coerce_url_for_excel_batch_import,
    normalize_fetch_target_param,
)
from app.services.import_link_excel_batch import merge_import_excel_overlay_into_product_data, parse_link_import_excel

logger = logging.getLogger(__name__)
router = APIRouter()

# Tránh hai luồng cùng chạy một batch (bấm «Chạy tiếp» hai lần hoặc startup + thủ công).
_batch_chain_lock = threading.Lock()
_batch_tokens_running: set[str] = set()


def _draft_import_status_terminal(status: Optional[str]) -> bool:
    s = (status or "").lower().strip()
    return s in {"done", "published", "error"}


def _import_static_uploads() -> Path:
    return Path(__file__).resolve().parents[2] / "static" / "uploads"


def _batch_meta_json_path(batch_token: str) -> Path:
    d = _import_static_uploads() / "import_batches"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{batch_token}.json"


def _safe_batch_token_param(raw: str) -> str:
    t = (raw or "").strip().lower()
    if not re.fullmatch(r"[a-f0-9]{8,128}", t):
        raise HTTPException(status_code=400, detail="batch_token không hợp lệ.")
    return t


def _batch_status_out_for_draft_ids(db: Session, batch_token: str, draft_ids: List[int]) -> Import1688BatchStatusOut:
    """Tổng hợp trạng thái đợt theo thứ tự draft_ids trong meta (1 truy vấn IN)."""
    ids = [int(x) for x in draft_ids if x is not None]
    if not ids:
        return Import1688BatchStatusOut(
            batch_token=batch_token,
            total=0,
            completed=0,
            failed=0,
            pending=0,
            items=[],
        )
    rows = db.query(ProductImportDraft).filter(ProductImportDraft.id.in_(ids)).all()
    by_id = {r.id: r for r in rows}
    items_out: List[Import1688BatchStatusItem] = []
    completed = 0
    failed = 0
    pending = 0
    for did in ids:
        draft = by_id.get(did)
        if not draft:
            continue
        st = (draft.status or "").lower()
        if st in {"done", "published"}:
            completed += 1
        elif st == "error":
            failed += 1
        else:
            pending += 1
        xr = None
        ov = getattr(draft, "excel_overlays", None)
        if isinstance(ov, dict) and ov.get("_excel_row") is not None:
            try:
                xr = int(ov["_excel_row"])
            except (TypeError, ValueError):
                xr = None
        items_out.append(
            Import1688BatchStatusItem(
                draft_id=draft.id,
                job_id=draft.job_id,
                excel_row=xr,
                status=draft.status,
                phase=draft.phase,
                message=draft.message,
            )
        )
    return Import1688BatchStatusOut(
        batch_token=batch_token,
        total=len(ids),
        completed=completed,
        failed=failed,
        pending=pending,
        items=items_out,
    )


def _infer_import_source_for_url(norm_url: str, requested_source: Optional[str] = None) -> Tuple[str, str]:
    """Trả (external_id, source). Raises ValueError nếu không phải 1688/Hibox."""
    req = (requested_source or "").strip().lower()
    force_hibox = req in {"hibox", "hi-box", "hi_box"} or "hibox.mn" in norm_url.lower()
    if force_hibox or is_hibox_import_url(norm_url):
        return (extract_hibox_slug(norm_url) or "hibox_import"), "hibox"
    offer_id = extract_offer_id(norm_url)
    if offer_id:
        return offer_id, "1688"
    raise ValueError("unsupported_import_link")


def _excel_export_columns_and_vi_headers() -> Tuple[List[str], List[str]]:
    """
    Trùng thứ tự với template / file 39 cột (sau `product_info` thêm tên tiếng Trung, shop Trung Quốc).
    """
    columns = [
        "id",
        "sku",
        "origin",
        "brand",
        "name",
        "pro_content",
        "price",
        "shop_name",
        "shop_id",
        "pro_lower_price",
        "pro_high_price",
        "rating_group_id",
        "question_group_id",
        "sizes",
        "Variant",
        "gallery_images",
        "detail_images",
        "product_url",
        "video_url",
        "main_image",
        "likes_count",
        "purchases_count",
        "reviews_count",
        "questions_count",
        "rating_score",
        "stock_quantity",
        "deposit_required",
        "Main Category",
        "Subcategory",
        "Sub-subcategory",
        "Material",
        "Style",
        "Color",
        "Occasion",
        "Features",
        "Weight",
        "product_info",
        "chinese_name",
        "shop_name_chinese",
    ]
    vietnamese_headers = [
        "Id sản phẩm",
        "Mã sản phẩm",
        "Xuất xứ",
        "Thương hiệu",
        "Tên",
        "Mô tả sản phẩm",
        "Giá",
        "Tên shop",
        "Shop id",
        "Sp giá thấp hơn",
        "Sp giá cao hơn",
        "Nhóm đánh giá",
        "Nhóm câu hỏi",
        "Size",
        "Biến thể",
        "Thư viện ảnh",
        "Nội dung",
        "Link mặc định",
        "Link Video",
        "Link img",
        "Thích",
        "Mua",
        "Lượt đánh giá",
        "Lượt hỏi",
        "Điểm đánh giá",
        "Số lượng có thể mua",
        "Cần đặt cọc",
        "Danh mục cấp 1",
        "Danh mục cấp 2",
        "Danh mục cấp 3",
        "Chất liệu",
        "Kiểu dáng",
        "màu sắc",
        "Dịp",
        "Tính năng",
        "Trọng lượng",
        "Thông tin sản phẩm",
        "Tên tiếng trung",
        "Shop Trung Quốc",
    ]
    return columns, vietnamese_headers


def _merge_excel_overlay_for_job(db: Session, job_id: str, product_data: Dict[str, Any]) -> None:
    d = draft_crud.get_by_job_id(db, job_id)
    ov = getattr(d, "excel_overlays", None) if d else None
    merge_import_excel_overlay_into_product_data(product_data, ov)


def _run_import_1688_chain_from_meta(meta_path_str: str) -> None:
    """
    Chạy tuần tự job trong file meta.
    Bỏ qua draft đã done / published / error — dùng sau restart hoặc «Chạy tiếp».
    """
    p = Path(meta_path_str)
    if not p.is_file():
        logger.warning("import batch meta không tồn tại: %s", meta_path_str)
        return
    token = p.stem
    with _batch_chain_lock:
        if token in _batch_tokens_running:
            logger.info("import batch chain đang chạy — bỏ qua lần gọi trùng: %s…", token[:12])
            return
        _batch_tokens_running.add(token)
    try:
        try:
            meta = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("import batch meta lỗi đọc: %s — %s", meta_path_str, exc)
            return
        job_ids = meta.get("job_ids") or []
        for jid in job_ids:
            if not (isinstance(jid, str) and jid.strip()):
                continue
            jid = jid.strip()
            db = SessionLocal()
            try:
                draft = draft_crud.get_by_job_id(db, jid)
                if draft is not None and _draft_import_status_terminal(draft.status):
                    continue
            finally:
                db.close()
            try:
                _run_import_1688_job(jid, False)
            except Exception:
                logger.exception(
                    "import batch chain: job lỗi không mong đợi (tiếp tục các job sau): job_id=%s…",
                    (jid[:16] if jid else ""),
                )
    finally:
        with _batch_chain_lock:
            _batch_tokens_running.discard(token)


def _resume_all_batches_pending_after_startup() -> None:
    """Quét mọi file meta; chạy tiếp batch còn pending (sau delay — gọi từ thread daemon)."""
    import time

    time.sleep(2.5)
    base = _import_static_uploads() / "import_batches"
    if not base.is_dir():
        return
    for fp in sorted(base.glob("*.json"), key=lambda p: p.stat().st_mtime):
        db = SessionLocal()
        try:
            try:
                meta = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                continue
            draft_ids = [int(x) for x in (meta.get("draft_ids") or []) if x is not None]
            st = _batch_status_out_for_draft_ids(db, fp.stem, draft_ids)
        finally:
            db.close()
        if st.pending <= 0:
            continue
        try:
            logger.info(
                "IMPORT_1688_BATCH_RESUME_ON_STARTUP: token=%s… pending=%s",
                fp.stem[:12],
                st.pending,
            )
            _run_import_1688_chain_from_meta(str(fp.resolve()))
        except Exception:
            logger.exception("batch resume on startup failed: %s", fp)


def start_import_batch_resume_daemon_if_enabled() -> None:
    """Gọi từ main.startup khi IMPORT_1688_BATCH_RESUME_ON_STARTUP=true."""
    if not getattr(settings, "IMPORT_1688_BATCH_RESUME_ON_STARTUP", False):
        return
    t = threading.Thread(
        target=_resume_all_batches_pending_after_startup,
        daemon=True,
        name="import1688-batch-resume-startup",
    )
    t.start()


def _apply_deepseek_taxonomy_after_scrape(db: Session, product_data: Dict[str, Any], warnings: List[str]) -> None:
    try:
        warnings.extend(apply_deepseek_taxonomy_to_product_data(db, product_data))
    except Exception as exc:
        logger.warning("import link DeepSeek taxonomy: %s", exc)
        warnings.append(f"deepseek_taxonomy: lỗi không mong đợi — {type(exc).__name__}: {exc}")
    apply_import_rating_question_groups_to_product_data(product_data, warnings)


@router.get("/debug/classify-url")
def debug_classify_import_url(
    url: str = Query(..., min_length=1, max_length=4096, description="URL dán thử (1688 hoặc Hibox)"),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """
    Không tạo job — chỉ trả kết quả chuẩn hóa + nhận dạng để debug 400 Bad Request.
    Mở trong trình duyệt (đã đăng nhập admin) hoặc gọi có Bearer token.
    """
    raw = url.strip()
    normalized = normalize_product_import_url(raw)
    hibox = is_hibox_import_url(normalized)
    slug = extract_hibox_slug(normalized) if hibox else None
    hibox_scrape = hibox_canonical_scrape_url(normalized) if hibox else None
    oid = extract_offer_id(normalized)
    short = len(normalized) < 10
    accepted = (not short) and (hibox or bool(oid))
    return {
        "received_length": len(raw),
        "normalized": normalized,
        "normalized_length": len(normalized),
        "is_hibox": hibox,
        "hibox_slug": slug,
        "hibox_canonical_scrape_url": hibox_scrape,
        "offer_id_1688": oid,
        "would_accept_for_post_jobs": accepted,
        "reject_reason": (
            "url_too_short"
            if short
            else ("ok" if accepted else "unsupported_import_link")
        ),
    }


class Import1688CookieSettingsIn(BaseModel):
    cookie_text: str


class Import1688CookieSettingsOut(BaseModel):
    enabled: bool
    cookie_file: str | None = None
    has_cookie: bool
    cookie_count: int
    cookie_names: List[str] = []
    message: str | None = None


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_cookie_file() -> Path:
    return _backend_root() / "1688-cookies.json"


def _env_local_file() -> Path:
    return _backend_root() / ".env.local"


def _cookie_items_from_text(cookie_text: str) -> List[Dict[str, Any]]:
    text = (cookie_text or "").strip()
    if not text:
        return []
    if text.lstrip().startswith(("[", "{")):
        data = json.loads(text)
        cookies = data.get("cookies") if isinstance(data, dict) else data
        if not isinstance(cookies, list):
            raise ValueError("JSON cookie phải là list hoặc object có key cookies.")
        out = []
        for item in cookies:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            c = dict(item)
            c["name"] = str(c.get("name") or "").strip()
            c["value"] = str(c.get("value") or "")
            c.setdefault("domain", ".1688.com")
            c.setdefault("path", "/")
            same_site = c.get("sameSite")
            if same_site is not None:
                normalized = str(same_site).strip().lower().replace("-", "_")
                same_site_map = {
                    "strict": "Strict",
                    "lax": "Lax",
                    "none": "None",
                    "no_restriction": "None",
                }
                if normalized in same_site_map:
                    c["sameSite"] = same_site_map[normalized]
                else:
                    c.pop("sameSite", None)
            out.append(c)
        return out
    out = []
    for part in text.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        if name:
            out.append({"name": name, "value": value.strip(), "domain": ".1688.com", "path": "/"})
    return out


def _read_cookie_items() -> List[Dict[str, Any]]:
    raw = (getattr(settings, "IMPORT_1688_COOKIE_JSON", "") or "").strip()
    cookie_file = (getattr(settings, "IMPORT_1688_COOKIE_FILE", "") or "").strip()
    if raw:
        try:
            return _cookie_items_from_text(raw)
        except Exception:
            return []
    if cookie_file:
        path = Path(cookie_file)
        if not path.is_absolute():
            path = _backend_root() / path
        if path.exists():
            try:
                return _cookie_items_from_text(path.read_text(encoding="utf-8"))
            except Exception:
                return []
    return []


def _upsert_env_local(values: Dict[str, str]) -> None:
    path = _env_local_file()
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = existing.splitlines()
    handled = set()
    next_lines = []
    for line in lines:
        replaced = False
        for key, value in values.items():
            if re.match(rf"^\s*{re.escape(key)}\s*=", line):
                next_lines.append(f"{key}={value}")
                handled.add(key)
                replaced = True
                break
        if not replaced:
            next_lines.append(line)
    for key, value in values.items():
        if key not in handled:
            next_lines.append(f"{key}={value}")
    path.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")


def _cookie_settings_out(message: str | None = None) -> Import1688CookieSettingsOut:
    cookies = _read_cookie_items()
    names = [str(c.get("name") or "") for c in cookies if c.get("name")]
    return Import1688CookieSettingsOut(
        enabled=bool(getattr(settings, "IMPORT_1688_ENABLED", True)),
        cookie_file=(getattr(settings, "IMPORT_1688_COOKIE_FILE", "") or None),
        has_cookie=bool(cookies),
        cookie_count=len(cookies),
        cookie_names=names[:30],
        message=message,
    )


def _restart_process_later() -> None:
    import os as _os
    import time as _time

    _time.sleep(0.8)
    _os._exit(0)


def _to_job_out(draft) -> Import1688JobOut:
    return Import1688JobOut(
        job_id=draft.job_id,
        status=draft.status,
        phase=draft.phase,
        message=draft.message,
        percent=draft.percent,
        draft_id=draft.id,
        product_data=draft.product_data,
        errors=draft.errors or [],
        warnings=draft.warnings or [],
        published_product_id=draft.published_product_id,
        created_at=draft.created_at,
        finished_at=draft.finished_at,
    )


@router.get("/settings/cookie", response_model=Import1688CookieSettingsOut)
def get_import_1688_cookie_settings(
    _: AdminUser = Depends(require_privileged_admin),
):
    return _cookie_settings_out()


@router.put("/settings/cookie", response_model=Import1688CookieSettingsOut)
def save_import_1688_cookie_settings(
    payload: Import1688CookieSettingsIn,
    _: AdminUser = Depends(require_privileged_admin),
):
    try:
        cookies = _cookie_items_from_text(payload.cookie_text)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cookie không hợp lệ: {exc}") from exc
    if not cookies:
        raise HTTPException(status_code=400, detail="Cookie trống hoặc không đọc được name=value.")

    cookie_file = _default_cookie_file()
    cookie_file.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
    _upsert_env_local(
        {
            "IMPORT_1688_COOKIE_FILE": cookie_file.name,
            "IMPORT_1688_COOKIE_JSON": "",
            "IMPORT_1688_ENABLED": "true",
        }
    )

    # Cập nhật ngay trong tiến trình hiện tại; restart vẫn hữu ích để đồng bộ mọi worker/process.
    settings.IMPORT_1688_COOKIE_FILE = cookie_file.name
    settings.IMPORT_1688_COOKIE_JSON = ""
    settings.IMPORT_1688_ENABLED = True
    return _cookie_settings_out("Đã lưu cookie 1688. Có thể import ngay hoặc restart API để đồng bộ process.")


@router.post("/settings/restart-api")
def restart_import_1688_api(
    background_tasks: BackgroundTasks,
    _: AdminUser = Depends(require_privileged_admin),
):
    background_tasks.add_task(_restart_process_later)
    return {
        "success": True,
        "message": "API sẽ tự thoát trong giây lát. PM2/systemd/Docker cần tự khởi động lại process.",
    }


def _coerce_colors_for_create(colors: Any) -> List[Dict[str, Any]]:
    """ProductCreate.colors là List[Dict]; Excel/import thường là list[str] hoặc list[dict]."""
    if not colors:
        return []
    out: List[Dict[str, Any]] = []
    for c in colors:
        if isinstance(c, dict):
            d = dict(c)
            d.pop("label", None)
            out.append(d)
        elif c is None:
            continue
        else:
            s = str(c).strip()
            if s:
                out.append({"name": s})
    return out


def _publish_payload(product_data: Dict[str, Any]) -> Dict[str, Any]:
    allowed = set(ProductCreate.model_fields.keys())
    payload = {k: v for k, v in (product_data or {}).items() if k in allowed}
    payload.setdefault("is_active", True)
    payload.setdefault("features", [])
    payload.setdefault("sizes", [])
    payload.setdefault("colors", [])
    payload.setdefault("images", [])
    payload.setdefault("gallery", [])
    payload.setdefault("price", 0)
    payload.setdefault("available", 500)
    required_missing = [k for k in ("product_id", "name") if not payload.get(k)]
    if required_missing:
        raise HTTPException(status_code=400, detail=f"Draft thiếu trường bắt buộc: {', '.join(required_missing)}")
    required_category_labels = {
        "category": "danh mục cấp 1",
        "subcategory": "danh mục cấp 2",
        "sub_subcategory": "danh mục cấp 3",
    }
    missing_categories = [
        label
        for key, label in required_category_labels.items()
        if not str(payload.get(key) or "").strip() or str(payload.get(key) or "").strip().lower() == "nan"
    ]
    if missing_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Draft thiếu {', '.join(missing_categories)} — không cho import sản phẩm.",
        )
    payload["colors"] = _coerce_colors_for_create(payload.get("colors"))
    # Khớp nghiệp vụ + cột Excel mẫu (=1): lưu DB dạng bool; draft/export dùng số 1/0.
    payload["deposit_require"] = True
    return payload


def _assign_internal_sku_to_import_product_data(
    db: Session,
    product_data: Dict[str, Any],
    *,
    exclude_draft_id: Optional[int] = None,
    batch_reserved: Optional[Set[str]] = None,
) -> None:
    """
    SKU đăng web là [A-Z][0-9]{4}, không phải slug Hibox (vd abb-922386436529).
    Ưu tiên mã vừa xuất file (TTL internal_sku_exports); không trùng SP / nháp khác / ô sheet SKU (định dạng nội bộ).
    Đồng bộ vào product_info.product_info.sku cho tab AK.
    """
    sku = ensure_import_link_internal_product_code(
        db,
        product_data.get("code"),
        exclude_product_id=None,
        exclude_draft_id=exclude_draft_id,
        batch_reserved=batch_reserved,
    )
    product_data["code"] = sku
    product_data["product_info"] = sync_internal_code_into_product_info(
        product_data.get("product_info"), sku
    )
    canonicalize_hibox_placeholder_product_id(product_data)
    compact_product_info_for_web(product_data)


def _draft_product_data_for_excel_export(
    db: Session,
    draft: ProductImportDraft,
    *,
    sku_fix_pending: Optional[List[Tuple[ProductImportDraft, Dict[str, Any]]]] = None,
    batch_reserved: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Trước khi xuất Excel: SKU phải đúng [A-Z][0-9]{4}, không được *0000, không trùng products.code
    của sản phẩm khác (trừ bản ghi đã publish từ chính nháp này).
    Nếu không → gán lại như lúc import và lưu vào draft.

    `sku_fix_pending` + `batch_reserved`: khi xuất hàng loạt, gom cập nhật DB một lần (tránh trăm lần commit).
    """
    pd = dict(draft.product_data or {})
    raw_code = pd.get("code")
    if raw_code is None:
        code_str = ""
    else:
        code_str = str(raw_code).strip()
    exclude_pid = None
    pub_pid = (draft.published_product_id or "").strip()
    if pub_pid:
        existing_pub = product_crud.get_product_by_product_id(db, pub_pid)
        if existing_pub is not None:
            exclude_pid = existing_pub.id
    needs_fix = not internal_sku_is_valid_format(code_str) or internal_sku_conflicts_global_inventory(
        db,
        code_str,
        exclude_product_id=exclude_pid,
        exclude_draft_id=draft.id,
    )
    if needs_fix:
        _assign_internal_sku_to_import_product_data(
            db,
            pd,
            exclude_draft_id=draft.id,
            batch_reserved=batch_reserved,
        )
        if sku_fix_pending is not None:
            sku_fix_pending.append((draft, pd))
        else:
            draft_crud.update_draft(db, draft, product_data=pd)
    return pd


def _excel_row_from_product(product_data: Dict[str, Any]) -> Dict[str, Any]:
    def j(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    def _style_cell_from_pd(pd: Dict[str, Any]) -> str:
        v = pd.get("style", "")
        if v is None:
            return ""
        return str(v).strip() if not isinstance(v, str) else v.strip()

    style_cell = _style_cell_from_pd(product_data)

    # Cột Excel mẫu 39 cột (sau AK: tên tiếng Trung, shop Trung Quốc) —
    # ảnh nguồn vẫn nằm trong product_data / JSON khi cần đối chiếu.
    # H–K để trống trên file Excel xuất ra (Kiểu dáng vẫn ở cột Style).
    return {
        "id": product_data.get("product_id", ""),
        "sku": product_data.get("code", ""),
        "origin": "",
        "brand": "",
        "name": product_data.get("name", ""),
        "pro_content": (product_data.get("description") or ""),
        "price": product_data.get("price", 0),
        "shop_name": "",
        "shop_id": "",
        "pro_lower_price": "",
        "pro_high_price": "",
        "rating_group_id": product_data.get("group_rating", 0),
        "question_group_id": product_data.get("group_question", 0),
        "sizes": j(product_data.get("sizes", [])),
        "Variant": j(product_data.get("colors", [])),
        "gallery_images": j(product_data.get("images", [])),
        "detail_images": j(product_data.get("gallery", [])),
        "product_url": product_data.get("link_default", ""),
        "video_url": product_data.get("video_link", ""),
        "main_image": product_data.get("main_image", ""),
        "likes_count": product_data.get("likes", 0),
        "purchases_count": product_data.get("purchases", 0),
        "reviews_count": product_data.get("rating_total", 0),
        "questions_count": product_data.get("question_total", 0),
        "rating_score": product_data.get("rating_point", 0),
        "stock_quantity": product_data.get("available", 500),
        "deposit_required": product_crud.deposit_require_to_excel_int(
            product_data.get("deposit_require"), default=1
        ),
        "Main Category": product_data.get("category", ""),
        "Subcategory": product_data.get("subcategory", ""),
        "Sub-subcategory": product_data.get("sub_subcategory", ""),
        "Material": (product_data.get("material") or ""),
        "Style": style_cell,
        "Color": product_data.get("color", ""),
        "Occasion": product_data.get("occasion", ""),
        "Features": j(product_data.get("features", [])),
        "Weight": product_data.get("weight", ""),
        "product_info": j(product_data.get("product_info", {})),
        "chinese_name": product_data.get("chinese_name", "") or "",
        "shop_name_chinese": product_data.get("shop_name_chinese", "") or "",
    }


def _run_import_1688_job(job_id: str, download_images: bool) -> None:
    db = SessionLocal()
    try:
        draft = draft_crud.get_by_job_id(db, job_id)
        if not draft:
            return
        norm_url = normalize_product_import_url(draft.source_url or "")
        saved_source = (draft.source or "1688").strip().lower()
        if saved_source == "hibox" or "hibox.mn" in norm_url.lower() or is_hibox_import_url(norm_url):
            source = "hibox"
        else:
            source = saved_source

        if source == "hibox":
            draft_crud.mark_running(db, draft, "scraping", "Đang mở trang Hibox bằng Playwright...", 15)
            raw_payload, product_data, warnings = scrape_hibox_for_import(draft.source_url)
            _apply_deepseek_taxonomy_after_scrape(db, product_data, warnings)
            _merge_excel_overlay_for_job(db, job_id, product_data)
            _assign_internal_sku_to_import_product_data(db, product_data, exclude_draft_id=draft.id)
            draft_crud.mark_done(
                db,
                draft,
                raw_payload=raw_payload,
                product_data=product_data,
                warnings=warnings,
                success_message="Đã tạo bản nháp từ link Hibox.",
            )
            return

        draft_crud.mark_running(db, draft, "scraping", "Đang mở link 1688 bằng Playwright...", 15)
        raw_payload, product_data, warnings = scrape_1688_product(draft.source_url)
        _apply_deepseek_taxonomy_after_scrape(db, product_data, warnings)

        draft = draft_crud.get_by_job_id(db, job_id)
        if not draft:
            return
        if download_images:
            draft_crud.mark_running(db, draft, "images", "Đang tải ảnh sản phẩm về CDN...", 70)
            product_data, image_warnings = ingest_1688_images(product_data, draft.source_offer_id)
            warnings.extend(image_warnings)

        _merge_excel_overlay_for_job(db, job_id, product_data)
        _assign_internal_sku_to_import_product_data(db, product_data, exclude_draft_id=draft.id)
        draft = draft_crud.get_by_job_id(db, job_id)
        if not draft:
            return
        draft_crud.mark_done(
            db,
            draft,
            raw_payload=raw_payload,
            product_data=product_data,
            warnings=warnings,
            success_message="Đã tạo bản nháp từ link 1688.",
        )
    except ImportHiboxError as exc:
        draft = draft_crud.get_by_job_id(db, job_id)
        if draft:
            draft_crud.mark_error(db, draft, message=str(exc), errors=[str(exc)])
    except Import1688Error as exc:
        draft = draft_crud.get_by_job_id(db, job_id)
        if draft:
            draft_crud.mark_error(db, draft, message=str(exc), errors=[str(exc)])
    except (ValueError, RuntimeError) as exc:
        draft = draft_crud.get_by_job_id(db, job_id)
        if draft:
            draft_crud.mark_error(db, draft, message=str(exc), errors=[str(exc)])
    except Exception as exc:
        draft = draft_crud.get_by_job_id(db, job_id)
        tb_lines = [ln for ln in traceback.format_exc().splitlines() if ln.strip()][-30:]
        if draft:
            draft_crud.mark_error(
                db,
                draft,
                message=f"Import draft thất bại: {exc}",
                errors=[f"{type(exc).__name__}: {exc}", *tb_lines],
            )
    finally:
        db.close()


@router.post("/jobs")
def create_import_1688_job(
    payload: Import1688JobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_module_permission("products")),
):
    source_url = normalize_product_import_url(payload.url.strip())
    if len(source_url) < 10:
        raise HTTPException(
            status_code=400,
            detail={
                "reason": "url_too_short",
                "message": "URL quá ngắn hoặc rỗng sau khi chuẩn hóa. Dán lại đúng link đầy đủ.",
                "normalized_length": len(source_url),
            },
        )

    try:
        ext_id, src = _infer_import_source_for_url(source_url, payload.source)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={
                "reason": "unsupported_import_link",
                "message": (
                    "Không nhận dạng được link là 1688 (offerId) hay Hibox / mirror taobao1688.kz (id=…)."
                ),
                "normalized_length": len(source_url),
                "normalized_preview": source_url[:200],
                "hints": (
                    "1688: có offer/xxxxxxxx.html hoặc ?offerId= (mobile: detail.m.1688.com/page/index.html?offerId=). "
                    "Hibox: https://hibox.mn/v/{mã}. Mirror: https://taobao1688.kz/item?id={mã}. "
                    "Nếu đúng là Hibox mà vẫn báo lỗi: API đang chạy có thể là bản cũ — restart backend và kiểm tra "
                    "bạn không gọi nhầm instance (hay gặp: Next dev ép cổng khác SERVER_PORT — xem frontend/.env.local (API_INTERNAL_ORIGIN, NEXT_PUBLIC_API_BASE_URL) và restart Next + backend."
                ),
            },
        )
    job_id = str(uuid.uuid4())
    draft = draft_crud.create_draft(
        db,
        job_id=job_id,
        source_url=source_url,
        source_offer_id=ext_id,
        created_by=getattr(admin, "id", None),
        source=src,
    )
    # Import từ link cần giữ URL ảnh gốc để admin kiểm tra/export đúng nguồn.
    # Không tự tải ảnh về Bunny trong luồng draft này.
    background_tasks.add_task(_run_import_1688_job, job_id, False)
    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "draft_id": draft.id,
            "message": "Đã nhận link. Dùng GET /import-1688/jobs/{job_id} để theo dõi.",
            "poll_url": f"/api/v1/import-1688/jobs/{job_id}",
        },
    )


@router.post("/jobs/batch-from-excel", response_model=Import1688ExcelBatchOut)
async def create_import_jobs_batch_from_excel(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    fetch_target: str = Form("auto"),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_module_permission("products")),
):
    """
    File .xlsx — **chỉ** mẫu tái nhập listing (hai dòng nhãn đầu): bắt buộc tiêu đề có **Link** (vd. Link SP)
    và **Giá Tệ / China price**. Không nhận cột giá VND (Q), cột G, khối L–O hay layout đặt hàng Excel cũ.

    **`price`** trên nháp luôn suy từ CN¥ × hệ_số_IF × `LISTING_IMPORT_VND_PER_CNY` (hoặc cột `vnd_per_cny_used`),
    rồi làm tròn lên bội 10.000 ₫.
    **Mã sp** chỉ khi có cột tiêu đề «Mã sp» đúng `[A-Z][0-9]{4}` — không đọc cột B cố định.

    Form **`fetch_target`**: `auto` (mặc định) | `hibox` | `1688` | `cssbuy` — ép link từng dòng về đúng định dạng trước khi tạo job
    (vd. 1688 offer → `hibox.mn/v/abb-…` khi chọn Hibox; slug `abb-*` trên Hibox → `detail.1688.com` khi chọn 1688).
    Dòng không quy đổi được bị **bỏ qua** kèm lý do trong `skipped`.
    """
    name = (file.filename or "").lower()
    if not name.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file .xlsx / .xlsm")

    uploads = _import_static_uploads()
    uploads.mkdir(parents=True, exist_ok=True)
    tmp_name = f"excel_batch_upload_{uuid.uuid4().hex}.xlsx"
    tmp_path = uploads / tmp_name
    try:
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="File rỗng")
        tmp_path.write_bytes(raw)
        parsed, pskip = parse_link_import_excel(tmp_path)
        skips = list(pskip)

        ft = normalize_fetch_target_param(fetch_target)

        batch_token = uuid.uuid4().hex
        draft_ids: List[int] = []
        job_ids: List[str] = []

        for it in parsed:
            url_norm = normalize_product_import_url(it["url"])
            if len(url_norm) < 10:
                skips.append(f"Dòng {it.get('excel_row')}: URL quá ngắn.")
                continue
            if ft != FETCH_TARGET_AUTO:
                coerced, skip_reason = coerce_url_for_excel_batch_import(url_norm, ft)
                if skip_reason:
                    skips.append(f"Dòng {it.get('excel_row')}: {skip_reason}")
                    continue
                url_norm = normalize_product_import_url(coerced)
                if len(url_norm) < 10:
                    skips.append(f"Dòng {it.get('excel_row')}: URL sau chuẩn hoá quá ngắn.")
                    continue
            try:
                ext_id, src = _infer_import_source_for_url(url_norm, None)
            except ValueError:
                skips.append(f"Dòng {it.get('excel_row')}: link không nhận dạng 1688/Hibox.")
                continue
            overlays = dict(it.get("overlays") or {})
            overlays["_excel_row"] = int(it["excel_row"])
            overlays["_batch_token"] = batch_token
            jid = str(uuid.uuid4())
            draft = draft_crud.create_draft(
                db,
                job_id=jid,
                source_url=url_norm,
                source_offer_id=ext_id,
                created_by=getattr(admin, "id", None),
                source=src,
                excel_overlays=overlays,
            )
            draft_ids.append(draft.id)
            job_ids.append(jid)

        meta_path = _batch_meta_json_path(batch_token)
        meta_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "job_ids": job_ids,
                    "draft_ids": draft_ids,
                    "skipped": skips[-80:],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        if job_ids:
            background_tasks.add_task(_run_import_1688_chain_from_meta, str(meta_path.absolute()))

        return Import1688ExcelBatchOut(
            batch_token=batch_token,
            total=len(job_ids),
            draft_ids=draft_ids,
            job_ids=job_ids,
            skipped=skips[:120],
        )
    finally:
        try:
            if tmp_path.is_file():
                tmp_path.unlink()
        except Exception:
            pass


@router.get("/jobs/excel-batches", response_model=Import1688ExcelBatchListOut)
def list_excel_import_batches(
    limit: int = Query(40, ge=1, le=120),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Danh sách các đợt import Excel (theo file meta), mới nhất trước."""
    d = _import_static_uploads() / "import_batches"
    if not d.is_dir():
        return Import1688ExcelBatchListOut(items=[], limit=limit)
    files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    summaries: List[Import1688ExcelBatchSummaryOut] = []
    for fp in files:
        token = fp.stem
        try:
            meta = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        draft_ids = [int(x) for x in (meta.get("draft_ids") or []) if x is not None]
        skipped = meta.get("skipped")
        skipped_n = len(skipped) if isinstance(skipped, list) else 0
        st = _batch_status_out_for_draft_ids(db, token, draft_ids)
        ca_raw = meta.get("created_at")
        created_at_out: Optional[str] = None
        if isinstance(ca_raw, str) and ca_raw.strip():
            created_at_out = ca_raw.strip()
        else:
            try:
                created_at_out = datetime.fromtimestamp(fp.stat().st_mtime, tz=timezone.utc).isoformat()
            except OSError:
                created_at_out = None
        summaries.append(
            Import1688ExcelBatchSummaryOut(
                batch_token=token,
                created_at=created_at_out,
                total_links=st.total,
                completed=st.completed,
                failed=st.failed,
                pending=st.pending,
                skipped_lines=skipped_n,
            ),
        )
    return Import1688ExcelBatchListOut(items=summaries, limit=limit)


@router.delete("/jobs/excel-batches/{batch_token}", response_model=Import1688ExcelBatchDeleteOut)
def delete_excel_import_batch(
    batch_token: str,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Xóa file meta đợt và toàn bộ bản nháp (draft) liệt kê trong meta."""
    tid = _safe_batch_token_param(batch_token)
    meta_path = _batch_meta_json_path(tid)
    if not meta_path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy đợt import (file meta).")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Meta batch hỏng: {exc}") from exc

    draft_ids = [int(x) for x in (meta.get("draft_ids") or []) if x is not None]
    deleted_ids: List[int] = []
    for did in draft_ids:
        if draft_crud.delete_draft_by_id(db, did):
            deleted_ids.append(did)

    meta_removed = False
    try:
        meta_path.unlink()
        meta_removed = True
    except OSError:
        logger.warning("Không xóa được file meta batch: %s", meta_path)

    return Import1688ExcelBatchDeleteOut(
        success=True,
        batch_token=tid,
        draft_ids_deleted=deleted_ids,
        meta_removed=meta_removed,
    )


@router.post("/jobs/excel-batches/{batch_token}/resume", response_model=Import1688BatchResumeOut)
def resume_excel_import_batch_chain(
    batch_token: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """
    Chạy tiếp các link trong đợt upload Excel còn queued/running (sau restart hoặc lỗi tạm).
    Draft đã done / published / error được bỏ qua.
    """
    tid = _safe_batch_token_param(batch_token)
    meta_path = _batch_meta_json_path(tid)
    if not meta_path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy đợt import (file meta).")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Meta batch hỏng: {exc}") from exc
    draft_ids = [int(x) for x in (meta.get("draft_ids") or []) if x is not None]
    st = _batch_status_out_for_draft_ids(db, tid, draft_ids)
    if st.pending <= 0:
        return Import1688BatchResumeOut(
            success=True,
            message="Không còn link chờ xử lý (mọi draft đã xong hoặc lỗi).",
            pending=0,
        )
    with _batch_chain_lock:
        if tid in _batch_tokens_running:
            return Import1688BatchResumeOut(
                success=True,
                message="Đợt này đang chạy trên server — chờ vài giây rồi làm mới.",
                pending=st.pending,
            )
    background_tasks.add_task(_run_import_1688_chain_from_meta, str(meta_path.resolve()))
    return Import1688BatchResumeOut(
        success=True,
        message=f"Đã xếp hàng chạy tiếp {st.pending} link chưa hoàn thành.",
        pending=st.pending,
    )


@router.get("/jobs/batch-excel/{batch_token}/status", response_model=Import1688BatchStatusOut)
def batch_excel_job_status(
    batch_token: str,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    tid = _safe_batch_token_param(batch_token)
    meta_path = _batch_meta_json_path(tid)
    if not meta_path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy batch hoặc token hết hiệu lực.")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Meta batch hỏng: {exc}") from exc

    draft_ids = [int(x) for x in (meta.get("draft_ids") or []) if x is not None]
    return _batch_status_out_for_draft_ids(db, tid, draft_ids)


@router.get("/drafts", response_model=Import1688DraftListOut)
def list_import_1688_drafts(
    status: Optional[str] = Query(None, description="Lọc theo status queued|running|done|error|published"),
    limit: int = Query(40, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    status_norm = (status or "").strip()
    rows, total = draft_crud.list_drafts(
        db, status=(status_norm or None), limit=limit, offset=offset
    )
    return Import1688DraftListOut(
        items=[ProductImportDraftOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def _file_response_import_excel_rows(rows_data: List[Dict[str, Any]], download_filename: str) -> Response:
    """Tạo Excel mẫu nhập web (cùng layout export bulk draft) — trả bytes, không phụ thuộc CWD hay ghi đĩa."""
    if not rows_data:
        raise HTTPException(
            status_code=400,
            detail="Không có draft nào trong danh sách đã có dữ liệu để export (chờ job done).",
        )
    columns, vietnamese_headers = _excel_export_columns_and_vi_headers()
    df = pd.DataFrame(rows_data, columns=columns)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Products", index=False, startrow=0)
        ws = writer.sheets["Products"]
        ws.insert_rows(2)
        for idx, header in enumerate(vietnamese_headers, 1):
            ws.cell(row=2, column=idx, value=header)
    body = buf.getvalue()
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{download_filename}"'},
    )


@router.post("/drafts/export-excel-bulk")
def export_import_1688_drafts_bulk(
    payload: Import1688DraftIdsBody,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    ids_sorted = sorted(set(payload.draft_ids))
    by_id = draft_crud.get_by_ids_map(db, ids_sorted)
    rows_data: List[Dict[str, Any]] = []
    batch_reserved: Set[str] = set()
    sku_fix_pending: List[Tuple[ProductImportDraft, Dict[str, Any]]] = []
    for did in ids_sorted:
        draft = by_id.get(did)
        if not draft:
            raise HTTPException(status_code=404, detail=f"Không có draft id={did}.")
        if not draft.product_data:
            continue
        pdata = _draft_product_data_for_excel_export(
            db,
            draft,
            sku_fix_pending=sku_fix_pending,
            batch_reserved=batch_reserved,
        )
        rows_data.append(_excel_row_from_product(pdata))

    if sku_fix_pending:
        for drow, pdata in sku_fix_pending:
            drow.product_data = pdata
            db.add(drow)
        db.commit()

    filename = f"import_1688_drafts_bulk_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return _file_response_import_excel_rows(rows_data, filename)


@router.get("/listing-queue/{queue_token}/export-products.xlsx")
def listing_import_queue_export_products_excel(
    queue_token: str,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Excel dữ liệu sản phẩm để nhập web — các draft đã hoàn thành trong đợt listing queue.

    Xuất thẳng từ `product_data` đã lưu (không chuẩn hoá SKU lại) để tránh hàng trăm truy vấn
    và timeout gateway (504) trên đợt lớn.
    """
    from app.services import listing_import_queue as liq

    tok = _safe_listing_queue_token_param(queue_token)
    try:
        draft_ids = liq.collect_terminal_draft_ids_from_queue(tok)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not draft_ids:
        raise HTTPException(
            status_code=400,
            detail="Đợt này chưa có draft nào (chưa có dòng done/error ghi draft_id).",
        )

    t0 = time.perf_counter()
    by_id = draft_crud.get_by_ids_map(db, draft_ids)
    rows_data: List[Dict[str, Any]] = []
    missing_in_db = 0
    # Không gọi _draft_product_data_for_excel_export (kiểm tra SKU + nhiều query DB / nháp):
    # với vài trăm dòng dễ vượt timeout nginx (504). Dữ liệu đã có từ crawl; SKU có thể chỉnh
    # qua export từng nháp hoặc bulk draft nếu cần.
    for did in draft_ids:
        draft = by_id.get(did)
        if not draft:
            missing_in_db += 1
            continue
        pdata = dict(draft.product_data or {})
        rows_data.append(_excel_row_from_product(pdata))

    elapsed = time.perf_counter() - t0
    logger.info(
        "listing_queue export-products (fast) token=%s… draft_ids=%s missing_in_db=%s excel_rows=%s duration_s=%.2f",
        tok[:12],
        len(draft_ids),
        missing_in_db,
        len(rows_data),
        elapsed,
    )

    if not rows_data:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Không xuất được dòng Excel nào: có {len(draft_ids)} draft_id trên snapshot đợt, "
                f"{missing_in_db} không còn trong DB (có thể nháp đã xóa). "
                "Kiểm tra bảng nháp Import hoặc tải CSV meta để đối chiếu draft_id."
            ),
        )

    if missing_in_db:
        logger.warning(
            "listing_queue export-products token=%s… %s draft_id trên đợt không tìm thấy trong DB",
            tok[:12],
            missing_in_db,
        )

    filename = f"listing_queue_products_{tok[:12]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    try:
        return _file_response_import_excel_rows(rows_data, filename)
    except Exception as exc:
        logger.exception("listing_queue export-products Excel build failed")
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi tạo file Excel trên server: {exc}",
        ) from exc


@router.get("/jobs/{job_id}", response_model=Import1688JobOut)
def get_import_1688_job(
    job_id: str,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    draft = draft_crud.get_by_job_id(db, job_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Không tìm thấy job import 1688.")
    return _to_job_out(draft)


@router.get("/drafts/{draft_id}", response_model=ProductImportDraftOut)
def get_import_1688_draft(
    draft_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    draft = draft_crud.get_by_id(db, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Không tìm thấy draft.")
    return draft


@router.put("/drafts/{draft_id}", response_model=ProductImportDraftOut)
def update_import_1688_draft(
    draft_id: int,
    payload: ProductImportDraftUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    draft = draft_crud.get_by_id(db, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Không tìm thấy draft.")
    pd = dict(payload.product_data or {})
    compact_product_info_for_web(pd)
    return draft_crud.update_draft(db, draft, product_data=pd, status="done", message="Đã cập nhật draft.")


@router.delete("/drafts/{draft_id}")
def delete_import_1688_draft(
    draft_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    ok = draft_crud.delete_draft_by_id(db, draft_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy draft.")
    return {"success": True, "draft_id": draft_id}


@router.post("/drafts/{draft_id}/publish")
def publish_import_1688_draft(
    draft_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    draft = draft_crud.get_by_id(db, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Không tìm thấy draft.")
    payload = _publish_payload(draft.product_data or {})

    src = (draft.source or "").strip().lower()
    norm_url = normalize_product_import_url(draft.source_url or "")

    existing = None
    if getattr(draft, "published_product_id", None):
        existing = product_crud.get_product_by_product_id(db, draft.published_product_id)
    if existing is None:
        existing = product_crud.get_product_by_product_id(db, payload["product_id"])

    exclude_id = existing.id if existing else None
    sku_reserved: set[str] = set()
    try:
        sku_code = ensure_import_link_internal_product_code(
            db,
            payload.get("code"),
            exclude_product_id=exclude_id,
            exclude_draft_id=draft_id,
            batch_reserved=sku_reserved,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload["code"] = sku_code
    payload["product_info"] = sync_internal_code_into_product_info(payload.get("product_info"), sku_code)

    canonical_pid = ""

    if src == "1688":
        oid = extract_1688_numeric_offer_id(norm_url, draft.source_offer_id)
        if not oid:
            raise HTTPException(
                status_code=400,
                detail={
                    "reason": "import_publish_missing_1688_offer_id",
                    "message": (
                        "Không trích được mã offer 1688 (chuỗi chữ số) từ link. "
                        "Cần URL dạng …/offer/<số>.html hoặc ?offerId=<số>."
                    ),
                    "normalized_url_preview": norm_url[:240],
                },
            )
        if existing is None:
            existing = product_crud.get_product_by_product_id(db, f"1688_{oid}")
        try:
            canonical_pid = build_canonical_1688_product_id(oid, sku_code)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"reason": "invalid_internal_product_id", "message": str(exc)},
            ) from exc

    elif src == "hibox":
        hid = (extract_hibox_slug(norm_url) or "").strip()
        if not hid:
            hid = (draft.source_offer_id or "").strip()
        if not hid or hid == "hibox_import":
            raise HTTPException(
                status_code=400,
                detail={
                    "reason": "import_publish_missing_hibox_item_id",
                    "message": (
                        "Không trích được mã sản phẩm Hibox (đoạn sau /v/ hoặc ?id= mirror). "
                        "Slug «abb-<số>» = cửa hàng 1688; slug chỉ chữ số = Taobao."
                    ),
                    "normalized_url_preview": norm_url[:240],
                    "source_offer_id": draft.source_offer_id,
                },
            )
        if existing is None:
            existing = product_crud.get_product_by_product_id(db, f"hibox_{hid}")
        try:
            canonical_pid = build_canonical_product_id_from_hibox_slug(hid, sku_code)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"reason": "invalid_internal_product_id", "message": str(exc)},
            ) from exc

        if existing is None:
            existing = product_crud.get_product_by_product_id(db, canonical_pid)
        if existing is None:
            oid1688 = extract_hibox_1688_offer_digits(hid)
            if oid1688:
                existing = product_crud.get_product_by_product_id(db, f"1688_{oid1688}")
        if existing is None:
            existing = product_crud.get_product_by_product_id(db, f"hibox_{hid}")
        if existing is None and hibox_slug_is_1688_offer(hid):
            legacy_pid = f"T{hid}a188{sku_code.strip().upper()}"
            existing = product_crud.get_product_by_product_id(db, legacy_pid)

    else:
        raise HTTPException(
            status_code=400,
            detail={
                "reason": "import_publish_unknown_source",
                "message": f"Nguồn draft không hỗ trợ đăng với quy tắc mã hiện tại: {src}",
                "draft_source": src,
            },
        )

    payload["product_id"] = canonical_pid

    exclude_pk: Set[int] = set()
    if existing:
        exclude_pk.add(existing.id)
    conflict_src = product_crud.find_conflicting_product_id_for_same_listing_source(
        db,
        canonical_pid,
        exclude_product_pk_ids=exclude_pk,
    )
    if conflict_src:
        raise HTTPException(
            status_code=400,
            detail={
                "reason": "duplicate_listing_source_id",
                "message": (
                    "Mã nguồn (1688: A… hoặc Taobao/Tmall: T…) — phần trước «a188» trong cột id — "
                    f"đã tồn tại trên shop ({conflict_src}). Không đăng trùng một offer/item."
                ),
                "existing_product_id": conflict_src,
                "candidate_product_id": canonical_pid,
            },
        )

    compact_product_info_for_web(payload)

    if existing is None:
        existing = product_crud.get_product_by_product_id(db, canonical_pid)

    if existing:
        product = product_crud.update_product(db, existing.id, ProductUpdate(**payload))
        action = "updated"
    else:
        product = product_crud.create_product(db, ProductCreate(**payload))
        action = "created"
    old_cid = product.category_id
    triple_idx = product_crud._build_cat3_triple_name_lookup(db)
    cat3_idx = product_crud._build_cat3_lookup_indexes(db)
    product_crud._sync_product_category_id_from_taxonomy(product, triple_idx, cat3_idx)
    db.commit()
    db.refresh(product)
    if product.category_id != old_cid:
        try:
            from app.utils.ttl_cache import cache as ttl_cache

            ttl_cache.invalidate_all()
        except Exception:
            pass

    merged_pd = dict(draft.product_data or {})
    merged_pd["product_id"] = canonical_pid
    merged_pd["code"] = sku_code
    merged_pd["product_info"] = sync_internal_code_into_product_info(
        merged_pd.get("product_info"), sku_code
    )
    compact_product_info_for_web(merged_pd)
    merged_pd["deposit_require"] = 1

    draft_crud.update_draft(
        db,
        draft,
        status="published",
        phase="published",
        message="Đã đăng sản phẩm.",
        published_product_id=product.product_id,
        product_data=merged_pd,
        finished_at=datetime.now(),
    )
    return {"success": True, "action": action, "product_id": product.product_id, "slug": product.slug}


@router.get("/drafts/{draft_id}/export-excel")
def export_import_1688_draft_excel(
    draft_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    draft = draft_crud.get_by_id(db, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Không tìm thấy draft.")
    if not draft.product_data:
        raise HTTPException(status_code=400, detail="Draft chưa có dữ liệu sản phẩm để export.")
    pdata = _draft_product_data_for_excel_export(db, draft)
    filename = f"import_1688_draft_{draft.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return _file_response_import_excel_rows([_excel_row_from_product(pdata)], filename)


def _safe_listing_queue_token_param(raw: str) -> str:
    t = (raw or "").strip().lower()
    if not re.fullmatch(r"[a-f0-9]{32,64}", t):
        raise HTTPException(status_code=400, detail="queue_token không hợp lệ.")
    return t


@router.post("/listing-queue/enqueue", response_model=ListingImportQueueEnqueueOut)
def listing_import_queue_enqueue(
    payload: ListingImportQueueEnqueueIn,
    admin: AdminUser = Depends(require_module_permission("products")),
):
    from app.services import listing_import_queue as liq

    admin_id = getattr(admin, "id", None)
    tasks = [
        {
            "url": it.url.strip(),
            "source": it.source or "hibox",
            "label": it.label,
            "chinese_name": it.chinese_name,
            "shop_name_chinese": it.shop_name_chinese,
        }
        for it in payload.items
    ]
    try:
        token, added, msg = liq.enqueue(payload.queue_token, tasks, admin_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ListingImportQueueEnqueueOut(queue_token=token, added=added, message=msg)


@router.get("/listing-queue/runs", response_model=ListingImportQueueRunsOut)
def listing_import_queue_list_runs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: AdminUser = Depends(require_module_permission("products")),
):
    from app.services import listing_import_queue as liq

    items, total = liq.list_saved_queue_summaries(limit=limit, offset=offset)
    return ListingImportQueueRunsOut(items=items, total=total, limit=limit, offset=offset)


@router.delete("/listing-queue/{queue_token}", response_model=ListingImportQueueDeleteOut)
def listing_import_queue_delete_saved(
    queue_token: str,
    _: AdminUser = Depends(require_module_permission("products")),
):
    from app.services import listing_import_queue as liq

    tok = _safe_listing_queue_token_param(queue_token)
    try:
        liq.delete_saved_queue(tok, None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ListingImportQueueDeleteOut(queue_token=tok, deleted=True)


@router.get("/listing-queue/{queue_token}")
def listing_import_queue_status(
    queue_token: str,
    _: AdminUser = Depends(require_module_permission("products")),
):
    from app.services import listing_import_queue as liq

    tok = _safe_listing_queue_token_param(queue_token)
    try:
        return liq.get_status_dict(tok)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/listing-queue/{queue_token}/pause", response_model=ListingImportQueueActionMessage)
def listing_import_queue_pause(
    queue_token: str,
    _: AdminUser = Depends(require_module_permission("products")),
):
    from app.services import listing_import_queue as liq

    tok = _safe_listing_queue_token_param(queue_token)
    try:
        out = liq.pause(tok, None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ListingImportQueueActionMessage(queue_token=out["queue_token"], message=out.get("message") or "OK")


@router.post("/listing-queue/{queue_token}/resume", response_model=ListingImportQueueActionMessage)
def listing_import_queue_resume(
    queue_token: str,
    admin: AdminUser = Depends(require_module_permission("products")),
):
    from app.services import listing_import_queue as liq

    tok = _safe_listing_queue_token_param(queue_token)
    admin_id = getattr(admin, "id", None)
    try:
        out = liq.resume(tok, admin_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ListingImportQueueActionMessage(queue_token=out["queue_token"], message=out.get("message") or "OK")


@router.post("/listing-queue/{queue_token}/stop", response_model=ListingImportQueueActionMessage)
def listing_import_queue_stop(
    queue_token: str,
    _: AdminUser = Depends(require_module_permission("products")),
):
    from app.services import listing_import_queue as liq

    tok = _safe_listing_queue_token_param(queue_token)
    try:
        out = liq.stop_permanent(tok, None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ListingImportQueueActionMessage(queue_token=out["queue_token"], message=out.get("message") or "OK")


@router.get("/listing-queue/{queue_token}/export.csv")
def listing_import_queue_export_csv(
    queue_token: str,
    finished_only: bool = Query(
        False,
        description="True = chỉ các dòng đã kết thúc (done/error). False = toàn bộ hàng đợi (snapshot tiến trình).",
    ),
    _: AdminUser = Depends(require_module_permission("products")),
):
    from app.services import listing_import_queue as liq

    tok = _safe_listing_queue_token_param(queue_token)
    try:
        csv_text = liq.export_snapshot_csv(tok, finished_only=finished_only)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    body = "\ufeff" + csv_text.lstrip("\ufeff")
    suffix = "_ket_qua" if finished_only else "_snapshot"
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="listing_import_queue_{tok[:12]}{suffix}.csv"',
        },
    )
