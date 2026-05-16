# backend/app/api/endpoints/products.py - COMPLETE FIXED VERSION WITH BOTH ENDPOINTS
from datetime import datetime
import io

import pandas as pd
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Annotated, List, Literal, Optional

from app.db.session import get_db
from app import crud
from app.crud import product_search_cache as product_search_cache_crud
from app.models.search_mapping import SearchMapping, SearchMappingType
from app.utils.vietnamese import normalize_for_search_no_accent
from difflib import SequenceMatcher
import json
from app.schemas.product import (
    Product,
    ProductCreate,
    ProductUpdate,
    PurgeDeadMediaUrlBody,
    ListingParserIdsDbPresenceBody,
    ListingParserIdsDbPresenceResponse,
)
from app.crud.product_category_size_guide import enrich_product_payloads_with_category_size_guide
from app.models.admin import AdminUser
from app.core.security import require_module_permission
from app.core.config import settings
from app.crud import product_media_purge
from app.services.source_stock_checker import enqueue_product_view_stock_check_if_needed
from app.services.admin_source_stock_batch import (
    admin_collect_distinct_product_urls_from_db,
    admin_source_stock_queue_stats,
    run_admin_source_stock_scan_next_from_db,
)

router = APIRouter()


class AdminSourceStockBatchBody(BaseModel):
    url: str = Field(..., min_length=3)
    domain: Literal["1688", "hibox"] = "1688"


class AdminSourceStockScanNextDbBody(BaseModel):
    domain: Literal["1688", "hibox"] = "1688"
    active_only: bool = True
    cursor_after_product_id: int = Field(0, ge=0)


class AdminBulkDeleteProductsByDbIdBody(BaseModel):
    """Xóa sản theo khóa chính bảng `products.id` (dùng cho admin sau kiểm tra nguồn)."""

    db_ids: Annotated[List[int], Field(default_factory=list, max_length=300)]


def _serialize_products_for_api(db: Session, raw_products: List) -> List:
    paired: List = []
    for product in raw_products:
        try:
            d = Product.model_validate(product).model_dump()
            paired.append((product, d))
        except Exception:
            paired.append((None, product))
    dict_rows = [(o, d) for o, d in paired if o is not None and isinstance(d, dict)]
    if dict_rows:
        enrich_product_payloads_with_category_size_guide(db, [t[0] for t in dict_rows], [t[1] for t in dict_rows])
    return [entry[1] for entry in paired]


def _product_to_response(db: Session, db_product) -> Product:
    d = Product.model_validate(db_product).model_dump()
    enrich_product_payloads_with_category_size_guide(db, [db_product], [d])
    return Product(**d)


