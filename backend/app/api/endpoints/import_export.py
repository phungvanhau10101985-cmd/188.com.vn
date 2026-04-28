# backend/app/api/endpoints/import_export.py - COMPLETE FINAL VERSION
import pandas as pd
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse, Response, StreamingResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import tempfile
import os
import shutil
import uuid
import threading
import traceback
from datetime import datetime
import json
import logging
import time

from app.db.session import get_db

logger = logging.getLogger(__name__)

# Chuỗi cố định để grep log: grep IMPORT_EXCEL trên VPS
IMPORT_EXCEL_LOG_PREFIX = "[IMPORT_EXCEL]"
from app.services.excel_importer import ExcelImporter
from app.core.config import settings
from app.services.category_seo_analyzer import scan_and_create_mappings
from app.services.import_excel_job_store import load_import_job, persist_import_job

excel_to_db_mapping = {
    # ID & Basic Info
    'id': 'product_id',
    'sku': 'code',
    'origin': 'origin',
    'brand': 'brand_name',
    'name': 'name',
    'pro_content': 'description',
    'price': 'price',
    
    # Shop Info
    'shop_name': 'shop_name',
    'shop_id': 'shop_id',
    
    # Prices
    'pro_lower_price': 'pro_lower_price',
    'pro_high_price': 'pro_high_price',
    
    # Ratings & Questions
    'rating_group_id': 'group_rating',
    'question_group_id': 'group_question',
    
    # Variants & Sizes (for ordering)
    'Variant': 'variant_colors',      # O: Biến thể màu để đặt hàng
    'sizes': 'sizes',                # N: Kích thước để đặt hàng
    
    # Images
    'gallery_images': 'images',
    'detail_images': 'gallery',
    'product_url': 'link_default',
    'video_url': 'video_link',
    'main_image': 'main_image',
    
    # Counts
    'likes_count': 'likes',
    'purchases_count': 'purchases',
    'reviews_count': 'rating_total',
    'questions_count': 'question_total',
    'rating_score': 'rating_point',
    
    # Stock
    'stock_quantity': 'available',
    'deposit_required': 'deposit_require',
    
    # Categories
    'Main Category': 'category',
    'Subcategory': 'subcategory',
    'Sub-subcategory': 'sub_subcategory',
    
    # Product Attributes
    'Material': 'material',
    'Style': 'style',
    
    # FILTER COLUMNS (multi-value, comma-separated)
    'Color': 'color_filters',        # AG: Màu sắc cho bộ lọc
    'Occasion': 'occasion_filters',  # AH: Dịp cho bộ lọc
    'Features': 'feature_filters',   # AI: Tính năng cho bộ lọc
    
    # Weight
    'Weight': 'weight',
    
    # Cột AK: Thông tin sản phẩm (JSON)
    'product_info': 'product_info',
}


router = APIRouter()

# --- Import Excel async (job + tiến trình) — dùng khi file lớn; server single-process ---
_import_job_lock = threading.Lock()
IMPORT_EXCEL_JOBS: dict = {}  # job_id -> trạng thái


