# backend/app/api/endpoints/category_seo.py - API quản lý SEO danh mục
"""
API endpoints cho:
1. Scan danh mục và phát hiện trùng lặp
2. Admin review/approve mappings
3. Lấy danh sách redirects
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Body
from sqlalchemy.orm import Session
from typing import List, Optional, Tuple
from datetime import datetime
import re

from app.db.session import get_db, SessionLocal
from app.models.category_seo import (
    CategorySeoMapping,
    CategorySeoDictionary,
    CategorySeoMeta,
    CategorySeoGeminiTarget,
    CategorySeoSettings,
)
from app.models.category_transform_rule import CategoryTransformRule
from app.models.category_final_mapping import CategoryFinalMapping
from app.models.product import Product
from app.crud import product as crud_product
from app.crud.product import category_field_equals_ci
from app.core.config import settings
from app.services.category_seo_service import generate_category_seo_body
from app.services.category_seo_analyzer import (
    scan_and_create_mappings,
    get_all_approved_redirects,
    get_all_category_paths,
    should_redirect_category,
    get_category_seo_status,
    merge_non_seo_categories_to_canonical,
)

try:
    from app.utils.slug import create_slug as slugify_vietnamese
except Exception:
    def slugify_vietnamese(text: str) -> str:
        return (text or "").strip().lower().replace(" ", "-")

router = APIRouter()

SEO_BODY_JOB_STATUS = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "total": 0,
    "done": 0,
    "skipped": 0,
    "failed": 0,
    "current_path": None,
    "report": [],
    "force": False,
    "path": None,
}

def _reset_seo_body_status(force: bool, path: Optional[str]):
    SEO_BODY_JOB_STATUS.update({
        "running": True,
        "started_at": datetime.utcnow().isoformat(),
        "finished_at": None,
        "total": 0,
        "done": 0,
        "skipped": 0,
        "failed": 0,
        "current_path": None,
        "report": [],
        "force": force,
        "path": path,
    })

def _append_seo_body_report(item: dict):
    report = SEO_BODY_JOB_STATUS.get("report") or []
    report.append(item)
    if len(report) > 500:
        report = report[-500:]
    SEO_BODY_JOB_STATUS["report"] = report


def _norm(s):
    if s is None:
        return ""
    return (s or "").strip().lower()


def _has_seo_links(body: Optional[str]) -> bool:
    if not body:
        return False
    text = body.lower()
    if "/danh-muc/" in text or "danh-muc/" in text:
        return True
    if "danh-muc" in text and ("href" in text or "<a" in text or "&lt;a" in text):
        return True
    if "<a" not in text and "&lt;a" not in text and "href" not in text:
        return False
    # Ưu tiên nhận diện link danh mục nội bộ
    return bool(re.search(r'href=[\"\\\']?[^\"\\\']*?/danh-muc/', text))


def _count_sibling_mentions(body: Optional[str], sibling_names: Optional[List[str]]) -> int:
    if not body or not sibling_names:
        return 0
    text = re.sub(r"\s+", " ", body.lower())
    count = 0
    for name in sibling_names:
        if not name:
            continue
        name_norm = re.sub(r"\s+", " ", name.strip().lower())
        if name_norm and name_norm in text:
            count += 1
    return count


def _flatten_tree_to_paths(tree):
    paths = []
    for c1 in tree:
        slug1 = _norm(c1.get("slug") or c1.get("name", ""))
        if not slug1:
            continue
        paths.append((slug1, None, None))
        for c2 in c1.get("children") or []:
            slug2 = _norm(c2.get("slug") or c2.get("name", ""))
            if not slug2:
                continue
            paths.append((slug1, slug2, None))
            for c3 in c2.get("children") or []:
                raw = c3.get("slug") if isinstance(c3, dict) else c3
                name = c3.get("name", raw) if isinstance(c3, dict) else raw
                slug3 = _norm(raw or name)
                if slug3:
                    paths.append((slug1, slug2, slug3))
    return paths


GEMINI_TARGETS_JOB_STATUS = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "total": 0,
    "processed": 0,
    "meta_generated": 0,
    "meta_skipped": 0,
    "body_generated": 0,
    "body_skipped": 0,
    "failed": 0,
    "current_path": None,
    "report": [],
    "force_description": False,
    "force_body": False,
}


def _reset_gemini_targets_status(force_description: bool, force_body: bool):
    GEMINI_TARGETS_JOB_STATUS.update({
        "running": True,
        "started_at": datetime.utcnow().isoformat(),
        "finished_at": None,
        "total": 0,
        "processed": 0,
        "meta_generated": 0,
        "meta_skipped": 0,
        "body_generated": 0,
        "body_skipped": 0,
        "failed": 0,
        "current_path": None,
        "report": [],
        "force_description": force_description,
        "force_body": force_body,
    })


def _append_gemini_targets_report(item: dict):
    report = GEMINI_TARGETS_JOB_STATUS.get("report") or []
    report.append(item)
    if len(report) > 500:
        report = report[-500:]
    GEMINI_TARGETS_JOB_STATUS["report"] = report


def _path_str_to_slug_tuple(path_str: str) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
    parts = [p.strip().lower() for p in (path_str or "").split("/") if p.strip()]
    if not parts:
        return None
    level1 = parts[0]
    level2 = parts[1] if len(parts) > 1 else None
    level3 = parts[2] if len(parts) > 2 else None
    return (level1, level2, level3)


def _gemini_targets_full_job(
    path_strs: List[str],
    force_description: bool,
    force_body: bool,
    delay: float,
):
    db = SessionLocal()
    try:
        _reset_gemini_targets_status(force_description, force_body)
        norm_paths = []
        for p in path_strs:
            k = (p or "").strip().lower()
            if k and k not in norm_paths:
                norm_paths.append(k)
        GEMINI_TARGETS_JOB_STATUS["total"] = len(norm_paths)
        import time

        for path_str in norm_paths:
            GEMINI_TARGETS_JOB_STATUS["current_path"] = path_str
            tup = _path_str_to_slug_tuple(path_str)
            if not tup:
                GEMINI_TARGETS_JOB_STATUS["failed"] += 1
                _append_gemini_targets_report({"path": path_str, "status": "failed", "message": "path không hợp lệ"})
                GEMINI_TARGETS_JOB_STATUS["processed"] += 1
                continue
            level1, level2, level3 = tup
            data = crud_product.get_category_seo_data(
                db,
                level1_slug=level1,
                level2_slug=level2,
                level3_slug=level3,
                is_active=True,
                image_limit=4,
            )
            if not data:
                GEMINI_TARGETS_JOB_STATUS["failed"] += 1
                _append_gemini_targets_report({"path": path_str, "status": "failed", "message": "Không resolve danh mục"})
                GEMINI_TARGETS_JOB_STATUS["processed"] += 1
                continue
            had_desc_before = bool((data.get("seo_description") or "").strip())
            had_body_before = bool((data.get("seo_body") or "").strip())
            did_desc = False
            did_body = False
            meta_err = None
            body_err = None
            try:
                did_desc = crud_product.ensure_category_seo_description(
                    db,
                    level1_slug=str(level1),
                    level2_slug=str(level2) if level2 else None,
                    level3_slug=str(level3) if level3 else None,
                    is_active=True,
                    force=bool(force_description),
                )
                if did_desc:
                    GEMINI_TARGETS_JOB_STATUS["meta_generated"] += 1
                else:
                    GEMINI_TARGETS_JOB_STATUS["meta_skipped"] += 1
            except Exception as e:
                meta_err = str(e)
                GEMINI_TARGETS_JOB_STATUS["failed"] += 1
                _append_gemini_targets_report({"path": path_str, "part": "meta", "status": "error", "message": meta_err})
            try:
                did_body = crud_product.ensure_category_seo_body(
                    db,
                    level1_slug=str(level1),
                    level2_slug=str(level2) if level2 else None,
                    level3_slug=str(level3) if level3 else None,
                    is_active=True,
                    force=bool(force_body),
                )
                if did_body:
                    GEMINI_TARGETS_JOB_STATUS["body_generated"] += 1
                else:
                    GEMINI_TARGETS_JOB_STATUS["body_skipped"] += 1
            except Exception as e:
                body_err = str(e)
                GEMINI_TARGETS_JOB_STATUS["failed"] += 1
                _append_gemini_targets_report({"path": path_str, "part": "body", "status": "error", "message": body_err})
            _append_gemini_targets_report({
                "path": path_str,
                "status": "ok",
                "meta": "error" if meta_err else ("generated" if did_desc else "skipped"),
                "body": "error" if body_err else ("generated" if did_body else "skipped"),
                "had_meta": had_desc_before,
                "had_body": had_body_before,
            })
            GEMINI_TARGETS_JOB_STATUS["processed"] += 1
            if delay and delay > 0:
                time.sleep(delay)
    finally:
        GEMINI_TARGETS_JOB_STATUS["running"] = False
        GEMINI_TARGETS_JOB_STATUS["current_path"] = None
        GEMINI_TARGETS_JOB_STATUS["finished_at"] = datetime.utcnow().isoformat()
        db.close()


def _generate_seo_bodies_job(force: bool, delay: float, path: Optional[str]):
    db = SessionLocal()
    try:
        _reset_seo_body_status(force, path)
        if path:
            parts = [p.strip().lower() for p in path.split("/") if p.strip()]
            if not parts:
                SEO_BODY_JOB_STATUS["running"] = False
                SEO_BODY_JOB_STATUS["finished_at"] = datetime.utcnow().isoformat()
                return
            level1 = parts[0]
            level2 = parts[1] if len(parts) > 1 else None
            level3 = parts[2] if len(parts) > 2 else None
            paths = [(level1, level2, level3)]
        else:
            tree = crud_product.get_category_tree_from_products(db, is_active=True)
            paths = _flatten_tree_to_paths(tree)

        SEO_BODY_JOB_STATUS["total"] = len(paths)

        for (level1, level2, level3) in paths:
            path_str = "/".join(x for x in (level1, level2, level3) if x)
            SEO_BODY_JOB_STATUS["current_path"] = path_str
            data = crud_product.get_category_seo_data(
                db,
                level1_slug=level1,
                level2_slug=level2,
                level3_slug=level3,
                is_active=True,
                image_limit=4,
            )
            if not data:
                SEO_BODY_JOB_STATUS["failed"] += 1
                _append_seo_body_report({"path": path_str, "status": "failed", "message": "Không resolve danh mục"})
                continue
            full_name = data.get("full_name", "")
            breadcrumb_names = data.get("breadcrumb_names", [])
            product_count = data.get("product_count", 0)
            sample_names = data.get("sample_product_names") or []
            sibling_names = crud_product.get_category_sibling_names(
                db, level1_slug=level1, level2_slug=level2, level3_slug=level3, is_active=True
            )
            seo_body = data.get("seo_body") or ""
            has_links = _has_seo_links(seo_body)
            sibling_mentions = _count_sibling_mentions(seo_body, sibling_names)
            if seo_body and not force:
                if has_links or sibling_mentions > 0:
                    SEO_BODY_JOB_STATUS["skipped"] += 1
                    _append_seo_body_report({
                        "path": path_str,
                        "status": "skipped",
                        "message": "Đã có SEO body và đã gắn link",
                        "seo_body_len": len(seo_body),
                        "has_links": True,
                        "sibling_count": len(sibling_names or []),
                        "sibling_mentions": sibling_mentions,
                    })
                    continue
                if not sibling_names:
                    SEO_BODY_JOB_STATUS["skipped"] += 1
                    _append_seo_body_report({
                        "path": path_str,
                        "status": "skipped",
                        "message": "Đã có SEO body nhưng không có danh mục anh em",
                        "seo_body_len": len(seo_body),
                        "has_links": False,
                        "sibling_count": 0,
                        "sibling_mentions": sibling_mentions,
                    })
                    continue

            body = generate_category_seo_body(
                category_name=full_name,
                breadcrumb_names=breadcrumb_names,
                product_count=product_count,
                sample_product_names=sample_names,
                related_category_names=sibling_names if sibling_names else None,
            )
            if not body:
                SEO_BODY_JOB_STATUS["failed"] += 1
                _append_seo_body_report({"path": path_str, "status": "failed", "message": "AI không trả về nội dung"})
                continue
            category_path = "/".join(_norm(x) for x in (level1, level2, level3) if x)
            crud_product.set_category_seo_body(db, category_path=category_path, seo_body=body)
            SEO_BODY_JOB_STATUS["done"] += 1
            _append_seo_body_report({
                "path": path_str,
                "status": "generated",
                "message": f"{len(body)} ký tự",
                "seo_body_len": len(seo_body),
                "has_links": has_links,
                "sibling_count": len(sibling_names or []),
                "sibling_mentions": sibling_mentions,
            })
            if delay and delay > 0:
                import time
                time.sleep(delay)
    finally:
        SEO_BODY_JOB_STATUS["running"] = False
        SEO_BODY_JOB_STATUS["current_path"] = None
        SEO_BODY_JOB_STATUS["finished_at"] = datetime.utcnow().isoformat()
        db.close()


def _apply_rules_to_product_model(product, rules: List[CategoryTransformRule]) -> bool:
    original = {
        "category": product.category,
        "subcategory": product.subcategory,
        "sub_subcategory": product.sub_subcategory,
    }
    updated = crud_product.apply_category_transform_rules_to_product(original.copy(), rules)
    if updated != original:
        product.category = updated.get("category")
        product.subcategory = updated.get("subcategory")
        product.sub_subcategory = updated.get("sub_subcategory")
        return True
    return False


@router.get("/scan")
def scan_categories(
    force_rescan: bool = Query(False, description="Rescan cả danh mục đã có mapping"),
    db: Session = Depends(get_db),
):
    """
    [ĐÃ TẮT] Trước đây scan tất cả danh mục và dùng AI để phát hiện danh mục trùng ý nghĩa.
    Theo yêu cầu mới: không còn tự động phân tích ý định SEO, chỉ dùng mapping do admin cấu hình thủ công.
    """
    result = scan_and_create_mappings(db, force_rescan=force_rescan)
    return {
        "status": "disabled",
        "message": "Tính năng scan tự động ý định SEO đã được tắt. Vui lòng cấu hình canonical/redirect thủ công nếu cần.",
        **result,
    }


@router.get("/mappings")
def get_mappings(
    status: Optional[str] = Query(None, description="Filter by status: pending, approved, rejected"),
    action: Optional[str] = Query(None, description="Filter by action: none, redirect, noindex"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    Lấy danh sách SEO mappings để admin review.
    """
    query = db.query(CategorySeoMapping)
    
    if status:
        query = query.filter(CategorySeoMapping.status == status)
    if action:
        query = query.filter(CategorySeoMapping.action == action)
    
    total = query.count()
    mappings = query.order_by(CategorySeoMapping.created_at.desc()).offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "mappings": [
            {
                "id": m.id,
                "source_name": m.source_name,
                "source_path": m.source_path,
                "source_slug": m.source_slug,
                "canonical_name": m.canonical_name,
                "canonical_path": m.canonical_path,
                "canonical_slug": m.canonical_slug,
                "action": m.action,
                "ai_confidence": m.ai_confidence,
                "ai_reason": m.ai_reason,
                "status": m.status,
                "reviewed_by": m.reviewed_by,
                "reviewed_at": m.reviewed_at.isoformat() if m.reviewed_at else None,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in mappings
        ]
    }