@router.get("/search", response_model=dict, include_in_schema=False)
@router.get("/search/", response_model=dict)
def search_products(
    response: Response,
    db: Session = Depends(get_db),
    q: Optional[str] = Query(None, description="Từ khóa tìm kiếm (tên, mã, danh mục, vật liệu, kiểu dáng, màu sắc, dịp, tính năng, size)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(48, ge=1, le=100),
    is_active: Optional[bool] = True,
    redirect: int = Query(0, ge=0, le=1, description="Nếu 1, trả về Redirect 302 khi match danh mục"),
):
    """
    Tìm kiếm sản phẩm theo: tên, mã sản phẩm, danh mục (cấp 1/2/3), vật liệu, kiểu dáng, màu sắc, dịp, tính năng, size.
    Từ khóa rời rạc, không phân biệt hoa thường, tự chuẩn tắc.
    """
    # ====== ZERO-DEAD-END FLOW ======
    try:
        response.headers["Cache-Control"] = "public, max-age=60"
        raw_q = (q or "").strip()
        norm_q = crud.product._normalize_search_key(raw_q)

        # Stage 1: Mapping Cache
        mapping = None
        if norm_q:
            mapping = db.query(SearchMapping).filter(SearchMapping.keyword_input == norm_q).first()
        if mapping:
            if mapping.type == SearchMappingType.category_redirect:
                if redirect == 1:
                    return RedirectResponse(url=mapping.keyword_target, status_code=302)
                return {"redirect_path": mapping.keyword_target, "status": "category_redirect"}
            else:
                # Override q with keyword_target
                raw_q = mapping.keyword_target
                norm_q = normalize_for_search_no_accent(raw_q)

        # Stage 2: Category Match (exact/fuzzy >= 90%)
        try:
            tree = crud.product.get_category_tree_from_products(db, is_active=is_active)
        except Exception:
            tree = []

        match_path = crud.product._match_category_path(norm_q, tree) if norm_q else None
        if match_path:
            # Save mapping for next time
            crud.product._save_search_mapping(db, norm_q, match_path["path"], SearchMappingType.category_redirect)
            if redirect == 1:
                return RedirectResponse(url=match_path["path"], status_code=302)
            return {"redirect_path": match_path["path"], "status": "category_redirect"}

        # Stage 3: Core Search
        result = crud.product.get_products(db, skip=skip, limit=limit, is_active=is_active, q=raw_q)
        total = int(result.get("total") or 0)
        if total > 0:
            # Serialize products
            if "products" in result:
                result["products"] = _serialize_products_for_api(db, result["products"])
            return result

        # Stage 4: AI Recovery & Normalize
        ai_corrected = None
        try:
            from app.services.search_query_corrector import correct_search_query_via_ai
            ai_corrected = crud.product._run_ai_call(correct_search_query_via_ai, raw_q, timeout_seconds=3)
        except Exception:
            ai_corrected = None

        if ai_corrected and ai_corrected.strip() and ai_corrected.strip() != raw_q:
            norm2 = crud.product._normalize_search_key(ai_corrected)
            # Try category match again
            match2 = crud.product._match_category_path(norm2, tree) if norm2 else None
            if match2:
                crud.product._save_search_mapping(db, norm_q, match2["path"], SearchMappingType.category_redirect)
                if redirect == 1:
                    return RedirectResponse(url=match2["path"], status_code=302)
                return {"redirect_path": match2["path"], "status": "category_redirect"}
            # Try core search again
            result2 = crud.product.get_products(db, skip=skip, limit=limit, is_active=is_active, q=ai_corrected)
            total2 = int(result2.get("total") or 0)
            if total2 > 10:
                crud.product._save_search_mapping(db, norm_q, ai_corrected, SearchMappingType.product_search)
            if total2 > 0:
                # Serialize products
                if "products" in result2:
                    result2["products"] = _serialize_products_for_api(db, result2["products"])
                return result2

        # Stage 5: AI Category Suggestions (Safety Net)
        try:
            from app.services.search_query_corrector import suggest_category_matches_via_ai
            categories_flat = crud.product._flatten_category_tree(tree)
            minimal = [{"id": f"{c['level']}|{c['slug']}", "name": c["name"]} for c in categories_flat]
            suggestions = crud.product._run_ai_call(
                suggest_category_matches_via_ai,
                raw_q,
                json.dumps(minimal, ensure_ascii=False),
                timeout_seconds=3
            ) or []
        except Exception:
            suggestions = []

        if not suggestions:
            # Fallback: fuzzy top 3
            scored = []
            for c in categories_flat:
                score = SequenceMatcher(None, norm_q, crud.product._normalize_search_key(c["name"])).ratio()
                scored.append((score, c))
            scored.sort(key=lambda x: x[0], reverse=True)
            top3 = [x[1] for x in scored[:3]]
            suggestions = [{"id": f"{c['level']}|{c['slug']}", "name": c["name"], "path": c["path"]} for c in top3]
        else:
            # Resolve to paths
            path_map = {}
            for c in categories_flat:
                key = f"{c['level']}|{c['slug']}"
                path_map[key] = c["path"]
            for s in suggestions:
                key = s.get("id")
                if key in path_map:
                    s["path"] = path_map[key]

        # Log stage 5 case
        crud.product._log_search(db, raw_q, 0, ai_processed=True)
        return {
            "status": "no_results",
            "message": "Không tìm thấy kết quả chính xác, nhưng có thể bạn quan tâm:",
            "suggested_categories": suggestions,
            "products": [],
            "total": 0,
        }
    except Exception as e:
        return {"error": str(e), "status": "serialization_error", "products": [], "total": 0}


def _read_products_list_impl(
    response: Response,
    db: Session,
    *,
    skip: int,
    limit: int,
    category: Optional[str],
    subcategory: Optional[str],
    sub_subcategory: Optional[str],
    shop_name: Optional[str],
    shop_id: Optional[str],
    style: Optional[str],
    shop_name_chinese: Optional[str],
    chinese_name: Optional[str],
    pro_lower_price: Optional[str],
    pro_high_price: Optional[str],
    min_price: Optional[float],
    max_price: Optional[float],
    is_active: Optional[bool],
    q: Optional[str],
    product_id: Optional[str],
    order_random: bool,
    sort: Optional[str],
    use_search_cache: bool,
    filter_size: Optional[str] = None,
    filter_color: Optional[str] = None,
    filter_style_tag: Optional[str] = None,
) -> dict:
    raw_q = (q or "").strip()
    pid = (product_id or "").strip()
    if order_random and not raw_q and not pid:
        response.headers["Cache-Control"] = "private, no-store"
    else:
        response.headers["Cache-Control"] = "public, max-age=60"
    cache_key = None
    if use_search_cache and raw_q and not pid:
        norm_q = crud.product._normalize_search_key(raw_q)
        cache_key = product_search_cache_crud.build_cache_key(
            norm_q=norm_q,
            skip=skip,
            limit=limit,
            category=category,
            subcategory=subcategory,
            sub_subcategory=sub_subcategory,
            shop_name=shop_name,
            shop_id=shop_id,
            style=style,
            shop_name_chinese=shop_name_chinese,
            chinese_name=chinese_name,
            pro_lower_price=pro_lower_price,
            pro_high_price=pro_high_price,
            min_price=min_price,
            max_price=max_price,
            is_active=is_active,
            sort=crud.product.normalize_product_list_sort(sort),
            filter_size=filter_size,
            filter_color=filter_color,
            filter_style_tag=filter_style_tag,
        )
        cached = product_search_cache_crud.get_cached_result(db, cache_key)
        if cached is not None:
            return cached

    result = crud.product.get_products(
        db,
        skip=skip,
        limit=limit,
        category=category,
        subcategory=subcategory,
        sub_subcategory=sub_subcategory,
        shop_name=shop_name,
        shop_id=shop_id,
        style=style,
        shop_name_chinese=shop_name_chinese,
        chinese_name=chinese_name,
        pro_lower_price=pro_lower_price,
        pro_high_price=pro_high_price,
        min_price=min_price,
        max_price=max_price,
        is_active=is_active,
        q=q,
        product_id=product_id,
        order_random=order_random,
        sort=sort,
        filter_size=filter_size,
        filter_color=filter_color,
        filter_style_tag=filter_style_tag,
    )

    if result and "products" in result:
        result["products"] = _serialize_products_for_api(db, result["products"])

    if (
        use_search_cache
        and cache_key
        and raw_q
        and not pid
        and not result.get("redirect_path")
        and not result.get("error")
    ):
        try:
            product_search_cache_crud.set_cached_result(db, cache_key, result)
        except Exception:
            pass

    return result


@router.get("", response_model=dict, include_in_schema=False)
@router.get("/", response_model=dict)
def read_products(
    response: Response,
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    sub_subcategory: Optional[str] = None,
    shop_name: Optional[str] = Query(None, description="Lọc theo shop_name"),
    shop_id: Optional[str] = Query(None, description="Lọc theo shop_id"),
    style: Optional[str] = Query(None, description="Lọc theo Style (cột Style / AF import)"),
    shop_name_chinese: Optional[str] = Query(None, description="Lọc theo Shop Trung Quốc (cột shop_name_chinese / AM)"),
    chinese_name: Optional[str] = Query(None, description="Lọc theo tên shop/chuỗi Trung Quốc (cột chinese_name)"),
    pro_lower_price: Optional[str] = Query(None, description="Lọc theo nhóm giá thấp hơn (chuỗi)"),
    pro_high_price: Optional[str] = Query(None, description="Lọc theo nhóm giá cao hơn (chuỗi)"),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    is_active: Optional[bool] = True,
    q: Optional[str] = Query(None, description="Tìm theo tên, mã, danh mục, vật liệu, kiểu dáng, màu sắc, dịp, tính năng, size (từ khóa rời rạc)"),
    product_id: Optional[str] = Query(None, description="Tìm theo ID sản phẩm (Excel) hoặc mã SKU (cột code)"),
    order_random: bool = Query(False, description="Trộn ngẫu nhiên (chỉ áp dụng khi không có q); phân trang theo random không ổn định giữa các lần tải"),
    sort: Optional[str] = Query(
        None,
        description="Sắp xếp: default | views_desc | newest | oldest (bị bỏ qua khi order_random=true)",
    ),
    size: Optional[str] = Query(None, description="Lọc size (khớp mảng JSON `sizes` của SP)"),
    color: Optional[str] = Query(
        None,
        description="Lọc màu (khớp tên SP, cột color, hoặc JSON colors — nên dùng giá trị từ category facets)",
    ),
    style_tag: Optional[str] = Query(None, description="Lọc kiểu phổ thông tự rút từ tên/thông tin sản phẩm"),
):
    """
    Get products with filtering and search (by name; the product_id filter matches Excel id or SKU code).
    """
    try:
        return _read_products_list_impl(
            response,
            db,
            skip=skip,
            limit=limit,
            category=category,
            subcategory=subcategory,
            sub_subcategory=sub_subcategory,
            shop_name=shop_name,
            shop_id=shop_id,
            style=style,
            shop_name_chinese=shop_name_chinese,
            chinese_name=chinese_name,
            pro_lower_price=pro_lower_price,
            pro_high_price=pro_high_price,
            min_price=min_price,
            max_price=max_price,
            is_active=is_active,
            q=q,
            product_id=product_id,
            order_random=order_random,
            sort=sort,
            use_search_cache=True,
            filter_size=size,
            filter_color=color,
            filter_style_tag=style_tag,
        )
    except Exception as e:
        return {"error": str(e), "status": "serialization_error"}


@router.get("/list/full", response_model=dict)
def read_products_full_list(
    response: Response,
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    sub_subcategory: Optional[str] = None,
    shop_name: Optional[str] = Query(None, description="Lọc theo shop_name"),
    shop_id: Optional[str] = Query(None, description="Lọc theo shop_id"),
    style: Optional[str] = Query(None, description="Lọc theo Style (cột Style / AF import)"),
    shop_name_chinese: Optional[str] = Query(None, description="Lọc theo Shop Trung Quốc (cột shop_name_chinese / AM)"),
    chinese_name: Optional[str] = Query(None, description="Lọc theo tên shop/chuỗi Trung Quốc (cột chinese_name)"),
    pro_lower_price: Optional[str] = Query(None, description="Lọc theo nhóm giá thấp hơn (chuỗi)"),
    pro_high_price: Optional[str] = Query(None, description="Lọc theo nhóm giá cao hơn (chuỗi)"),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    is_active: Optional[bool] = True,
    q: Optional[str] = Query(None, description="Tìm theo tên, mã, danh mục, vật liệu, kiểu dáng, màu sắc, dịp, tính năng, size (từ khóa rời rạc)"),
    product_id: Optional[str] = Query(None, description="Tìm theo ID sản phẩm (Excel) hoặc mã SKU (cột code)"),
    order_random: bool = Query(False, description="Trộn ngẫu nhiên (chỉ áp dụng khi không có q); phân trang theo random không ổn định giữa các lần tải"),
    sort: Optional[str] = Query(
        None,
        description="Sắp xếp: default | views_desc | newest | oldest (bị bỏ qua khi order_random=true)",
    ),
    size: Optional[str] = Query(None, description="Lọc size (khớp mảng JSON `sizes` của SP)"),
    color: Optional[str] = Query(
        None,
        description="Lọc màu (khớp tên SP, cột color, hoặc JSON colors — nên dùng giá trị từ category facets)",
    ),
    style_tag: Optional[str] = Query(None, description="Lọc kiểu phổ thông tự rút từ tên/thông tin sản phẩm"),
):
    """
    Danh sách sản phẩm **đầy đủ trường** (khớp schema `Product`: mọi cột bảng `products`, gồm `category_id`,
    `raw_category`, `raw_subcategory`, `raw_sub_subcategory`, `product_info`, SEO, bản địa hóa ảnh, v.v.).
    Bộ lọc và phân trang giống `GET /api/v1/products/`. Không ghi/đọc cache tìm kiếm theo `q` để luôn có payload đầy đủ theo phiên bản schema hiện tại.
    """
    try:
        return _read_products_list_impl(
            response,
            db,
            skip=skip,
            limit=limit,
            category=category,
            subcategory=subcategory,
            sub_subcategory=sub_subcategory,
            shop_name=shop_name,
            shop_id=shop_id,
            style=style,
            shop_name_chinese=shop_name_chinese,
            chinese_name=chinese_name,
            pro_lower_price=pro_lower_price,
            pro_high_price=pro_high_price,
            min_price=min_price,
            max_price=max_price,
            is_active=is_active,
            q=q,
            product_id=product_id,
            order_random=order_random,
            sort=sort,
            use_search_cache=False,
            filter_size=size,
            filter_color=color,
            filter_style_tag=style_tag,
        )
    except Exception as e:
        return {"error": str(e), "status": "serialization_error"}


@router.get("/category-facets", response_model=dict)
def read_category_product_facets(
    response: Response,
    db: Session = Depends(get_db),
    category: Optional[str] = Query(None, description="Danh mục cấp 1 (tên hiển thị)"),
    subcategory: Optional[str] = Query(None),
    sub_subcategory: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    size: Optional[str] = Query(None),
    color: Optional[str] = Query(None),
    style_tag: Optional[str] = Query(None),
):
    """
    Size / màu / khoảng giá duy nhất trong phạm vi danh mục (SP `is_active=true`),
    dùng cho bộ lọc trang `/danh-muc/...`.
    """
    response.headers["Cache-Control"] = "public, max-age=120"
    try:
        facets = crud.product.get_category_product_facets(
            db,
            category=category,
            subcategory=subcategory,
            sub_subcategory=sub_subcategory,
            min_price=min_price,
            max_price=max_price,
            filter_size=size,
            filter_color=color,
            filter_style_tag=style_tag,
        )
        return {"status": "ok", **facets}
    except Exception as e:
        return {"status": "error", "error": str(e), "sizes": [], "colors": [], "style_tags": [], "price_min": None, "price_max": None}


@router.get("/search-facets", response_model=dict)
def read_search_product_facets(
    response: Response,
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=1, description="Từ khóa tìm (cùng logic GET /products?q=)"),
    category: Optional[str] = Query(None),
    subcategory: Optional[str] = Query(None),
    sub_subcategory: Optional[str] = Query(None),
    shop_name: Optional[str] = Query(None),
    shop_id: Optional[str] = Query(None),
    style: Optional[str] = Query(None),
    shop_name_chinese: Optional[str] = Query(None),
    chinese_name: Optional[str] = Query(None),
    pro_lower_price: Optional[str] = Query(None),
    pro_high_price: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    size: Optional[str] = Query(None),
    color: Optional[str] = Query(None),
    style_tag: Optional[str] = Query(None),
    is_active: Optional[bool] = True,
):
    """
    Size / màu / khoảng giá trong tập kết quả tìm theo `q` (trước lọc size/màu/giá trên UI).
    Dùng cho trang chủ `/?q=...`.
    """
    response.headers["Cache-Control"] = "public, max-age=90"
    try:
        facets = crud.product.get_search_product_facets(
            db,
            q,
            category=category,
            subcategory=subcategory,
            sub_subcategory=sub_subcategory,
            shop_name=shop_name,
            shop_id=shop_id,
            style=style,
            shop_name_chinese=shop_name_chinese,
            chinese_name=chinese_name,
            pro_lower_price=pro_lower_price,
            pro_high_price=pro_high_price,
            min_price=min_price,
            max_price=max_price,
            filter_size=size,
            filter_color=color,
            filter_style_tag=style_tag,
            is_active=is_active,
        )
        return {"status": "ok", **facets}
    except Exception as e:
        return {"status": "error", "error": str(e), "sizes": [], "colors": [], "style_tags": [], "price_min": None, "price_max": None}