def auto_scan_category_seo_safe() -> None:
    """Gọi scan SEO với session mới (an toàn sau khi request/import job đóng DB)."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        auto_scan_category_seo(db)
    finally:
        db.close()


def _import_progress_message(phase: str, current: int, total: Optional[int]) -> str:
    if phase == "reading":
        return "Đang đọc file Excel..."
    if phase == "parsing" and total:
        return f"Đang xử lý dòng {current:,} / {total:,}..."
    if phase == "parsing":
        return "Đang xử lý các dòng trong file..."
    if phase == "database" and total is not None:
        return f"Đang ghi CSDL: {current:,} / {total:,} sản phẩm..."
    if phase == "seo_categories" and total:
        return f"Sinh nội dung SEO danh mục: {current} / {total}..."
    if phase == "seo_categories":
        return "Đang sinh nội dung SEO cho danh mục..."
    if phase == "done":
        return "Hoàn tất import."
    return "Đang xử lý..."


def _import_job_percent(phase: str, current: int, total: Optional[int]) -> Optional[float]:
    if total and total > 0 and current >= 0:
        return min(100.0, round(100.0 * current / total, 1))
    return None


def _import_job_update(job_id: str, **kwargs) -> None:
    """Đồng bộ RAM + file JSON để GET /job/:id hoạt động sau pm2 restart (trùng thư mục)."""
    with _import_job_lock:
        st = IMPORT_EXCEL_JOBS.get(job_id)
        if st is None:
            st = load_import_job(job_id)
        if st is None:
            st = {}
        st.update(kwargs)
        IMPORT_EXCEL_JOBS[job_id] = st
        try:
            persist_import_job(job_id, st)
        except OSError:
            pass


def _run_import_excel_job(
    job_id: str,
    temp_file_path: str,
    overwrite: bool,
    original_filename: str,
) -> None:
    """Chạy sau khi POST /import/excel/async trả 202."""
    from app.db.session import SessionLocal

    _tick = {"phase": "", "mono": 0.0}

    def on_progress(phase: str, current: int, total: Optional[int]) -> None:
        _import_job_update(
            job_id,
            status="running",
            phase=phase,
            current=current,
            total=total,
            message=_import_progress_message(phase, current, total),
            percent=_import_job_percent(phase, current, total),
        )
        # Tránh spam: đổi phase hoặc mỗi ~25 giây
        now_m = time.monotonic()
        phase_changed = _tick["phase"] != phase
        _tick["phase"] = phase
        elapsed = now_m - _tick["mono"]
        if phase_changed:
            _tick["mono"] = now_m
            logger.info(
                "%s job=%s phase=%s current=%s total=%s",
                IMPORT_EXCEL_LOG_PREFIX,
                job_id,
                phase,
                current,
                total,
            )
        elif elapsed >= 25.0:
            _tick["mono"] = now_m
            logger.info(
                "%s job=%s phase=%s current=%s total=%s (định kỳ)",
                IMPORT_EXCEL_LOG_PREFIX,
                job_id,
                phase,
                current,
                total,
            )

    db = SessionLocal()
    try:
        fz = os.path.getsize(temp_file_path) if os.path.isfile(temp_file_path) else 0
        logger.info(
            "%s start job=%s file=%s size=%s overwrite=%s tmp=%s",
            IMPORT_EXCEL_LOG_PREFIX,
            job_id,
            original_filename,
            fz,
            overwrite,
            temp_file_path,
        )
        _import_job_update(
            job_id,
            status="running",
            phase="reading",
            current=0,
            total=None,
            message=_import_progress_message("reading", 0, None),
            percent=None,
        )
        importer = ExcelImporter(db)
        result = importer.import_from_excel(
            temp_file_path,
            overwrite,
            progress_callback=on_progress,
        )

        if result.get("error"):
            err_lines = result.get("errors") or []
            if isinstance(err_lines, list):
                err_lines_out = [
                    str(x) for x in err_lines[:200] if x is not None and str(x).strip()
                ]
            else:
                err_lines_out = []
            warn_lines = result.get("warnings") or []
            if isinstance(warn_lines, list):
                warn_lines_out = [str(x) for x in warn_lines[:80] if x is not None and str(x).strip()]
            else:
                warn_lines_out = []
            _import_job_update(
                job_id,
                status="error",
                phase="error",
                finished_at=datetime.now().isoformat(),
                detail=str(result["error"]),
                message=str(result["error"]),
                percent=None,
                errors=err_lines_out if err_lines_out else None,
                warnings=warn_lines_out if warn_lines_out else None,
                total_rows=result.get("total_rows"),
            )
            logger.error(
                "%s failed job=%s importer_error=%s",
                IMPORT_EXCEL_LOG_PREFIX,
                job_id,
                str(result["error"])[:500],
            )
            return

        data = {
            "created": result.get("created", 0),
            "updated": result.get("updated", 0),
            "total_processed": result.get("total_processed", 0),
            "success_rate": result.get("success_rate", "0%"),
            "file_name": original_filename,
            "import_time": datetime.now().isoformat(),
            "auto_seo_scan": "running_in_background",
        }
        _import_job_update(
            job_id,
            status="done",
            phase="done",
            finished_at=datetime.now().isoformat(),
            percent=100.0,
            message=_import_progress_message("done", 0, None),
            result={
                "success": True,
                "message": f"Đã import {result.get('total_processed', 0)} sản phẩm.",
                "data": data,
                "warnings": result.get("warnings", [])[:50],
                "errors": result.get("errors", [])[:150],
            },
        )
        threading.Thread(target=auto_scan_category_seo_safe, daemon=True).start()
        logger.info(
            "%s done job=%s created=%s updated=%s processed=%s file=%s (auto_scan_seo_spawned=yes)",
            IMPORT_EXCEL_LOG_PREFIX,
            job_id,
            result.get("created"),
            result.get("updated"),
            result.get("total_processed"),
            original_filename,
        )

    except Exception as e:
        traceback.print_exc()
        tb = traceback.format_exc()
        tb_lines = [ln for ln in tb.strip().splitlines() if ln.strip()][-40:]
        _import_job_update(
            job_id,
            status="error",
            phase="error",
            finished_at=datetime.now().isoformat(),
            detail=str(e),
            message=f"Import thất bại: {e}",
            percent=None,
            errors=[f"{type(e).__name__}: {e}", *tb_lines] if tb_lines else [f"{type(e).__name__}: {e}"],
        )
        logger.exception(
            "%s exception job=%s:%s",
            IMPORT_EXCEL_LOG_PREFIX,
            job_id,
            str(e)[:400],
        )
    finally:
        db.close()
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass


def auto_scan_category_seo(db: Session):
    """
    Background task: Tự động scan SEO danh mục sau import.
    Chỉ gọi AI cho danh mục MỚI, danh mục cũ dùng mapping đã lưu.
    AI tự approve nếu confidence cao (≥ 0.85).
    """
    try:
        print("\n🔍 [Background] Bắt đầu auto scan SEO danh mục...")
        result = scan_and_create_mappings(db, force_rescan=False)
        print(f"✅ [Background] Auto SEO scan hoàn tất:")
        print(f"   - Tổng danh mục: {result.get('total_categories', 0)}")
        print(f"   - Danh mục MỚI: {result.get('new_categories', 0)} (gọi AI)")
        print(f"   - Danh mục cũ: {result.get('skipped_existing', 0)} (dùng mapping đã lưu)")
        print(f"   - Trùng lặp phát hiện: {result.get('duplicates_found', 0)}")
        print(f"   - AI tự duyệt: {result.get('auto_approved', 0)} redirect")
        pending = result.get('new_mappings', 0) - result.get('auto_approved', 0)
        if pending > 0:
            print(f"   - ⚠️  Cần review: {pending} mapping")
    except Exception as e:
        print(f"⚠️ [Background] Auto SEO scan failed: {e}")
        # Không raise - import vẫn thành công

# ========== IMPORT FUNCTIONS ==========

@router.post("/import/excel/async")
async def import_excel_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    overwrite: bool = False,
):
    """
    Nhận file Excel, trả về job_id ngay (202). Client poll GET /import/excel/job/{job_id}
    để xem tiến trình (parse dòng, ghi DB, SEO danh mục).
    """
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=400,
            detail="Chỉ hỗ trợ file Excel (.xlsx, .xls).",
        )

    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile(dir=temp_dir, suffix=".xlsx", delete=False) as tmp:
        temp_file_path = tmp.name
        content = await file.read()
        tmp.write(content)

    job_id = str(uuid.uuid4())
    logger.info(
        "%s queued job=%s file=%s bytes=%s overwrite=%s",
        IMPORT_EXCEL_LOG_PREFIX,
        job_id,
        file.filename,
        len(content) if content else 0,
        overwrite,
    )
    initial = {
        "job_id": job_id,
        "status": "queued",
        "phase": "queued",
        "current": 0,
        "total": None,
        "percent": None,
        "message": "Đã nhận file, đang vào hàng đợi...",
        "created_at": datetime.now().isoformat(),
        "finished_at": None,
        "result": None,
        "detail": None,
    }
    with _import_job_lock:
        IMPORT_EXCEL_JOBS[job_id] = initial
        try:
            persist_import_job(job_id, IMPORT_EXCEL_JOBS[job_id])
        except OSError:
            pass

    background_tasks.add_task(
        _run_import_excel_job,
        job_id,
        temp_file_path,
        overwrite,
        file.filename,
    )

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "message": "Đã nhận file. Dùng GET /import-export/import/excel/job/{job_id} để theo dõi tiến trình.",
            "poll_url": f"/api/v1/import-export/import/excel/job/{job_id}",
        },
    )


@router.get("/import/excel/job/{job_id}")
def get_import_excel_job(job_id: str):
    """Trạng thái import async (tiến trình + kết quả khi xong). Đọc từ RAM hoặc file (sau khi restart API)."""
    with _import_job_lock:
        job = IMPORT_EXCEL_JOBS.get(job_id)
        if job is None:
            loaded = load_import_job(job_id)
            if loaded:
                IMPORT_EXCEL_JOBS[job_id] = loaded
                job = loaded
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy job import.")
    return job


@router.post("/import/excel")
async def import_excel(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    overwrite: bool = False,
    db: Session = Depends(get_db)
):
    """
    Import products from Excel file (36 columns A-AJ)
    
    IMPORTANT: 
    - Excel file has 36 columns (A-AJ) WITHOUT Slug column
    - Slug will be auto-generated from product name and ID
    - Returns JSON with import results
    """
    if not file.filename or not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400, 
            detail="Chỉ hỗ trợ file Excel (.xlsx, .xls)."
        )
    
    temp_file_path = None
    
    try:
        print(f"\n{'='*60}")
        print(f"📥 BẮT ĐẦU IMPORT EXCEL: {file.filename}")
        print(f"{'='*60}")
        
        # Create temp directory if not exists
        temp_dir = "temp_uploads"
        os.makedirs(temp_dir, exist_ok=True)
        
        # Create temp file with context manager
        with tempfile.NamedTemporaryFile(
            dir=temp_dir,
            suffix='.xlsx',
            delete=False
        ) as tmp:
            temp_file_path = tmp.name
            
            # Read and write file
            content = await file.read()
            tmp.write(content)

        nbytes = len(content) if content is not None else 0
        
        print(f"✅ Đã lưu file tạm: {temp_file_path}")
        print(f"📏 Kích thước: {nbytes:,} bytes")

        logger.info(
            "%s sync_start file=%s bytes=%s overwrite=%s tmp=%s",
            IMPORT_EXCEL_LOG_PREFIX,
            file.filename,
            nbytes,
            overwrite,
            temp_file_path,
        )
        
        # Close file handle
        del content
        
        try:
            df_preview = pd.read_excel(temp_file_path, nrows=5)
            print(f"📋 Preview - Số dòng: {len(df_preview)}, Số cột: {len(df_preview.columns)}")
            print(f"📋 Các cột: {list(df_preview.columns)}")
        except Exception as e:
            print(f"⚠️  Không đọc được preview: {e}")
        
        # Import using ExcelImporter
        importer = ExcelImporter(db)
        result = importer.import_from_excel(temp_file_path, overwrite)
        
        # Process result
        if "error" in result and result["error"]:
            raise HTTPException(status_code=400, detail=result["error"])
        
        print(f"\n{'='*60}")
        print(f"✅ IMPORT HOÀN TẤT")
        print(f"   ➕ Tạo mới: {result.get('created', 0)}")
        print(f"   🔄 Cập nhật: {result.get('updated', 0)}")
        print(f"   ⚠️  Cảnh báo: {len(result.get('warnings', []))}")
        print(f"   ❌ Lỗi: {len(result.get('errors', []))}")
        print(f"{'='*60}")

        logger.info(
            "%s sync_done file=%s created=%s updated=%s total_processed=%s warnings=%s errors=%s",
            IMPORT_EXCEL_LOG_PREFIX,
            file.filename,
            result.get("created", 0),
            result.get("updated", 0),
            result.get("total_processed", 0),
            len(result.get("warnings", []) or []),
            len(result.get("errors", []) or []),
        )
        
        # Tự động scan SEO danh mục trong background (session mới, không dùng db request)
        background_tasks.add_task(auto_scan_category_seo_safe)
        print("🚀 Đã thêm task: Auto scan SEO danh mục (chạy background)")
        
        return {
            "success": True,
            "message": f"Đã import {result.get('total_processed', 0)} sản phẩm. Đang tự động scan SEO danh mục...",
            "data": {
                "created": result.get("created", 0),
                "updated": result.get("updated", 0),
                "total_processed": result.get("total_processed", 0),
                "success_rate": result.get("success_rate", "0%"),
                "file_name": file.filename,
                "import_time": datetime.now().isoformat(),
                "auto_seo_scan": "running_in_background"
            },
            "warnings": result.get("warnings", [])[:10],
            "errors": result.get("errors", [])[:20],
            "note": "File Excel có 36 cột (A-AJ), Slug được tự động tạo từ tên sản phẩm và product_id. SEO scan tự động chạy background."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ LỖI IMPORT: {str(e)}")
        traceback.print_exc()
        logger.exception(
            "%s sync_failed file=%s",
            IMPORT_EXCEL_LOG_PREFIX,
            getattr(file, "filename", None) or "(unknown)",
        )
        
        # Cleanup temp file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                time.sleep(0.1)
                os.remove(temp_file_path)
            except:
                pass
        
        raise HTTPException(
            status_code=500,
            detail=f"Import thất bại: {str(e)}"
        )
    finally:
        # Always try to cleanup
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                for _ in range(3):
                    try:
                        os.remove(temp_file_path)
                        break
                    except:
                        time.sleep(0.1)
            except:
                pass

# ========== EXPORT FUNCTIONS ==========

@router.get("/export/excel", responses={
    200: {
        "description": "Export products to Excel",
        "content": {
            "application/json": {},
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}
        }
    }
})
async def export_excel(
    category: str = None,
    subcategory: str = None,
    is_active: bool = True,
    download: bool = Query(False, description="Set to true to download file directly"),
    db: Session = Depends(get_db)
):
    """
    Export products to Excel file (37 columns A-AK)
    
    Features:
    - Returns Excel file with 37 columns (A-AK) including Slug
    - Slug column is automatically added as last column
    - Set download=true to get file download
    - Default returns JSON info
    """
    try:
        print(f"\n{'='*60}")
        print(f"📤 BẮT ĐẦU EXPORT EXCEL")
        print(f"   Download mode: {'✅ ON' if download else '📄 JSON'}")
        print(f"{'='*60}")
        
        from app.crud.product import get_products, get_all_products_for_export
        
        if category or subcategory:
            export_cap = max(1, int(getattr(settings, "MAX_EXCEL_IMPORT_ROWS", 30000) or 30000))
            result = get_products(
                db,
                category=category,
                subcategory=subcategory,
                is_active=is_active,
                limit=export_cap,
            )
            products_data = result.get("products", [])
            print(f"📊 Lọc theo: category={category}, subcategory={subcategory}")
        else:
            products_data = get_all_products_for_export(db)
            print(f"📊 Xuất tất cả sản phẩm")
        
        if not products_data:
            raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm để export")
        
        print(f"✅ Tìm thấy {len(products_data)} sản phẩm")
        
        importer = ExcelImporter(db)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"export_products_{timestamp}.xlsx"
        if category:
            filename = f"export_{category}_{timestamp}.xlsx"
        
        result = importer.export_to_excel(products_data, filename)
        
        if not result.get("success", False):
            raise HTTPException(status_code=500, detail=result.get("error", "Export failed"))
        
        print(f"\n{'='*60}")
        print(f"✅ EXPORT HOÀN TẤT")
        print(f"   📁 File: {result.get('filename')}")
        print(f"   📏 Kích thước: {result.get('file_size', 0):,} bytes")
        print(f"   📊 Số dòng: {result.get('rows', 0)}")
        print(f"{'='*60}")
        
        # IF download=true, return file directly
        if download:
            filepath = result.get("filepath")
            if filepath and os.path.exists(filepath):
                return FileResponse(
                    path=filepath,
                    filename=filename,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                raise HTTPException(status_code=500, detail="Export file not created")
        
        # IF download=false, return JSON info (default)
        return {
            "success": True,
            "message": f"Đã export {len(products_data)} sản phẩm",
            "data": {
                "filename": result.get("filename"),
                "filepath": result.get("filepath"),
                "download_url": result.get("download_url"),
                "direct_download_url": f"/api/v1/import-export/export/excel?download=true",
                "latest_download_url": "/api/v1/import-export/download/latest-export",
                "merchant_center_tsv_feed": "/api/v1/import-export/export/merchant-center-feed.tsv",
                "file_size": result.get("file_size"),
                "columns": result.get("columns"),
                "rows": result.get("rows"),
                "export_time": datetime.now().isoformat(),
                "note": "File có 37 cột (A-AK) bao gồm cột Slug (cột cuối cùng). Add ?download=true to get file directly."
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ LỖI EXPORT: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Export thất bại: {str(e)}"
        )

# ========== SAMPLE TEMPLATE ==========

@router.get("/export/sample")
async def export_sample_excel():
    """
    Download sample Excel template for import (36 columns A-AJ)
    
    IMPORTANT:
    - Template has 36 columns WITHOUT Slug column
    - Slug will be auto-generated when importing
    - Use this template for new imports
    """
    try:
        print(f"\n{'='*60}")
        print(f"🎯 TẠO SAMPLE TEMPLATE")
        print(f"{'='*60}")
        
        importer = ExcelImporter(None)
        
        result = importer.create_sample_template()
        
        if not result.get("success", False):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to create sample"))
        
        print(f"✅ Đã tạo template mẫu: {result.get('filename')}")
        print(f"📋 Template có 36 cột (A-AJ) - KHÔNG có cột Slug")
        print(f"💡 Slug sẽ được tự động tạo khi import")
        print(f"{'='*60}")
        
        return {
            "success": True,
            "message": "Đã tạo template mẫu thành công",
            "data": {
                "filename": result.get("filename"),
                "filepath": result.get("filepath"),
                "download_url": result.get("download_url"),
                "note": "Template có 36 cột (A-AJ), không có cột Slug. Slug sẽ được tự động tạo khi import."
            }
        }
        
    except Exception as e:
        print(f"❌ LỖI TẠO TEMPLATE: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Không thể tạo template mẫu: {str(e)}"
        )

# ========== DOWNLOAD ENDPOINTS ==========

@router.get("/download/sample")
async def download_sample_template():
    """
    Tải file Excel mẫu để import sản phẩm (36 cột A-AJ).
    Tạo file mẫu nếu chưa có, sau đó trả về file để tải xuống.
    """
    try:
        importer = ExcelImporter(None)
        result = importer.create_sample_template()
        if not result.get("success", False):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to create sample"))
        filepath = result.get("filepath")
        filename = result.get("filename", "sample_import_template.xlsx")
        if not filepath or not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="File mẫu không tồn tại")
        return FileResponse(
            path=filepath,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/export/{filename}")
async def download_export_file(filename: str):
    """
    Download specific exported Excel file
    
    Parameters:
    - filename: Name of the exported file (e.g., export_products_20260125_xxxxxx.xlsx)
    """
    filepath = os.path.join("app", "static", "uploads", filename)
    
    if not os.path.exists(filepath):
        # Try to find the file case-insensitive
        uploads_dir = os.path.join("app", "static", "uploads")
        if os.path.exists(uploads_dir):
            # List all Excel files
            all_files = os.listdir(uploads_dir)
            matching_files = [f for f in all_files if f.lower() == filename.lower()]
            
            if matching_files:
                filepath = os.path.join(uploads_dir, matching_files[0])
                filename = matching_files[0]
            else:
                raise HTTPException(status_code=404, detail=f"File '{filename}' not found")
        else:
            raise HTTPException(status_code=404, detail="Uploads directory not found")
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@router.get("/download/latest-export")
async def download_latest_export():
    """
    Download the latest exported Excel file
    
    Automatically finds and downloads the most recent export file
    """
    uploads_dir = os.path.join("app", "static", "uploads")
    
    if not os.path.exists(uploads_dir):
        raise HTTPException(status_code=404, detail="Uploads directory not found")
    
    # Find all export Excel files
    excel_files = []
    for f in os.listdir(uploads_dir):
        if f.endswith('.xlsx') and 'export' in f.lower():
            filepath = os.path.join(uploads_dir, f)
            if os.path.isfile(filepath):
                excel_files.append((f, os.path.getmtime(filepath)))
    
    if not excel_files:
        raise HTTPException(status_code=404, detail="No export files found")
    
    # Sort by modification time (newest first)
    excel_files.sort(key=lambda x: x[1], reverse=True)
    
    latest_filename = excel_files[0][0]
    filepath = os.path.join(uploads_dir, latest_filename)
    
    return FileResponse(
        path=filepath,
        filename=latest_filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ========== GOOGLE MERCHANT CENTER — FEED TSV ==========

@router.get("/export/merchant-center-feed.tsv")
def export_merchant_center_feed_tsv(db: Session = Depends(get_db)):
    """
    Xuất primary feed định dạng **TSV UTF-8** (tab) theo các cột Merchant Center (đầy đủ thường dùng).
    URL cố định, công khai — có thể dán vào Merchant Center (**Nguồn dữ liệu** → **Đường dẫn tệp**).

    Tuỳ chọn trong `.env`: `MERCHANT_FEED_CURRENCY` (mặc định `VND`).
    `MERCHANT_FEED_IMAGE_BASE_URL` có thể đặt riêng; không đặt thì dùng `BUNNY_CDN_PUBLIC_BASE` (app.core.config).
    """
    from app.services.merchant_feed_tsv import iter_merchant_feed_lines

    shop = (settings.FRONTEND_BASE_URL or "").rstrip("/") or "http://localhost:3001"
    cur = getattr(settings, "MERCHANT_FEED_CURRENCY", "VND") or "VND"
    img = getattr(settings, "MERCHANT_FEED_IMAGE_BASE_URL", "") or ""

    def body():
        for line in iter_merchant_feed_lines(db, shop, currency=cur, image_site_base=img or shop):
            yield (line + "\n").encode("utf-8")

    return StreamingResponse(
        body(),
        media_type="text/tab-separated-values; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="merchant-center-products.tsv"',
            "Cache-Control": "no-store",
        },
    )


# ---------- Meta (Facebook / Instagram Commerce) catalogue ----------

@router.get("/export/meta-catalog-feed.tsv")
def export_meta_catalog_feed_tsv(db: Session = Depends(get_db)):
    """
    Feed **TSV UTF-8** theo các cột catalogue Meta Commerce (URL để Commerce Manager / scheduled fetch).
    Đặt `META_FEED_FB_PRODUCT_CATEGORY` và tuỳ chọn `CATALOG_FEED_DEFAULT_GOOGLE_PRODUCT_CATEGORY` trong `.env` backend.
    """
    from app.services.social_catalog_feed_tsv import iter_meta_catalog_lines

    shop = (settings.FRONTEND_BASE_URL or "").rstrip("/") or "http://localhost:3001"
    cur = getattr(settings, "MERCHANT_FEED_CURRENCY", "VND") or "VND"
    img = getattr(settings, "MERCHANT_FEED_IMAGE_BASE_URL", "") or ""
    fb_cat = getattr(settings, "META_FEED_FB_PRODUCT_CATEGORY", "") or "Apparel & Accessories"
    gcat = getattr(settings, "CATALOG_FEED_DEFAULT_GOOGLE_PRODUCT_CATEGORY", "") or ""

    def body():
        for line in iter_meta_catalog_lines(
            db,
            shop,
            currency=cur,
            image_site_base=img or shop,
            fb_product_category=fb_cat,
            google_product_category_default=gcat,
        ):
            yield (line + "\n").encode("utf-8")

    return StreamingResponse(
        body(),
        media_type="text/tab-separated-values; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="meta-catalog-products.tsv"',
            "Cache-Control": "no-store",
        },
    )


# ---------- TikTok catalogue (Ads / Shop) ----------

@router.get("/export/tiktok-catalog-feed.tsv")
def export_tiktok_catalog_feed_tsv(db: Session = Depends(get_db)):
    """
    Feed **TSV UTF-8** theo tham số catalogue TikTok (`sku_id`, `link`, `image_link`, …).
    Tuỳ chọn `CATALOG_FEED_DEFAULT_GOOGLE_PRODUCT_CATEGORY` trong `.env` nếu cần một taxonomy Google cố định.
    """
    from app.services.social_catalog_feed_tsv import iter_tiktok_catalog_lines

    shop = (settings.FRONTEND_BASE_URL or "").rstrip("/") or "http://localhost:3001"
    cur = getattr(settings, "MERCHANT_FEED_CURRENCY", "VND") or "VND"
    img = getattr(settings, "MERCHANT_FEED_IMAGE_BASE_URL", "") or ""
    gcat = getattr(settings, "CATALOG_FEED_DEFAULT_GOOGLE_PRODUCT_CATEGORY", "") or ""

    def body():
        for line in iter_tiktok_catalog_lines(
            db,
            shop,
            currency=cur,
            image_site_base=img or shop,
            google_product_category_default=gcat,
        ):
            yield (line + "\n").encode("utf-8")

    return StreamingResponse(
        body(),
        media_type="text/tab-separated-values; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="tiktok-catalog-products.tsv"',
            "Cache-Control": "no-store",
        },
    )


# ========== UTILITY ENDPOINTS ==========

@router.get("/import/status")
async def get_import_status():
    """
    Get import/export system status
    
    Returns system configuration and status information
    """
    return {
        "system": "Excel Import/Export System",
        "status": "active",
        "version": "2.0.0",
        "import_format": "36 columns (A-AJ) without Slug",
        "export_format": "37 columns (A-AK) with Slug",
        "slug_generation": "auto-generated from product name and ID",
        "supported_formats": [".xlsx", ".xls"],
        "max_file_size": "10MB",
        "template_available": True,
        "endpoints": {
            "import": "POST /api/v1/import-export/import/excel",
            "export_json": "GET /api/v1/import-export/export/excel",
            "export_download": "GET /api/v1/import-export/export/excel?download=true",
            "template": "GET /api/v1/import-export/export/sample",
            "latest_download": "GET /api/v1/import-export/download/latest-export",
            "merchant_center_tsv_feed": "GET /api/v1/import-export/export/merchant-center-feed.tsv",
            "meta_catalog_tsv_feed": "GET /api/v1/import-export/export/meta-catalog-feed.tsv",
            "tiktok_catalog_tsv_feed": "GET /api/v1/import-export/export/tiktok-catalog-feed.tsv",
        },
        "catalog_env_hints": {
            "MERCHANT_FEED_CURRENCY": "Đơn vị tiền feed (Merchant / Meta / TikTok)",
            "MERCHANT_FEED_IMAGE_BASE_URL": "Origin ảnh feed; để trống = dùng BUNNY_CDN_PUBLIC_BASE (app.core.config)",
            "BUNNY_STORAGE_ZONE_NAME": "Bunny Storage zone (script upload / migrate)",
            "BUNNY_STORAGE_ACCESS_KEY": "Storage API password — không commit",
            "BUNNY_CDN_PUBLIC_BASE": "Pull Zone (vd https://188comvn.b-cdn.net) — đồng bộ frontend NEXT_PUBLIC_CDN_URL",
            "BUNNY_UPLOAD_PATH_PREFIX": "Prefix object khi migrate backend/app/static → Bunny (mặc định site)",
            "BUNNY_WEB_PUBLIC_PREFIX": "Prefix upload từ frontend/public (để trống = path trùng URL /images/...)",
            "META_FEED_FB_PRODUCT_CATEGORY": "Danh mục Meta (taxonomy spreadsheet)",
            "CATALOG_FEED_DEFAULT_GOOGLE_PRODUCT_CATEGORY": "Optional: google_product_category mặc định — trống thì build từ category trong DB",
            "NEXT_PUBLIC_CDN_URL": "(frontend/.env) trùng BUNNY_CDN_PUBLIC_BASE; see frontend/lib/site-config.ts",
        },
    }

@router.post("/fix/slugs")
async def fix_all_slugs(db: Session = Depends(get_db)):
    """
    Fix all slugs in database (utility endpoint)
    
    Regenerates slugs for all products based on current names and IDs
    Useful when slug generation logic changes
    """
    try:
        from app.crud.product import fix_all_slugs as fix_slugs_func
        result = fix_slugs_func(db)
        
        return {
            "success": True,
            "message": "Đã sửa tất cả slug",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi sửa slug: {str(e)}")

@router.get("/test-connection")
async def test_connection(db: Session = Depends(get_db)):
    """
    Test database connection and product count
    
    Quick health check for import/export system
    """
    try:
        from app.crud.product import get_all_products_for_export
        
        products_data = get_all_products_for_export(db)
        product_count = len(products_data) if products_data else 0
        
        return {
            "success": True,
            "message": "Import/Export system is ready",
            "data": {
                "database_connected": True,
                "product_count": product_count,
                "system_time": datetime.now().isoformat(),
                "note": f"Hệ thống có {product_count} sản phẩm để export"
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Database connection error"
        }