@router.get("/mappings/pending")
def get_pending_mappings(db: Session = Depends(get_db)):
    """
    Lấy danh sách mappings cần admin review (status=pending).
    """
    mappings = db.query(CategorySeoMapping).filter(
        CategorySeoMapping.status == "pending"
    ).order_by(CategorySeoMapping.ai_confidence.desc()).all()
    
    return {
        "total": len(mappings),
        "mappings": [
            {
                "id": m.id,
                "source_name": m.source_name,
                "source_path": m.source_path,
                "canonical_name": m.canonical_name,
                "canonical_path": m.canonical_path,
                "action": m.action,
                "ai_confidence": m.ai_confidence,
                "ai_reason": m.ai_reason,
            }
            for m in mappings
        ]
    }


@router.post("/mappings/{mapping_id}/approve")
def approve_mapping(
    mapping_id: int,
    admin_name: str = Query("admin", description="Tên admin approve"),
    db: Session = Depends(get_db),
):
    """
    Approve một SEO mapping.
    """
    mapping = db.query(CategorySeoMapping).filter(CategorySeoMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Không tìm thấy mapping")
    
    mapping.status = "approved"
    mapping.reviewed_by = admin_name
    mapping.reviewed_at = datetime.now()
    
    db.commit()
    
    return {
        "status": "success",
        "message": f"Đã approve mapping: {mapping.source_name} → {mapping.canonical_name or 'CANONICAL'}",
        "mapping_id": mapping_id
    }


@router.post("/mappings/{mapping_id}/reject")
def reject_mapping(
    mapping_id: int,
    admin_name: str = Query("admin", description="Tên admin reject"),
    db: Session = Depends(get_db),
):
    """
    Reject một SEO mapping (không redirect).
    """
    mapping = db.query(CategorySeoMapping).filter(CategorySeoMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Không tìm thấy mapping")
    
    mapping.status = "rejected"
    mapping.action = "none"
    mapping.reviewed_by = admin_name
    mapping.reviewed_at = datetime.now()
    
    db.commit()
    
    return {
        "status": "success",
        "message": f"Đã reject mapping: {mapping.source_name}",
        "mapping_id": mapping_id
    }


@router.put("/mappings/{mapping_id}")
def update_mapping(
    mapping_id: int,
    action: Optional[str] = Query(None, description="none, redirect, noindex, canonical_tag"),
    canonical_path: Optional[str] = Query(None, description="Path của trang canonical"),
    canonical_name: Optional[str] = Query(None, description="Tên trang canonical"),
    status: Optional[str] = Query(None, description="pending, approved, rejected"),
    admin_name: str = Query("admin", description="Tên admin"),
    db: Session = Depends(get_db),
):
    """
    Cập nhật một SEO mapping (admin chỉnh sửa).
    """
    mapping = db.query(CategorySeoMapping).filter(CategorySeoMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Không tìm thấy mapping")
    
    if action is not None:
        mapping.action = action
    if canonical_path is not None:
        mapping.canonical_path = canonical_path
    if canonical_name is not None:
        mapping.canonical_name = canonical_name
    if status is not None:
        mapping.status = status
    
    mapping.reviewed_by = admin_name
    mapping.reviewed_at = datetime.now()
    
    db.commit()
    
    return {
        "status": "success",
        "message": f"Đã cập nhật mapping: {mapping.source_name}",
        "mapping_id": mapping_id
    }


@router.get("/redirects")
def get_redirects(db: Session = Depends(get_db)):
    """
    Lấy danh sách tất cả redirects đã approved.
    Dùng cho frontend để redirect client-side hoặc middleware.
    """
    redirects = get_all_approved_redirects(db)
    return {
        "total": len(redirects),
        "redirects": redirects
    }


@router.get("/check-redirect")
def check_redirect(
    path: str = Query(..., description="Category path to check (e.g., giay-dep-nam/boot-nam)"),
    db: Session = Depends(get_db),
):
    """
    Kiểm tra một path: redirect hay noindex.
    Mỗi ý định tìm kiếm chỉ SEO một trang; trang cùng ý định khác → redirect hoặc noindex.
    Trả về: should_redirect, redirect_to, seo_indexable, canonical_url.
    """
    return get_category_seo_status(db, path)


@router.post("/merge-non-seo")
def merge_non_seo_categories(db: Session = Depends(get_db)):
    """
    [ĐÃ TẮT] Trước đây gộp danh mục không được SEO vào danh mục canonical (chuẩn SEO)
    bằng cách chuyển toàn bộ sản phẩm sang danh mục đại diện.

    Theo yêu cầu mới: KHÔNG tự động gộp hay di chuyển sản phẩm giữa các danh mục nữa.
    """
    result = merge_non_seo_categories_to_canonical(db)
    return {
        "status": "disabled",
        "message": "Tính năng gộp sản phẩm theo intent SEO đã được tắt. Hệ thống sẽ giữ nguyên danh mục của sản phẩm.",
        "display_note": (
            "Không còn tự động chuyển sản phẩm giữa các danh mục dựa trên mapping SEO. "
            "Nếu cần thay đổi, hãy chỉnh sửa danh mục sản phẩm thủ công."
        ),
        **result,
    }


@router.get("/categories")
def get_all_categories(db: Session = Depends(get_db)):
    """
    Lấy danh sách tất cả danh mục từ sản phẩm.
    """
    categories = get_all_category_paths(db)
    return {
        "total": len(categories),
        "categories": categories
    }


@router.get("/summary")
def get_seo_summary(db: Session = Depends(get_db)):
    """
    Lấy tổng quan tình trạng SEO danh mục.
    """
    total_categories = len(get_all_category_paths(db))
    
    total_mappings = db.query(CategorySeoMapping).count()
    pending = db.query(CategorySeoMapping).filter(CategorySeoMapping.status == "pending").count()
    approved = db.query(CategorySeoMapping).filter(CategorySeoMapping.status == "approved").count()
    rejected = db.query(CategorySeoMapping).filter(CategorySeoMapping.status == "rejected").count()
    
    redirects = db.query(CategorySeoMapping).filter(
        CategorySeoMapping.status == "approved",
        CategorySeoMapping.action == "redirect"
    ).count()
    
    return {
        "total_categories": total_categories,
        "total_mappings": total_mappings,
        "pending_review": pending,
        "approved": approved,
        "rejected": rejected,
        "active_redirects": redirects,
        "coverage": f"{(total_mappings / total_categories * 100):.1f}%" if total_categories > 0 else "0%"
    }


# ========== DICTIONARY ENDPOINTS ==========

@router.get("/dictionary")
def get_dictionary(db: Session = Depends(get_db)):
    """
    Lấy từ điển đồng nghĩa.
    """
    entries = db.query(CategorySeoDictionary).filter(
        CategorySeoDictionary.is_active == True
    ).all()
    
    return {
        "total": len(entries),
        "entries": [
            {
                "id": e.id,
                "term": e.term,
                "synonyms": e.synonyms,
                "canonical_term": e.canonical_term,
                "term_type": e.term_type,
            }
            for e in entries
        ]
    }


@router.post("/dictionary")
def add_dictionary_entry(
    term: str = Query(..., description="Từ/cụm từ gốc"),
    synonyms: str = Query(..., description="Các từ đồng nghĩa (comma-separated)"),
    canonical_term: str = Query(..., description="Từ canonical (ưu tiên dùng)"),
    term_type: str = Query("category", description="Loại: category, material, style, color"),
    db: Session = Depends(get_db),
):
    """
    Thêm từ vào từ điển đồng nghĩa.
    """
    # Check trùng
    existing = db.query(CategorySeoDictionary).filter(
        CategorySeoDictionary.term == term.lower().strip()
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail=f"Từ '{term}' đã tồn tại trong từ điển")
    
    entry = CategorySeoDictionary(
        term=term.lower().strip(),
        synonyms=synonyms,
        canonical_term=canonical_term,
        term_type=term_type,
        is_active=True,
    )
    db.add(entry)
    db.commit()
    
    return {
        "status": "success",
        "message": f"Đã thêm từ '{term}' vào từ điển",
        "entry_id": entry.id
    }


# ========== CATEGORY MANAGEMENT ENDPOINTS ==========

@router.post("/move-level2-to-level3")
def move_level2_to_level3(
    category: str = Query(..., description="Tên danh mục cấp 1"),
    subcategory: str = Query(..., description="Tên danh mục cấp 2 cần chuyển xuống cấp 3"),
    target_subcategory: str = Query(..., description="Tên danh mục cấp 2 đích (sẽ trở thành parent)"),
    new_sub_subcategory_name: Optional[str] = Query(None, description="Tên mới cho cấp 3 (mặc định giữ nguyên tên)"),
    db: Session = Depends(get_db),
):
    """
    Chuyển danh mục cấp 2 xuống làm danh mục cấp 3.
    Ví dụ: Giày dép Nam > Giày lười nam → chuyển xuống → Giày dép Nam > Giày tây nam > Giày lười nam
    """
    from app.models.product import Product
    
    # Tìm các sản phẩm thuộc danh mục cấp 2 cần chuyển
    products = db.query(Product).filter(
        Product.category == category,
        Product.subcategory == subcategory
    ).all()
    
    if not products:
        raise HTTPException(
            status_code=404, 
            detail=f"Không tìm thấy sản phẩm nào trong danh mục '{category} > {subcategory}'"
        )
    
    # Tên cấp 3 mới
    new_name = new_sub_subcategory_name if new_sub_subcategory_name else subcategory
    
    # Cập nhật tất cả sản phẩm: giữ nguyên danh mục cấp 2 đích, chỉ chuyển cấp 2 xuống cấp 3
    updated_count = 0
    for product in products:
        product.subcategory = target_subcategory
        if not product.sub_subcategory or not str(product.sub_subcategory).strip():
            # Nếu chưa có cấp 3, gán tên cấp 2 cũ làm cấp 3
            product.sub_subcategory = new_name
        updated_count += 1
    
    db.commit()

    
    return {
        "status": "success",
        "message": f"Đã chuyển '{subcategory}' xuống cấp 3 dưới '{target_subcategory}'",
        "products_updated": updated_count,
        "from": f"{category} > {subcategory}",
        "to": f"{category} > {target_subcategory} > {new_name}"
    }


@router.post("/move-level3-to-level2")
def move_level3_to_level2(
    category: str = Query(..., description="Tên danh mục cấp 1"),
    subcategory: str = Query(..., description="Tên danh mục cấp 2 hiện tại"),
    sub_subcategory: str = Query(..., description="Tên danh mục cấp 3 cần chuyển lên cấp 2"),
    new_subcategory_name: Optional[str] = Query(None, description="Tên mới cho cấp 2 (mặc định giữ nguyên tên)"),
    db: Session = Depends(get_db),
):
    """
    Chuyển danh mục cấp 3 lên làm danh mục cấp 2.
    Ví dụ: Giày dép Nam > Giày tây nam > Giày lười da → chuyển lên → Giày dép Nam > Giày lười da
    """
    from app.models.product import Product
    
    # Tìm các sản phẩm thuộc danh mục cấp 3 cần chuyển
    _fc = category_field_equals_ci(Product.category, category)
    _fs = category_field_equals_ci(Product.subcategory, subcategory)
    _fss = category_field_equals_ci(Product.sub_subcategory, sub_subcategory)
    if _fc is None or _fs is None or _fss is None:
        raise HTTPException(
            status_code=400,
            detail="Thiếu hoặc không hợp lệ category / subcategory / sub_subcategory",
        )
    products = db.query(Product).filter(
        _fc, _fs, _fss,
    ).all()
    
    # Tên cấp 2 mới
    new_name = new_subcategory_name if new_subcategory_name else sub_subcategory
    
    # Cập nhật tất cả sản phẩm: chuyển toàn bộ nhóm sang cấp 2 mới
    updated_count = 0
    for product in products:
        old_subcategory = product.subcategory
        product.subcategory = new_name
        # Chỉ đổi cấp 3 khi là danh mục đang chuyển hoặc đang trống
        if not product.sub_subcategory or str(product.sub_subcategory).strip() == str(sub_subcategory).strip():
            product.sub_subcategory = old_subcategory
        updated_count += 1
    
    db.commit()

    
    return {
        "status": "success",
        "message": f"Đã chuyển '{sub_subcategory}' lên cấp 2",
        "products_updated": updated_count,
        "from": f"{category} > {subcategory} > {sub_subcategory}",
        "to": f"{category} > {new_name}"
    }


@router.post("/swap-level2-level3")
def swap_level2_level3(
    category: str = Query(..., description="Tên danh mục cấp 1"),
    subcategory: str = Query(..., description="Tên danh mục cấp 2"),
    sub_subcategory: str = Query(..., description="Tên danh mục cấp 3 cần đổi lên cấp 2"),
    db: Session = Depends(get_db),
):
    """
    Đổi cấp danh mục giữa cấp 2 và cấp 3 trong cùng nhóm.
    Ví dụ: Giày dép Nam > Giày tây Nam > (Giày da Nam, Giày Monkstrap, Giày Oxford)
    Đổi 'Giày da Nam' lên cấp 2 => cấp 2 mới là 'Giày da Nam',
    cấp 3 sẽ gồm 'Giày tây Nam', 'Giày Monkstrap', 'Giày Oxford'.
    """
    from app.models.product import Product

    products = db.query(Product).filter(
        Product.category == category,
        Product.subcategory == subcategory,
    ).all()

    if not products:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy sản phẩm nào trong danh mục '{category} > {subcategory}'"
        )

    existing = db.query(CategoryTransformRule).filter(
        CategoryTransformRule.rule_type == "swap_level2_level3",
        CategoryTransformRule.category == category,
        CategoryTransformRule.subcategory == subcategory,
        CategoryTransformRule.sub_subcategory == sub_subcategory,
    ).first()

    inverse = db.query(CategoryTransformRule).filter(
        CategoryTransformRule.rule_type == "swap_level2_level3",
        CategoryTransformRule.category == category,
        CategoryTransformRule.subcategory == sub_subcategory,
        CategoryTransformRule.sub_subcategory == subcategory,
    ).first()

    if inverse:
        # Đang tạo rule ngược lại -> xóa rule cũ và khôi phục sản phẩm
        products = db.query(Product).filter(
            Product.category == category,
            Product.subcategory == sub_subcategory,
        ).all()
        updated_count = 0
        for product in products:
            product.subcategory = subcategory
            if str(product.sub_subcategory or "").strip() == str(subcategory).strip():
                product.sub_subcategory = sub_subcategory
            updated_count += 1
        db.delete(inverse)
        db.commit()
        return {
            "status": "success",
            "message": f"Đã khôi phục rule đổi cấp: '{sub_subcategory}' → '{subcategory}'",
            "products_updated": updated_count,
            "from": f"{category} > {sub_subcategory} > {subcategory}",
            "to": f"{category} > {subcategory} > {sub_subcategory}"
        }

    if existing:
        return {
            "status": "success",
            "message": f"Rule đã tồn tại: '{subcategory}' ↔ '{sub_subcategory}'",
            "products_updated": 0,
            "from": f"{category} > {subcategory} > {sub_subcategory}",
            "to": f"{category} > {sub_subcategory} > {subcategory}"
        }

    updated_count = 0
    for product in products:
        old_subcategory = product.subcategory
        product.subcategory = sub_subcategory
        if not product.sub_subcategory or str(product.sub_subcategory).strip() == "":
            product.sub_subcategory = old_subcategory
        elif str(product.sub_subcategory).strip() == str(sub_subcategory).strip():
            product.sub_subcategory = old_subcategory
        updated_count += 1

    db.commit()

    db.add(CategoryFinalMapping(
        from_category=category,
        from_subcategory=subcategory,
        from_sub_subcategory=sub_subcategory,
        to_category=category,
        to_subcategory=sub_subcategory,
        to_sub_subcategory=subcategory,
    ))
    db.commit()

    return {
        "status": "success",
        "message": f"Đã đổi cấp: '{subcategory}' ↔ '{sub_subcategory}'",
        "products_updated": updated_count,
        "from": f"{category} > {subcategory} > {sub_subcategory}",
        "to": f"{category} > {sub_subcategory} > {subcategory}"
    }


@router.post("/rename-category")
def rename_category(
    level: int = Query(..., description="Cấp danh mục cần đổi tên (2 hoặc 3)"),
    category: str = Query(..., description="Tên danh mục cấp 1"),
    subcategory: Optional[str] = Query(None, description="Tên danh mục cấp 2 hiện tại"),
    sub_subcategory: Optional[str] = Query(None, description="Tên danh mục cấp 3 hiện tại"),
    new_name: str = Query(..., description="Tên danh mục mới"),
    db: Session = Depends(get_db),
):
    """
    Đổi tên danh mục cấp 2 hoặc cấp 3. Sản phẩm sẽ được cập nhật theo.
    """
    from app.models.product import Product

    if level not in (2, 3):
        raise HTTPException(status_code=400, detail="level phải là 2 hoặc 3")
    if not new_name or not str(new_name).strip():
        raise HTTPException(status_code=400, detail="Tên mới không được rỗng")

    updated_count = 0
    level1_slug = slugify_vietnamese(category)
    if level == 2:
        if not subcategory:
            raise HTTPException(status_code=400, detail="Thiếu tên danh mục cấp 2")
        old_path = "/".join([level1_slug, slugify_vietnamese(subcategory)])
        new_path = "/".join([level1_slug, slugify_vietnamese(new_name)])
        products = db.query(Product).filter(
            Product.category == category,
            Product.subcategory == subcategory
        ).all()
        for product in products:
            product.subcategory = new_name
            updated_count += 1
        db.commit()

        # Update SEO meta path
        meta_old = db.query(CategorySeoMeta).filter(CategorySeoMeta.category_path == old_path).first()
        meta_new = db.query(CategorySeoMeta).filter(CategorySeoMeta.category_path == new_path).first()
        if meta_old:
            if meta_new:
                for field in ["image_1", "image_2", "image_3", "image_4", "seo_description", "seo_body"]:
                    val = getattr(meta_old, field, None)
                    if val:
                        setattr(meta_new, field, val)
                db.delete(meta_old)
            else:
                meta_old.category_path = new_path
        db.add(CategoryFinalMapping(
            from_category=category,
            from_subcategory=subcategory,
            from_sub_subcategory="",
            to_category=category,
            to_subcategory=new_name,
            to_sub_subcategory="",
        ))
        db.commit()
        return {
            "status": "success",
            "message": f"Đã đổi tên cấp 2: '{subcategory}' → '{new_name}'",
            "products_updated": updated_count,
        }

    if not subcategory or not sub_subcategory:
        raise HTTPException(status_code=400, detail="Thiếu tên danh mục cấp 2 hoặc cấp 3")
    level2_slug = slugify_vietnamese(subcategory)
    old_path = "/".join([level1_slug, level2_slug, slugify_vietnamese(sub_subcategory)])
    new_path = "/".join([level1_slug, level2_slug, slugify_vietnamese(new_name)])
    _fc = category_field_equals_ci(Product.category, category)
    _fs = category_field_equals_ci(Product.subcategory, subcategory)
    _fss = category_field_equals_ci(Product.sub_subcategory, sub_subcategory)
    if _fc is None or _fs is None or _fss is None:
        raise HTTPException(
            status_code=400,
            detail="Thiếu hoặc không hợp lệ category / subcategory / sub_subcategory",
        )
    products = db.query(Product).filter(
        _fc, _fs, _fss,
    ).all()
    for product in products:
        product.sub_subcategory = new_name
        updated_count += 1
    db.commit()

    meta_old = db.query(CategorySeoMeta).filter(CategorySeoMeta.category_path == old_path).first()
    meta_new = db.query(CategorySeoMeta).filter(CategorySeoMeta.category_path == new_path).first()
    if meta_old:
        if meta_new:
            for field in ["image_1", "image_2", "image_3", "image_4", "seo_description", "seo_body"]:
                val = getattr(meta_old, field, None)
                if val:
                    setattr(meta_new, field, val)
            db.delete(meta_old)
        else:
            meta_old.category_path = new_path

    db.add(CategoryFinalMapping(
        from_category=category,
        from_subcategory=subcategory,
        from_sub_subcategory=sub_subcategory,
        to_category=category,
        to_subcategory=subcategory,
        to_sub_subcategory=new_name,
    ))
    db.commit()
    return {
        "status": "success",
        "message": f"Đã đổi tên cấp 3: '{sub_subcategory}' → '{new_name}'",
        "products_updated": updated_count,
    }


@router.get("/app-settings")
def get_category_seo_app_settings(db: Session = Depends(get_db)):
    """
    Trạng thái Gemini SEO danh mục: admin bật / .env VPS cho phép / hiệu lực cuối cùng.
    """
    return crud_product.get_category_gemini_auto_settings_snapshot(db)


@router.put("/app-settings")
def put_category_seo_app_settings(payload: dict = Body(...), db: Session = Depends(get_db)):
    """Bật/tắt chạy tự động sau import và khi tạo-sửa SP (chỉ khi máy chủ đã cho phép qua .env)."""
    val = bool(payload.get("gemini_auto_enabled"))
    if val and not getattr(settings, "CATEGORY_GEMINI_SEO_AUTO_ENABLED", False):
        raise HTTPException(
            status_code=400,
            detail=(
                "Không thể bật tự động: chỉ VPS (ENVIRONMENT=staging|production và "
                "CATEGORY_GEMINI_SEO_AUTO_ENABLED=true trong .env) mới cho phép. "
                "Trên máy dev hãy dùng nút sinh Gemini thủ công trong trang này."
            ),
        )
    row = db.query(CategorySeoSettings).filter(CategorySeoSettings.id == 1).first()
    if row is None:
        row = CategorySeoSettings(id=1, gemini_auto_enabled=val)
        db.add(row)
    else:
        row.gemini_auto_enabled = val
    db.commit()
    return {"status": "success", **crud_product.get_category_gemini_auto_settings_snapshot(db)}


@router.get("/gemini-targets/catalog")
def gemini_targets_catalog(db: Session = Depends(get_db)):
    """
    Danh sách danh mục từ SP + trạng thái meta/body + đã đánh dấu Gemini đích hay chưa (lưu DB).

    Tránh gọi get_category_seo_data() theo từng path (mỗi lần rebuild cây + có thể query SP lấy ảnh) —
    đó là nguyên nhân hay gây timeout 504 proxy khi có nhiều danh mục.
    """
    tree = crud_product.get_category_tree_from_products(db, is_active=True)
    paths = _flatten_tree_to_paths(tree)
    meta_map = {
        (m.category_path or "").strip().lower(): m
        for m in db.query(CategorySeoMeta).all()
    }
    target_set = {
        (t.category_path or "").strip().lower()
        for t in db.query(CategorySeoGeminiTarget).all()
    }
    rows = []
    for (level1, level2, level3) in paths:
        path_str = "/".join(x for x in (level1, level2, level3) if x)
        bc = crud_product.resolve_category_breadcrumb_names_from_tree(tree, level1, level2, level3)
        if not bc:
            continue
        n = len(bc)
        if n == 1:
            full_name = bc[0]
        elif n == 2:
            full_name = f"{bc[0]} - {bc[1]}"
        else:
            full_name = f"{bc[0]} - {bc[1]} - {bc[2]}"
        product_count = crud_product.count_products_for_category_path(
            db,
            bc[0],
            bc[1] if n > 1 else None,
            bc[2] if n > 2 else None,
            is_active=True,
        )
        meta = meta_map.get(path_str.strip().lower())
        desc_text = ((getattr(meta, "seo_description", None) or "") if meta else "").strip()
        body_text = ((getattr(meta, "seo_body", None) or "") if meta else "").strip()
        rows.append({
            "path": path_str,
            "breadcrumb_label": full_name,
            "level": n,
            "product_count": int(product_count or 0),
            "has_seo_description": bool(desc_text),
            "has_seo_body": bool(body_text),
            "gemini_enabled": path_str.strip().lower() in target_set,
        })

    total = len(rows)
    with_p = sum(1 for r in rows if r["product_count"] > 0)
    ge = sum(1 for r in rows if r["gemini_enabled"])
    miss_d = sum(1 for r in rows if r["gemini_enabled"] and not r["has_seo_description"])
    miss_b = sum(1 for r in rows if r["gemini_enabled"] and not r["has_seo_body"])
    return {
        "total": total,
        "summary": {
            "paths_total": total,
            "with_products": with_p,
            "gemini_target_count": ge,
            "gemini_missing_description": miss_d,
            "gemini_missing_body": miss_b,
            "not_marked_for_gemini": total - ge,
        },
        "rows": rows,
    }


@router.put("/gemini-targets")
def gemini_targets_toggle(payload: dict = Body(...), db: Session = Depends(get_db)):
    """Bật/tắt danh mục trong whitelist Gemini (category_path slug chữ thường)."""
    raw = payload.get("paths")
    paths = raw if isinstance(raw, list) else []
    enabled = bool(payload.get("enabled", True))
    affected = 0
    for p in paths:
        key = (str(p) if p is not None else "").strip().lower()
        if not key:
            continue
        existing = db.query(CategorySeoGeminiTarget).filter(CategorySeoGeminiTarget.category_path == key).first()
        if enabled:
            if not existing:
                db.add(CategorySeoGeminiTarget(category_path=key))
                affected += 1
        else:
            if existing:
                db.delete(existing)
                affected += 1
    db.commit()
    return {"status": "success", "affected": affected}


@router.post("/gemini-targets/run")
def gemini_targets_run(background_tasks: BackgroundTasks, payload: dict = Body(default_factory=dict)):
    """
    Sinh meta description + seo_body (Gemini) cho danh sách path.
    Nếu body.paths rỗng/không gửi → chạy toàn bộ path đang có trong whitelist DB.
    """
    if SEO_BODY_JOB_STATUS.get("running") or GEMINI_TARGETS_JOB_STATUS.get("running"):
        raise HTTPException(status_code=409, detail="Đang có job SEO chạy, vui lòng đợi xong.")

    raw_paths = payload.get("paths")
    force_description = bool(payload.get("force_description", False))
    force_body = bool(payload.get("force_body", False))
    try:
        delay = float(payload.get("delay") if payload.get("delay") is not None else 1.2)
    except (TypeError, ValueError):
        delay = 1.2
    if delay < 0:
        delay = 0

    db = SessionLocal()
    try:
        if isinstance(raw_paths, list) and len(raw_paths) > 0:
            path_list = list({(str(p) if p is not None else "").strip().lower() for p in raw_paths if (str(p) if p is not None else "").strip()})
        else:
            path_list = sorted({(r.category_path or "").strip().lower() for r in db.query(CategorySeoGeminiTarget).all() if (r.category_path or "").strip()})
    finally:
        db.close()

    if not path_list:
        raise HTTPException(
            status_code=400,
            detail="Không có danh mục để chạy: thêm path vào Gemini đích hoặc gửi paths trong body.",
        )

    background_tasks.add_task(
        _gemini_targets_full_job,
        path_list,
        force_description,
        force_body,
        delay,
    )
    return {
        "status": "started",
        "path_count": len(path_list),
        "force_description": force_description,
        "force_body": force_body,
        "delay": delay,
    }


@router.get("/gemini-targets/status")
def gemini_targets_run_status():
    return GEMINI_TARGETS_JOB_STATUS


@router.post("/seo-bodies/generate")
def generate_seo_bodies(
    background_tasks: BackgroundTasks,
    force: bool = Query(False, description="Ghi đè cả khi đã có seo_body"),
    dry_run: bool = Query(False, description="Chỉ trả về danh sách path"),
    path: Optional[str] = Query(None, description="Chỉ generate 1 path, VD: giay-dep-nam/giay-tay-nam/giay-da-nam"),
    delay: float = Query(1.5, ge=0, description="Nghỉ giữa mỗi lần gọi AI (giây)"),
):
    """
    Tạo lại seo_body cho danh mục (Gemini).
    Nếu dry_run=true sẽ chỉ trả danh sách path.
    """
    if not dry_run and (SEO_BODY_JOB_STATUS.get("running") or GEMINI_TARGETS_JOB_STATUS.get("running")):
        raise HTTPException(status_code=409, detail="Đang có job SEO chạy, vui lòng đợi xong.")
    if dry_run:
        db = SessionLocal()
        try:
            if path:
                parts = [p.strip().lower() for p in path.split("/") if p.strip()]
                if not parts:
                    return {"status": "error", "message": "path không hợp lệ", "paths": []}
                level1 = parts[0]
                level2 = parts[1] if len(parts) > 1 else None
                level3 = parts[2] if len(parts) > 2 else None
                paths = [(level1, level2, level3)]
            else:
                tree = crud_product.get_category_tree_from_products(db, is_active=True)
                paths = _flatten_tree_to_paths(tree)
            path_strs = ["/".join(x for x in p if x) for p in paths]
            return {"status": "dry_run", "total": len(path_strs), "paths": path_strs}
        finally:
            db.close()

    background_tasks.add_task(_generate_seo_bodies_job, force, delay, path)
    return {
        "status": "started",
        "message": "Đã bắt đầu tạo lại SEO body. Vui lòng chờ hoàn tất.",
        "force": force,
        "path": path,
    }


@router.get("/seo-bodies/status")
def get_seo_bodies_status():
    return SEO_BODY_JOB_STATUS


# ========== CATEGORY TRANSFORM RULES ==========

@router.get("/rules")
def get_transform_rules(db: Session = Depends(get_db)):
    rules = db.query(CategoryTransformRule).order_by(CategoryTransformRule.created_at.desc()).all()
    return {
        "total": len(rules),
        "rules": [
            {
                "id": r.id,
                "rule_type": r.rule_type,
                "level": r.level,
                "category": r.category,
                "subcategory": r.subcategory,
                "sub_subcategory": r.sub_subcategory,
                "source_subcategories": r.source_subcategories or [],
                "target_name": r.target_name,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rules
        ]
    }


@router.post("/rules")
def create_transform_rule(
    rule_type: str = Query(..., description="Loại rule"),
    level: Optional[int] = Query(None, description="Cấp danh mục"),
    category: str = Query(..., description="Danh mục cấp 1"),
    subcategory: Optional[str] = Query(None, description="Danh mục cấp 2"),
    sub_subcategory: Optional[str] = Query(None, description="Danh mục cấp 3"),
    source_subcategories: Optional[str] = Query(None, description="Danh sách nguồn, phân tách dấu phẩy"),
    target_name: Optional[str] = Query(None, description="Tên đích"),
    db: Session = Depends(get_db),
):
    sources = [s.strip() for s in (source_subcategories or "").split(",") if s.strip()]
    rule = CategoryTransformRule(
        rule_type=rule_type,
        level=level,
        category=category,
        subcategory=subcategory,
        sub_subcategory=sub_subcategory,
        source_subcategories=sources or None,
        target_name=target_name,
    )
    db.add(rule)
    db.commit()
    return {"status": "success", "rule_id": rule.id}


@router.put("/rules/{rule_id}")
def update_transform_rule(
    rule_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    rule = db.query(CategoryTransformRule).filter(CategoryTransformRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Không tìm thấy rule")

    for field in ["rule_type", "level", "category", "subcategory", "sub_subcategory", "source_subcategories", "target_name"]:
        if field in payload:
            setattr(rule, field, payload[field])
    db.commit()
    return {"status": "success", "rule_id": rule.id}


@router.delete("/rules/{rule_id}")
def delete_transform_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(CategoryTransformRule).filter(CategoryTransformRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Không tìm thấy rule")
    db.delete(rule)
    db.commit()
    return {"status": "success"}


@router.post("/rules/apply")
def apply_rules_to_existing_products(db: Session = Depends(get_db)):
    rules = db.query(CategoryTransformRule).order_by(CategoryTransformRule.created_at.asc()).all()
    if not rules:
        return {"status": "success", "updated": 0}
    products = db.query(Product).all()
    updated = 0
    for product in products:
        if _apply_rules_to_product_model(product, rules):
            updated += 1
    db.commit()
    return {"status": "success", "updated": updated}


@router.get("/rules/export")
def export_rules(db: Session = Depends(get_db)):
    rules = db.query(CategoryTransformRule).order_by(CategoryTransformRule.created_at.asc()).all()
    return {
        "rules": [
            {
                "rule_type": r.rule_type,
                "level": r.level,
                "category": r.category,
                "subcategory": r.subcategory,
                "sub_subcategory": r.sub_subcategory,
                "source_subcategories": r.source_subcategories or [],
                "target_name": r.target_name,
            }
            for r in rules
        ]
    }


@router.post("/rules/import")
def import_rules(
    replace: bool = Query(False, description="Xóa rule cũ trước khi import"),
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    rules = payload.get("rules") or []
    if replace:
        db.query(CategoryTransformRule).delete()
        db.commit()
    created = 0
    for r in rules:
        rule = CategoryTransformRule(
            rule_type=r.get("rule_type"),
            level=r.get("level"),
            category=r.get("category"),
            subcategory=r.get("subcategory"),
            sub_subcategory=r.get("sub_subcategory"),
            source_subcategories=r.get("source_subcategories") or None,
            target_name=r.get("target_name"),
        )
        db.add(rule)
        created += 1
    db.commit()
    return {"status": "success", "created": created, "replaced": replace}


# ========== FINAL CATEGORY MAPPINGS ==========

@router.get("/mappings-final")
def get_final_mappings(db: Session = Depends(get_db)):
    mappings = db.query(CategoryFinalMapping).order_by(CategoryFinalMapping.created_at.desc()).all()
    return {
        "total": len(mappings),
        "mappings": [
            {
                "id": m.id,
                "from_category": m.from_category,
                "from_subcategory": m.from_subcategory,
                "from_sub_subcategory": m.from_sub_subcategory,
                "to_category": m.to_category,
                "to_subcategory": m.to_subcategory,
                "to_sub_subcategory": m.to_sub_subcategory,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in mappings
        ]
    }


@router.post("/mappings-final")
def create_final_mapping(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    rule = CategoryFinalMapping(
        from_category=payload.get("from_category"),
        from_subcategory=payload.get("from_subcategory") or "",
        from_sub_subcategory=payload.get("from_sub_subcategory") or "",
        to_category=payload.get("to_category"),
        to_subcategory=payload.get("to_subcategory") or "",
        to_sub_subcategory=payload.get("to_sub_subcategory") or "",
    )
    existing = db.query(CategoryFinalMapping).filter(
        CategoryFinalMapping.from_category == rule.from_category,
        CategoryFinalMapping.from_subcategory == rule.from_subcategory,
        CategoryFinalMapping.from_sub_subcategory == rule.from_sub_subcategory,
    ).first()
    if existing:
        db.delete(existing)
        db.commit()
    db.add(rule)
    db.commit()
    db.refresh(rule)
    products_updated = crud_product.batch_apply_final_mapping_to_products(db, rule)
    db.commit()
    return {"status": "success", "mapping_id": rule.id, "products_updated": products_updated}


@router.put("/mappings-final/{mapping_id}")
def update_final_mapping(
    mapping_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    mapping = db.query(CategoryFinalMapping).filter(CategoryFinalMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Không tìm thấy mapping")
    for field in [
        "from_category",
        "from_subcategory",
        "from_sub_subcategory",
        "to_category",
        "to_subcategory",
        "to_sub_subcategory",
    ]:
        if field in payload:
            setattr(mapping, field, payload[field] or "")
    db.commit()
    products_updated = crud_product.batch_apply_final_mapping_to_products(db, mapping)
    db.commit()
    return {"status": "success", "mapping_id": mapping.id, "products_updated": products_updated}


@router.delete("/mappings-final/{mapping_id}")
def delete_final_mapping(mapping_id: int, db: Session = Depends(get_db)):
    mapping = db.query(CategoryFinalMapping).filter(CategoryFinalMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Không tìm thấy mapping")
    db.delete(mapping)
    db.commit()
    return {"status": "success"}


@router.post("/mappings-final/apply")
def apply_final_mappings(db: Session = Depends(get_db)):
    """
    Đồng bộ lại sản phẩm theo các mapping đã lưu — **không** reset raw_* hay áp wildcard L2 lên toàn bộ SP.

    Chỉ cập nhật các hàng khớp đúng (category, subcategory, sub_subcategory) nguồn có **cấp 3 đầy đủ**
    (`from_sub_subcategory` không rỗng), giống lúc POST/PUT mapping.
    """
    mappings = db.query(CategoryFinalMapping).order_by(CategoryFinalMapping.id.asc()).all()
    total_updates = 0
    for m in mappings:
        total_updates += crud_product.batch_apply_final_mapping_to_products(db, m)
    db.commit()
    return {"status": "success", "updated": total_updates}


@router.get("/mappings-final/export")
def export_final_mappings(db: Session = Depends(get_db)):
    mappings = db.query(CategoryFinalMapping).order_by(CategoryFinalMapping.created_at.asc()).all()
    return {
        "mappings": [
            {
                "from_category": m.from_category,
                "from_subcategory": m.from_subcategory,
                "from_sub_subcategory": m.from_sub_subcategory,
                "to_category": m.to_category,
                "to_subcategory": m.to_subcategory,
                "to_sub_subcategory": m.to_sub_subcategory,
            }
            for m in mappings
        ]
    }


@router.post("/mappings-final/import")
def import_final_mappings(
    replace: bool = Query(False, description="Xóa mapping cũ trước khi import"),
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    items = payload.get("mappings") or []
    if replace:
        db.query(CategoryFinalMapping).delete()
        db.commit()
    created = 0
    for r in items:
        mapping = CategoryFinalMapping(
            from_category=r.get("from_category"),
            from_subcategory=r.get("from_subcategory") or "",
            from_sub_subcategory=r.get("from_sub_subcategory") or "",
            to_category=r.get("to_category"),
            to_subcategory=r.get("to_subcategory") or "",
            to_sub_subcategory=r.get("to_sub_subcategory") or "",
        )
        db.add(mapping)
        created += 1
    db.commit()
    products_updated = 0
    for m in db.query(CategoryFinalMapping).order_by(CategoryFinalMapping.id.asc()).all():
        products_updated += crud_product.batch_apply_final_mapping_to_products(db, m)
    db.commit()
    return {"status": "success", "created": created, "replaced": replace, "products_updated": products_updated}


@router.post("/merge-level2")
def merge_level2_categories(
    category: str = Query(..., description="Tên danh mục cấp 1"),
    source_subcategories: List[str] = Query(..., description="Danh sách danh mục cấp 2 nguồn cần gộp"),
    target_subcategory: Optional[str] = Query(None, description="Tên danh mục cấp 2 đích (gộp vào đây)"),
    new_target_name: Optional[str] = Query(None, description="Tên danh mục cấp 2 mới (nếu muốn tạo mới)"),
    db: Session = Depends(get_db),
):
    """
    Gộp nhiều danh mục cấp 2 thành một.
    Ví dụ: Gộp "Giày boot Nam", "Boot Chelsea Nam", "Boot Cổ Cao Nam" → "Giày boot Nam"
    Tất cả sản phẩm sẽ được chuyển sang danh mục đích.
    """
    from app.models.product import Product
    
    if not source_subcategories or len(source_subcategories) == 0:
        raise HTTPException(status_code=400, detail="Danh sách danh mục nguồn không được rỗng")
    
    if not target_subcategory and not new_target_name:
        raise HTTPException(status_code=400, detail="Cần chọn danh mục đích hoặc nhập tên danh mục mới")
    if target_subcategory and new_target_name:
        raise HTTPException(status_code=400, detail="Chỉ được chọn danh mục đích hoặc tạo mới, không chọn cả hai")
    
    # Tìm tất cả sản phẩm thuộc các danh mục nguồn
    products = db.query(Product).filter(
        Product.category == category,
        Product.subcategory.in_(source_subcategories)
    ).all()
    
    if not products:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy sản phẩm nào trong các danh mục cần gộp"
        )
    
    # Cập nhật tất cả sản phẩm sang danh mục đích
    updated_count = 0
    final_target = new_target_name or target_subcategory
    for product in products:
        product.subcategory = final_target
        updated_count += 1
    
    db.commit()

    for src in source_subcategories:
        existing = db.query(CategoryFinalMapping).filter(
            CategoryFinalMapping.from_category == category,
            CategoryFinalMapping.from_subcategory == src,
            CategoryFinalMapping.from_sub_subcategory == ""
        ).first()
        if existing:
            db.delete(existing)
        db.add(CategoryFinalMapping(
            from_category=category,
            from_subcategory=src,
            from_sub_subcategory="",
            to_category=category,
            to_subcategory=final_target,
            to_sub_subcategory="",
        ))
    db.commit()
    
    return {
        "status": "success",
        "message": f"Đã gộp {len(source_subcategories)} danh mục cấp 2 vào '{final_target}'",
        "products_updated": updated_count,
        "merged_categories": source_subcategories,
        "target_category": f"{category} > {final_target}"
    }


@router.post("/merge-level3")
def merge_level3_categories(
    category: str = Query(..., description="Tên danh mục cấp 1"),
    subcategory: str = Query(..., description="Tên danh mục cấp 2"),
    source_sub_subcategories: List[str] = Query(..., description="Danh sách danh mục cấp 3 nguồn cần gộp"),
    target_sub_subcategory: Optional[str] = Query(None, description="Tên danh mục cấp 3 đích (gộp vào đây)"),
    new_target_name: Optional[str] = Query(None, description="Tên danh mục cấp 3 mới (nếu muốn tạo mới)"),
    db: Session = Depends(get_db),
):
    """
    Gộp nhiều danh mục cấp 3 thành một.
    Ví dụ: Gộp "Giày lười da", "Giày lười vải" → "Giày lười nam"
    Tất cả sản phẩm sẽ được chuyển sang danh mục đích.
    """
    from app.models.product import Product
    
    if not source_sub_subcategories or len(source_sub_subcategories) == 0:
        raise HTTPException(status_code=400, detail="Danh sách danh mục nguồn không được rỗng")
    
    if not target_sub_subcategory and not new_target_name:
        raise HTTPException(status_code=400, detail="Cần chọn danh mục đích hoặc nhập tên danh mục mới")
    if target_sub_subcategory and new_target_name:
        raise HTTPException(status_code=400, detail="Chỉ được chọn danh mục đích hoặc tạo mới, không chọn cả hai")
    
    # Tìm tất cả sản phẩm thuộc các danh mục nguồn
    products = db.query(Product).filter(
        Product.category == category,
        Product.subcategory == subcategory,
        Product.sub_subcategory.in_(source_sub_subcategories)
    ).all()
    
    if not products:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy sản phẩm nào trong các danh mục cần gộp"
        )
    
    # Cập nhật tất cả sản phẩm sang danh mục đích
    updated_count = 0
    final_target = new_target_name or target_sub_subcategory
    for product in products:
        product.sub_subcategory = final_target
        updated_count += 1
    
    db.commit()

    for src in source_sub_subcategories:
        existing = db.query(CategoryFinalMapping).filter(
            CategoryFinalMapping.from_category == category,
            CategoryFinalMapping.from_subcategory == subcategory,
            CategoryFinalMapping.from_sub_subcategory == src
        ).first()
        if existing:
            db.delete(existing)
        db.add(CategoryFinalMapping(
            from_category=category,
            from_subcategory=subcategory,
            from_sub_subcategory=src,
            to_category=category,
            to_subcategory=subcategory,
            to_sub_subcategory=final_target,
        ))
    db.commit()
    
    return {
        "status": "success",
        "message": f"Đã gộp {len(source_sub_subcategories)} danh mục cấp 3 vào '{final_target}'",
        "products_updated": updated_count,
        "merged_categories": source_sub_subcategories,
        "target_category": f"{category} > {subcategory} > {final_target}"
    }