@router.get("/listing-facets", response_model=dict)
def read_product_listing_facets(
    response: Response,
    db: Session = Depends(get_db),
    q: Optional[str] = Query(None, description="Nếu có — cùng logic GET /products?q= và search-facets"),
    category: Optional[str] = Query(None),
    subcategory: Optional[str] = Query(None),
    sub_subcategory: Optional[str] = Query(None),
    shop_name: Optional[str] = Query(None),
    shop_id: Optional[str] = Query(None),
    style: Optional[str] = Query(None),
    shop_name_chinese: Optional[str] = Query(None),
    chinese_name: Optional[str] = Query(None),
    pro_lower_price: Optional[str] = Query(None),
    pro_high_price: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    size: Optional[str] = Query(None),
    color: Optional[str] = Query(None),
    style_tag: Optional[str] = Query(None),
    is_active: Optional[bool] = True,
):
    """
    Facets cho listing `/` không bắt buộc `q` — style, danh mục, shop… (không áp size/màu/min/max trong SQL).
    """
    response.headers["Cache-Control"] = "public, max-age=90"
    try:
        facets = crud.product.get_product_listing_facets(
            db,
            q=q,
            category=category,
            subcategory=subcategory,
            sub_subcategory=sub_subcategory,
            shop_name=shop_name,
            shop_id=shop_id,
            style=style,
            shop_name_chinese=shop_name_chinese,
            chinese_name=chinese_name,
            pro_lower_price=pro_lower_price,
            pro_high_price=pro_high_price,
            min_price=min_price,
            max_price=max_price,
            filter_size=size,
            filter_color=color,
            filter_style_tag=style_tag,
            is_active=is_active,
        )
        return {"status": "ok", **facets}
    except Exception as e:
        return {"status": "error", "error": str(e), "sizes": [], "colors": [], "style_tags": [], "price_min": None, "price_max": None}


@router.get("/export-unused-internal-skus/available-count", response_model=dict)
def get_unused_internal_sku_available_count(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Số lượng mã SKU còn có thể export (và tổng dải). Reserve sau mỗi lần tải file hết hiệu lực sau 7 ngày."""
    from app.services.product_internal_sku import count_available_internal_skus_for_export

    return count_available_internal_skus_for_export(db)


@router.post("/export-unused-internal-skus")
def export_unused_internal_skus(
    count: int = Query(100, ge=1, le=10_000, description="Số mã SKU cần lấy (A0001–Z9999, không gồm X0000)"),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """
    Xuất Excel một cột `sku`: các mã chưa gán SP và không đang reserved bởi lần tải file trong 7 ngày qua.
    Mã được ghi vào `internal_sku_exports`; sau 7 ngày bản ghi cũ được xóa — có thể xuất trùng mã và import không buộc đối chiếu file đó.
    """
    from app.services.product_internal_sku import allocate_unused_internal_skus_for_export

    try:
        codes = allocate_unused_internal_skus_for_export(db, count)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    df = pd.DataFrame({"sku": codes})
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="sku")
    buf.seek(0)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"internal_skus_unused_{count}_{stamp}.xlsx"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/listing-parser-db-presence",
    response_model=ListingParserIdsDbPresenceResponse,
    include_in_schema=False,
)
def post_listing_parser_ids_db_presence(
    body: ListingParserIdsDbPresenceBody,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """
    Cho trang admin parse HTML listing:

    - Luôn đối chiếu `products` (trùng `product_id` hoặc prefix `{id}a188…`).
    - ``products_active_only``: chỉ SP đang ``is_active`` (đang hiển thị trên shop).
    - ``include_done_drafts``: gộp id đã có nháp import ``done`` + ``product_data`` (dùng để ẩn dòng lưới parse:
      «chưa có trên shop và chưa có nháp»). Modal «đăng web sau crawl» nên gửi ``include_done_drafts=false``
      để «đã có trong shop» chỉ khi đã có trong ``products``.
    """
    raw_ids = body.ids or []
    if len(raw_ids) > 2000:
        raise HTTPException(status_code=400, detail="Tối đa 2000 id mỗi lần gọi.")

    existing_products = crud.product.listing_parser_ids_existing_in_products(
        db, raw_ids, active_only=body.products_active_only
    )
    merged = set(existing_products)
    if body.include_done_drafts:
        merged |= crud.product.listing_parser_ids_with_done_drafts(db, raw_ids)
    return ListingParserIdsDbPresenceResponse(existing_normalized=sorted(merged))


@router.post("", response_model=Product, include_in_schema=False)
@router.post("/", response_model=Product)
def create_product(
    product: ProductCreate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """
    Create new product
    """
    pid = (product.product_id or "").strip()
    if pid:
        hit = crud.product.find_conflicting_product_id_for_same_listing_source(db, pid)
        if hit:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Mã nguồn trong id (phần trước «a188») đã tồn tại — sản phẩm {hit}. "
                    "Không tạo trùng offer/item 1688 hoặc Taobao."
                ),
            )
    created = crud.product.create_product(db=db, product=product)
    return _product_to_response(db, created)

@router.get("/{product_id}", response_model=Product)
def read_product(
    product_id: str,
    db: Session = Depends(get_db)
):
    """
    Get product by PRODUCT_ID (string from Excel column A)
    """
    db_product = crud.product.get_product_by_product_id(db, product_id=product_id)
    if db_product is None:
        db_product = crud.product.get_product_by_slug(db, slug=product_id)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_response(db, db_product)


def update_product(
    product_id: str,
    product_update: ProductUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """
    Update product (product_id = Excel column A / product_id string)
    """
    existing = crud.product.get_product_by_product_id(db, product_id=product_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Product not found")
    db_product = crud.product.update_product(db, product_id=existing.id, product_update=product_update)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_response(db, db_product)

@router.delete("/{product_id}", response_model=Product)
def delete_product(
    product_id: str,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """
    Delete product (product_id = Excel column A / product_id string)
    """
    existing = crud.product.get_product_by_product_id(db, product_id=product_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Product not found")
    db_product = crud.product.delete_product(db, product_id=existing.id)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_response(db, db_product)

@router.get("/by-slug/{slug}", response_model=Product)
def read_product_by_slug(
    slug: str,
    db: Session = Depends(get_db)
):
    """
    Get product by slug (path parameter version)
    - URL: /api/v1/products/by-slug/{slug}
    """
    db_product = crud.product.get_product_by_slug(db, slug=slug)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_response(db, db_product)

@router.get("/by-slug/", response_model=Product)
def read_product_by_slug_query(
    slug: str = Query(..., description="Product slug"),
    db: Session = Depends(get_db)
):
    """
    Get product by slug (query parameter version)
    - URL: /api/v1/products/by-slug?slug={slug}
    - Frontend hiện đang gọi theo cách này
    """
    db_product = crud.product.get_product_by_slug(db, slug=slug)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_response(db, db_product)

@router.get("/by-code/{product_code}", response_model=Product)
def read_product_by_code(
    product_code: str,
    db: Session = Depends(get_db)
):
    """
    Get product by product_id (Excel column A)
    """
    db_product = crud.product.get_product_by_product_id(db, product_id=product_code)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_response(db, db_product)

@router.get("/by-id/{id}", response_model=Product)
def read_product_by_id(
    id: int,
    db: Session = Depends(get_db)
):
    """
    Get product by database ID (integer primary key)
    """
    db_product = crud.product.get_product(db, product_id=id)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_response(db, db_product)


@router.post("/by-id/{id}/source-stock-check/enqueue", response_model=dict)
def enqueue_product_source_stock_check(
    id: int,
    db: Session = Depends(get_db),
):
    """
    Kích kiểm tra tồn kho nguồn cho PDP. Response trả ngay; worker nền xử lý theo rate limit.
    """
    db_product = crud.product.get_product(db, product_id=id)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    queued = enqueue_product_view_stock_check_if_needed(db_product)
    try:
        db.refresh(db_product)
    except Exception:
        pass
    return {
        "queued": queued,
        "source_stock_status": getattr(db_product, "source_stock_status", None),
        "source_stock_checked_at": getattr(db_product, "source_stock_checked_at", None),
        "source_stock_next_check_at": getattr(db_product, "source_stock_next_check_at", None),
    }


@router.post("/admin/source-stock-batch/run", response_model=dict, include_in_schema=False)
def admin_source_stock_batch_run(
    body: AdminSourceStockBatchBody,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Admin: kiểm tra một URL nguồn (1688 cookie / hoặc Hibox scrape). Lỗi hoặc hết → có thể set available=0."""
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Thiếu URL.")

    try:
        from app.services.admin_source_stock_batch import run_admin_source_url_scan

        out = run_admin_source_url_scan(db, url=url, domain=str(body.domain))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("detail") or "Yêu cầu không hợp lệ.")
    return out


@router.post("/admin/source-stock-batch/run-next-from-db", response_model=dict, include_in_schema=False)
def admin_source_stock_batch_run_next_from_db(
    body: AdminSourceStockScanNextDbBody,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Lấy một sản phẩm kế trong DB có link_default (Excel product_url) và chạy một lần kiểm tra nguồn."""
    try:
        out = run_admin_source_stock_scan_next_from_db(
            db,
            domain=str(body.domain),
            active_only=bool(body.active_only),
            cursor_after_product_id=int(body.cursor_after_product_id),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("detail") or "Yêu cầu không hợp lệ.")
    return out


@router.post("/admin/source-stock-batch/delete-by-db-ids", response_model=dict, include_in_schema=False)
def admin_source_stock_delete_products_by_db_ids(
    body: AdminBulkDeleteProductsByDbIdBody,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """
    Xóa vĩnh viễn các sản trong CSDL (`products.id`), kèm dọn Bunny như DELETE sản đơn lẻ.
    Dùng từ màn Kiểm tra nguồn hàng: danh sách hết/khớp SP trên phiên chỉ là tạm; thao tác này mới gỡ SP khỏi shop.
    """
    incoming = getattr(body, "db_ids", None) or []
    seen: set[int] = set()
    ordered: List[int] = []
    for x in incoming:
        try:
            pk = int(x)
        except (TypeError, ValueError):
            continue
        if pk <= 0 or pk in seen:
            continue
        seen.add(pk)
        ordered.append(pk)

    if not ordered:
        raise HTTPException(
            status_code=400,
            detail="Không có id DB hợp lệ (cần số nguyên dương, tối đa 300 mỗi lần).",
        )

    deleted_db_ids: List[int] = []
    not_found_db_ids: List[int] = []
    for pk in ordered:
        row = crud.product.get_product(db, product_id=pk)
        if row is None:
            not_found_db_ids.append(pk)
            continue
        crud.product.delete_product(db, product_id=pk)
        deleted_db_ids.append(pk)

    return {
        "ok": True,
        "deleted_count": len(deleted_db_ids),
        "deleted_db_ids": deleted_db_ids,
        "not_found_db_ids": not_found_db_ids,
    }


@router.get("/admin/source-stock-batch/queue-stats", response_model=dict, include_in_schema=False)
def admin_source_stock_batch_queue_stats(
    domain: Literal["1688", "hibox"] = Query(
        "1688",
        description="Cùng nhánh lọc như run-next-from-db / product-urls",
    ),
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Đếm SP trong phạm vi link + miền và tách TTL (sẵn sàng vòng / chờ cooldown)."""
    return admin_source_stock_queue_stats(db, domain=str(domain), active_only=bool(active_only))


@router.get("/admin/source-stock-batch/product-urls", response_model=dict, include_in_schema=False)
def admin_source_stock_batch_product_urls(
    domain: Literal["1688", "hibox"] = Query(
        "1688",
        description="Lọc link phù hợp luồng kiểm tra (Excel product_url → DB link_default)",
    ),
    limit: int = Query(6000, ge=1, le=15000),
    active_only: bool = Query(True, description="Chỉ sản phẩm is_active"),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    domain_l = (domain or "1688").strip().lower()
    return admin_collect_distinct_product_urls_from_db(db, domain=domain_l, limit=int(limit), active_only=bool(active_only))

@router.post("/by-id/{id}/purge-dead-media-url", response_model=dict, include_in_schema=False)
def purge_dead_media_url_by_db_id(
    id: int,
    body: PurgeDeadMediaUrlBody,
    db: Session = Depends(get_db),
    x_broken_media_purge_key: Optional[str] = Header(None, alias="X-Broken-Media-Purge-Key"),
):
    """
    Xóa URL ảnh khỏi các cột media của sản phẩm **chỉ khi** HEAD/GET xác nhận 404/410 và URL thuộc bản ghi này.
    Bảo vệ bằng `BROKEN_MEDIA_PURGE_SECRET` (header X-Broken-Media-Purge-Key) — gọi từ Next server, không public.
    """
    secret = (getattr(settings, "BROKEN_MEDIA_PURGE_SECRET", None) or "").strip()
    if not secret or (x_broken_media_purge_key or "").strip() != secret:
        raise HTTPException(status_code=404, detail="Not found")
    p = crud.product.get_product(db, product_id=id)
    if p is None:
        raise HTTPException(status_code=404, detail="Product not found")
    url = (body.url or "").strip()
    out = product_media_purge.run_purge_dead_media_if_eligible(db, p, url)
    if not out.get("ok"):
        if out.get("reason") == "url_not_on_product":
            raise HTTPException(status_code=400, detail="URL does not belong to this product")
        raise HTTPException(status_code=400, detail="URL is still reachable or could not verify (not 404)")
    return out

