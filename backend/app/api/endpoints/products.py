# backend/app/api/endpoints/products.py - COMPLETE FIXED VERSION WITH BOTH ENDPOINTS
from datetime import datetime
import io
import logging
import random
from urllib.parse import unquote

import pandas as pd
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Annotated, List, Literal, Optional

from app.db.session import get_db
from app.db.retry import TransientDbError
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
from app.core.security import require_module_permission, get_current_user_optional
from app.models.user import User
from app.core.config import settings
from app.crud import product_media_purge
from app.services.source_stock_checker import (
    admin_preview_source_stock_by_url,
    enqueue_product_view_stock_check_if_needed,
    get_source_stock_worker_admin_snapshot,
    set_source_stock_worker_paused,
)
from app.services.admin_source_stock_batch import (
    admin_collect_distinct_product_urls_from_db,
    admin_clear_false_source_oos_flag,
    admin_force_worker_source_stock_recheck,
    admin_reset_source_stock_pdp_cycle,
    admin_source_stock_activity_report,
    admin_source_stock_queue_stats,
    run_admin_source_stock_scan_next_from_db,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_DB_UNAVAILABLE_DETAIL = "Cơ sở dữ liệu tạm thời không phản hồi — vui lòng thử lại sau vài giây"


def _apply_storefront_image_gate(db: Session, row):
    """SP không có ảnh storefront → gỡ khỏi catalog (404 cho khách)."""
    from app.services.product_image_visibility import (
        deactivate_product_without_storefront_image,
        product_has_storefront_image,
    )

    if row is None:
        return None
    if not product_has_storefront_image(row):
        deactivate_product_without_storefront_image(db, row)
        return None
    return row


def _lookup_product_by_slug(db: Session, slug: str):
    try:
        row = crud.product.get_product_by_slug(db, slug=slug)
        return _apply_storefront_image_gate(db, row)
    except TransientDbError as exc:
        raise HTTPException(
            status_code=503,
            detail=_DB_UNAVAILABLE_DETAIL,
            headers={"Retry-After": "3"},
        ) from exc


def _resolve_storefront_product(db: Session, key: str):
    """Tra SP theo product_id / slug / code — cùng luật ẩn ảnh như by-slug."""
    try:
        pid = _normalize_excel_product_id(key)
        row = crud.product.resolve_product_by_sku(db, sku=pid)
        return _apply_storefront_image_gate(db, row)
    except TransientDbError as exc:
        raise HTTPException(
            status_code=503,
            detail=_DB_UNAVAILABLE_DETAIL,
            headers={"Retry-After": "3"},
        ) from exc


class AdminSourceStockBatchBody(BaseModel):
    url: str = Field(..., min_length=3)
    domain: Literal["hibox", "cssbuy", "vipomall"] = "cssbuy"
    dual_alternate_fallback: bool = Field(
        False,
        description="Sen kẽ thứ tự Hibox/CSSBuy theo alternate_sequence_index, fallback khi một nền không đọc được.",
    )
    alternate_sequence_index: int = Field(0, ge=0, le=900_000_000)


class AdminSourceStockScanNextDbBody(BaseModel):
    domain: Literal["hibox", "cssbuy", "vipomall"] = "cssbuy"
    active_only: bool = True
    cursor_after_product_id: int = Field(0, ge=0)
    sticky_seed_product_id: int = Field(
        0,
        ge=0,
        description="products.id — ưu tiên kiểm tra lại đúng SP (retry sau lỗi tạm captcha/chặn). 0 = tắt.",
    )
    skip_sticky_after_failure: bool = Field(
        False,
        description="Nếu sticky SP vẫn lỗi tạm sau khi retry, đóng dấu TTL để bỏ qua vòng này và chạy SP kế.",
    )
    dual_alternate_fallback: bool = Field(
        False,
        description="Sen kẽ + fallback hai nền (Hibox scrape / CSSBuy API) trong một lần kiểm tra.",
    )
    alternate_sequence_index: int = Field(0, ge=0, le=900_000_000)


class AdminBulkDeleteProductsByDbIdBody(BaseModel):
    """Xóa sản theo khóa chính bảng `products.id` (dùng cho admin sau kiểm tra nguồn)."""

    db_ids: Annotated[List[int], Field(default_factory=list, max_length=300)]


class AdminSingleProductDbIdBody(BaseModel):
    db_id: int = Field(..., gt=0, description="Khóa chính products.id")


class AdminSourceStockWorkerPauseBody(BaseModel):
    paused: bool


class AdminSourceStockPreviewUrlBody(BaseModel):
    """Admin thử PDP theo một URL — không ghi DB (ưu tiên CSSBuy; Hibox chỉ khi CSS blocked/error)."""

    url: str = Field(..., min_length=8, max_length=8192)


class AdminSourceStockResetPdpBody(BaseModel):
    """Reset kết quả kiểm tra PDP (source_stock_*) và xóa queue RAM của một process."""

    domain: Literal["hibox", "cssbuy", "vipomall"] = Field(
        "cssbuy",
        description="Giống queue-stats — lọc phạm vi sản có link có thể quy đổi như nhập Excel.",
    )
    active_only: bool = Field(True)
    confirm: bool = Field(
        False,
        description="Bắt buộc gửi true sau khi admin đọc đủ cảnh báo — ngăn bấm nhầm.",
    )


# Trường nặng không cần trên lưới admin (mô tả/SEO) — giảm payload & thời gian serialize.
_ADMIN_LIST_DUMP_EXCLUDE = frozenset(
    {
        "description",
        "product_info",
        "meta_title",
        "meta_description",
        "meta_keywords",
    }
)


def _should_skip_total_storefront_list(
    *,
    admin_list: bool,
    skip_total: bool,
    raw_q: str,
    pid: str,
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
    filter_size: Optional[str],
    filter_color: Optional[str],
    filter_style_tag: Optional[str],
    order_random: bool,
    warehouse_clearance_only: bool,
) -> bool:
    """Storefront danh sách thuần (không lọc/tìm): bỏ COUNT(*) ~30k SP — giảm giữ connection DB."""
    if admin_list or skip_total or raw_q or pid or order_random or warehouse_clearance_only:
        return False
    text_filters = (
        category,
        subcategory,
        sub_subcategory,
        shop_name,
        shop_id,
        style,
        shop_name_chinese,
        chinese_name,
        pro_lower_price,
        pro_high_price,
        filter_size,
        filter_color,
        filter_style_tag,
    )
    if any(x is not None and str(x).strip() for x in text_filters):
        return False
    if min_price is not None or max_price is not None:
        return False
    return True


def _serialize_products_for_api(
    db: Session,
    raw_products: List,
    user: Optional[User] = None,
    *,
    include_warehouse_clearance: bool = False,
    admin_list: bool = False,
) -> List:
    paired: List = []
    if admin_list:
        for product in raw_products:
            try:
                d = Product.model_validate(product).model_dump(
                    exclude=_ADMIN_LIST_DUMP_EXCLUDE,
                )
                paired.append((product, d))
            except Exception:
                paired.append((None, product))
        return [entry[1] for entry in paired]

    from app.services import sale_calendar as sale_calendar_svc

    sale_state = sale_calendar_svc.resolve_sale_calendar_state(db, user=user)
    for product in raw_products:
        try:
            d = Product.model_validate(product).model_dump()
            # Dòng kho thanh lý: giá sale kho riêng — không chồng lịch Sale site (6/6, …).
            if not getattr(product, "is_warehouse_clearance", False):
                sale_calendar_svc.enrich_product_payload_with_site_sale(d, sale_state)
            paired.append((product, d))
        except Exception:
            paired.append((None, product))
    dict_rows = [(o, d) for o, d in paired if o is not None and isinstance(d, dict)]
    if dict_rows:
        enrich_product_payloads_with_category_size_guide(db, [t[0] for t in dict_rows], [t[1] for t in dict_rows])
        if include_warehouse_clearance:
            from app.services.warehouse_clearance import enrich_listing_product_payloads

            enrich_listing_product_payloads(db, dict_rows)
    return [entry[1] for entry in paired]


def _product_to_response(
    db: Session,
    db_product,
    user: Optional[User] = None,
    *,
    attach_group_listing: bool = False,
) -> Product:
    from app.services import sale_calendar as sale_calendar_svc
    from app.services import warehouse_clearance as wh_clearance_svc
    from app.utils.public_product_url import slug_path_segment_from_input

    row = db_product
    standalone_wh = False
    if getattr(db_product, "is_warehouse_clearance", False):
        parent = wh_clearance_svc.find_parent_product_by_base_sku(
            db, getattr(db_product, "base_sku", None) or db_product.code or ""
        )
        if parent is not None:
            row = parent
        else:
            standalone_wh = True

    d = Product.model_validate(row).model_dump()
    if standalone_wh:
        wh_clearance_svc.enrich_standalone_warehouse_product(db, d, db_product)
        d["slug"] = crud.product.generate_consistent_slug(
            d.get("name") or getattr(db_product, "name", "") or "",
            getattr(db_product, "product_id", None) or "",
        )
    else:
        sale_state = sale_calendar_svc.resolve_sale_calendar_state(db, user=user)
        sale_calendar_svc.enrich_product_payload_with_site_sale(d, sale_state)
        wh_clearance_svc.enrich_parent_with_warehouse_clearance(db, d, row)
    enrich_product_payloads_with_category_size_guide(db, [row], [d])

    wh_variants = d.get("warehouse_variants") or []
    source_oos = bool(d.get("source_oos"))
    has_wh_stock = len(wh_variants) > 0
    if attach_group_listing and int(d.get("available") or 0) <= 0:
        if not (source_oos and has_wh_stock):
            if not has_wh_stock:
                src = slug_path_segment_from_input(getattr(row, "slug", None)) or (
                    (getattr(row, "slug", None) or "").strip()
                )
                d["group_listing_path"] = crud.product.resolve_product_group_listing_path(
                    db,
                    source_slug=src,
                    product=row,
                    product_id=getattr(row, "product_id", None),
                )
    try:
        return Product(**d)
    except Exception as exc:
        logger.exception(
            "serialize product failed id=%s product_id=%s",
            getattr(row, "id", None),
            getattr(row, "product_id", None),
        )
        raise HTTPException(status_code=404, detail="Product not found") from exc


def _shuffle_cached_products_response(result: dict) -> dict:
    """
    Trả bản copy response với products đã shuffle để sort=random
    vẫn đổi lưới mỗi lần đọc từ cache.
    """
    rows = result.get("products")
    if not isinstance(rows, list) or len(rows) <= 1:
        return result
    cloned = dict(result)
    shuffled = list(rows)
    random.shuffle(shuffled)
    cloned["products"] = shuffled
    return cloned


@router.get("/search", response_model=dict, include_in_schema=False)
@router.get("/search/", response_model=dict)
def search_products(
    response: Response,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
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
        # Dùng cây menu đã cache — tránh DISTINCT+prune toàn bảng mỗi lần search (treo pool/CPU).
        try:
            tree = crud.product.get_cached_menu_category_tree(
                is_active if is_active is not None else True
            )
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
                result["products"] = _serialize_products_for_api(
                    db,
                    result["products"],
                    user=current_user,
                    include_warehouse_clearance=True,
                )
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
                    result2["products"] = _serialize_products_for_api(
                        db,
                        result2["products"],
                        user=current_user,
                        include_warehouse_clearance=True,
                    )
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
    search_refresh: Optional[str] = None,
    skip_total: bool = False,
    user: Optional[User] = None,
    include_warehouse_clearance: bool = False,
    warehouse_clearance_only: bool = False,
    admin_list: bool = False,
) -> dict:
    from app.services import sale_calendar as sale_calendar_svc

    if not admin_list and is_active is None:
        is_active = True

    raw_q = (q or "").strip()
    pid = (product_id or "").strip()
    if admin_list and not skip_total and not raw_q and not pid:
        skip_total = True
    if _should_skip_total_storefront_list(
        admin_list=admin_list,
        skip_total=skip_total,
        raw_q=raw_q,
        pid=pid,
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
        filter_size=filter_size,
        filter_color=filter_color,
        filter_style_tag=filter_style_tag,
        order_random=order_random,
        warehouse_clearance_only=warehouse_clearance_only,
    ):
        skip_total = True
    if order_random and not raw_q and not pid:
        response.headers["Cache-Control"] = "private, no-store"
    elif raw_q and crud.product.normalize_product_list_sort(sort) == "random":
        response.headers["Cache-Control"] = "private, no-store"
    else:
        # Admin / công cụ nội bộ cần dữ liệu mới sau PUT; public cache gây hiển thị cũ ~60s.
        response.headers["Cache-Control"] = "private, no-cache, must-revalidate"
    cache_key = None
    list_query_payload = None
    norm_q = None
    skip_search_cache = admin_list or (
        user is not None and sale_calendar_svc.is_site_sale_test_enabled(db, user)
    )
    sort_norm = crud.product.normalize_product_list_sort(sort)
    search_cache_active = use_search_cache and raw_q and not pid and not skip_search_cache
    fetch_skip = skip
    fetch_limit = limit
    paginate_from_list_cache = False

    if search_cache_active:
        norm_q = crud.product._normalize_search_key(raw_q)
        list_query_payload = product_search_cache_crud.build_keyword_list_cache_payload(
            norm_q=norm_q,
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
            sort=sort_norm,
            search_refresh=search_refresh,
            filter_size=filter_size,
            filter_color=filter_color,
            filter_style_tag=filter_style_tag,
        )
        cache_key = product_search_cache_crud.build_keyword_list_cache_key(
            norm_q=norm_q,
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
            sort=sort_norm,
            search_refresh=search_refresh,
            filter_size=filter_size,
            filter_color=filter_color,
            filter_style_tag=filter_style_tag,
        )
        cached_full = product_search_cache_crud.get_cached_result(db, cache_key)
        if cached_full is not None and product_search_cache_crud.cached_list_covers_page(
            cached_full, skip, limit
        ):
            shuffle_page = sort_norm == "random"
            return product_search_cache_crud.paginate_cached_search_response(
                cached_full, skip, limit, shuffle_random=shuffle_page
            )

        beyond_list_cap = skip + limit > product_search_cache_crud.SEARCH_LIST_CACHE_MAX_PRODUCTS
        if not beyond_list_cap:
            fetch_skip = 0
            fetch_limit = product_search_cache_crud.list_cache_fetch_limit(skip, limit)
            paginate_from_list_cache = True

    result = crud.product.get_products(
        db,
        skip=fetch_skip,
        limit=fetch_limit,
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
        search_refresh=search_refresh,
        skip_total=skip_total,
        include_warehouse_products=admin_list,
        warehouse_clearance_only=warehouse_clearance_only,
        admin_list_query=admin_list,
    )

    if result and "products" in result:
        result["products"] = _serialize_products_for_api(
            db,
            result["products"],
            user=user,
            include_warehouse_clearance=include_warehouse_clearance,
            admin_list=admin_list,
        )

    if (
        search_cache_active
        and cache_key
        and list_query_payload
        and paginate_from_list_cache
        and not result.get("redirect_path")
        and not result.get("error")
    ):
        try:
            product_search_cache_crud.set_cached_result(
                db,
                cache_key,
                result,
                norm_q=norm_q,
                query_payload=list_query_payload,
            )
        except Exception:
            pass

    if paginate_from_list_cache and not result.get("redirect_path") and not result.get("error"):
        shuffle_page = sort_norm == "random"
        return product_search_cache_crud.paginate_cached_search_response(
            result, skip, limit, shuffle_random=shuffle_page
        )

    return result


@router.get("", response_model=dict, include_in_schema=False)
@router.get("/", response_model=dict)
def read_products(
    response: Response,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
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
    is_active: Optional[bool] = Query(
        None,
        description="Lọc hiển thị shop. Mặc định storefront=true; admin_list=true thì mặc định null (mọi trạng thái).",
    ),
    q: Optional[str] = Query(None, description="Tìm theo tên, mã, danh mục, vật liệu, kiểu dáng, màu sắc, dịp, tính năng, size (từ khóa rời rạc)"),
    product_id: Optional[str] = Query(
        None,
        description="Tìm theo ID SP (cột A / prefix A|T+số, có hoặc không hậu tố a188SKU), mã SKU (code) hoặc khớp một phần",
    ),
    order_random: bool = Query(False, description="Trộn ngẫu nhiên (chỉ áp dụng khi không có q); phân trang theo random không ổn định giữa các lần tải"),
    sort: Optional[str] = Query(
        None,
        description="Sắp xếp: id_desc | newest | oldest | views_desc | available_desc | available_asc | id_asc (bị bỏ qua khi order_random=true)",
    ),
    size: Optional[str] = Query(None, description="Lọc size (khớp mảng JSON `sizes` của SP)"),
    color: Optional[str] = Query(
        None,
        description="Lọc màu (khớp tên SP, cột color, hoặc JSON colors — nên dùng giá trị từ category facets)",
    ),
    style_tag: Optional[str] = Query(None, description="Lọc kiểu phổ thông tự rút từ tên/thông tin sản phẩm"),
    search_refresh: Optional[str] = Query(
        None,
        description="Token làm mới random sort cho mỗi lượt search (giữ ổn định trong cùng lần phân trang).",
    ),
    skip_total: bool = Query(
        False,
        description="Bỏ COUNT(*) — dùng cho khối SP liên quan PDP (chỉ cần danh sách)",
    ),
    include_warehouse_clearance: bool = Query(
        False,
        description="Gắn warehouse_variants cho thẻ SP (chỉ bật storefront; admin để false tránh chậm)",
    ),
    warehouse_clearance_only: bool = Query(
        False,
        description="Chỉ SP hàng thanh lý kho (trang /kho-sale). Tìm q= vẫn gồm kho thanh lý khi không bật cờ này.",
    ),
    admin_list: bool = Query(
        False,
        description="Lưới admin: bỏ enrich sale/size-guide, không cache tìm kiếm, mặc định hiện cả SP ẩn.",
    ),
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
            search_refresh=search_refresh,
            skip_total=skip_total,
            user=current_user,
            include_warehouse_clearance=include_warehouse_clearance,
            warehouse_clearance_only=warehouse_clearance_only,
            admin_list=admin_list,
        )
    except Exception as e:
        return {"error": str(e), "status": "serialization_error"}


@router.get("/list/full", response_model=dict)
def read_products_full_list(
    response: Response,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
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
    is_active: Optional[bool] = Query(
        None,
        description="Lọc hiển thị shop. Mặc định true (chỉ SP đang bán).",
    ),
    q: Optional[str] = Query(None, description="Tìm theo tên, mã, danh mục, vật liệu, kiểu dáng, màu sắc, dịp, tính năng, size (từ khóa rời rạc)"),
    product_id: Optional[str] = Query(
        None,
        description="Tìm theo ID SP (cột A / prefix A|T+số, có hoặc không hậu tố a188SKU), mã SKU (code) hoặc khớp một phần",
    ),
    order_random: bool = Query(False, description="Trộn ngẫu nhiên (chỉ áp dụng khi không có q); phân trang theo random không ổn định giữa các lần tải"),
    sort: Optional[str] = Query(
        None,
        description="Sắp xếp: id_desc | newest | oldest | views_desc | available_desc | available_asc | id_asc (bị bỏ qua khi order_random=true)",
    ),
    size: Optional[str] = Query(None, description="Lọc size (khớp mảng JSON `sizes` của SP)"),
    color: Optional[str] = Query(
        None,
        description="Lọc màu (khớp tên SP, cột color, hoặc JSON colors — nên dùng giá trị từ category facets)",
    ),
    style_tag: Optional[str] = Query(None, description="Lọc kiểu phổ thông tự rút từ tên/thông tin sản phẩm"),
    search_refresh: Optional[str] = Query(
        None,
        description="Token làm mới random sort cho mỗi lượt search (giữ ổn định trong cùng lần phân trang).",
    ),
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
            search_refresh=search_refresh,
            user=current_user,
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
    warehouse_clearance_only: bool = Query(False, description="Facets trên tập /kho-sale"),
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
            warehouse_clearance_only=warehouse_clearance_only,
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


@router.get("/group-listing-path", response_model=dict)
def read_product_group_listing_path(
    response: Response,
    slug: str = Query(..., min_length=3, description="Slug PDP / URL marketing"),
    db: Session = Depends(get_db),
):
    """API nhẹ: chỉ trả đường dẫn listing nhóm (cache HTTP 10 phút)."""
    response.headers["Cache-Control"] = "public, max-age=600, stale-while-revalidate=120"
    source = (slug or "").strip()
    current = _lookup_product_by_slug(db, slug=source)
    pid = getattr(current, "product_id", None) if current else None
    path = crud.product.resolve_product_group_listing_path(
        db,
        source_slug=source,
        product=current,
        product_id=pid,
    )
    return {"redirect_path": path, "redirect_type": "group_listing"}


@router.get("/oos-group-redirect", response_model=dict)
def read_product_oos_group_redirect(
    response: Response,
    slug: str = Query(..., min_length=3, description="Slug PDP / URL marketing đang mở"),
    min_similarity: float = Query(
        0.8,
        ge=0.5,
        le=1.0,
        description="Giữ tương thích client; không dùng khi redirect listing nhóm",
    ),
    legacy_path: bool = Query(
        False,
        description="Giữ tương thích URL marketing một segment",
    ),
    db: Session = Depends(get_db),
):
    """
    Hết hàng / không có SP: trả ``redirect_path`` tới listing nhóm (/c/..., /danh-muc/..., /?q=...),
    không gợi ý PDP sản phẩm khác.
    """
    response.headers["Cache-Control"] = "public, max-age=600, stale-while-revalidate=120"
    source = (slug or "").strip()
    current = _lookup_product_by_slug(db, slug=source)
    pid = getattr(current, "product_id", None) if current else None
    path = crud.product.resolve_product_group_listing_path(
        db,
        source_slug=source,
        product=current,
        product_id=pid,
    )
    return {
        "redirect_slug": None,
        "redirect_path": path,
        "redirect_type": "group_listing",
        "similarity_min": min_similarity,
        "legacy_path": legacy_path,
    }


@router.get("/sitemap-slugs", response_model=dict)
def read_product_sitemap_slugs(
    response: Response,
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(5000, ge=1, le=10000),
    is_active: bool = Query(True),
    skip_total: bool = Query(False),
):
    """slug + updated_at only — lightweight for Next.js sitemap (avoids >2MB list payloads)."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    return crud.product.get_product_sitemap_slugs(
        db, skip=skip, limit=limit, is_active=is_active, skip_total=skip_total
    )


# Phải đăng ký TRƯỚC /{product_id} — nếu không "by-slug" bị nuốt như product_id.
@router.get("/by-slug/{slug:path}", response_model=Product)
def read_product_by_slug(
    slug: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Get product by slug (path parameter version)
    - URL: /api/v1/products/by-slug/{slug}
    """
    db_product = _lookup_product_by_slug(db, slug=slug)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_response(db, db_product, user=current_user)


@router.get("/by-slug", response_model=Product)
@router.get("/by-slug/", response_model=Product)
def read_product_by_slug_query(
    slug: str = Query(..., description="Product slug"),
    attach_group_listing: bool = Query(
        False,
        description="Khi SP hết hàng, kèm group_listing_path để redirect 1 round-trip",
    ),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Get product by slug (query parameter version)
    - URL: /api/v1/products/by-slug?slug={slug}
    - Frontend hiện đang gọi theo cách này
    """
    db_product = _lookup_product_by_slug(db, slug=slug)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_response(
        db,
        db_product,
        user=current_user,
        attach_group_listing=attach_group_listing,
    )


@router.get("/by-code/{product_code}", response_model=Product)
def read_product_by_code(
    product_code: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Get product by product_id, slug, or internal code (SKU).
    """
    db_product = _resolve_storefront_product(db, product_code)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_response(db, db_product, user=current_user)


@router.get("/by-id/{id}", response_model=Product)
def read_product_by_id(
    id: int,
    attach_group_listing: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Get product by database ID (integer primary key)
    """
    db_product = crud.product.get_product(db, product_id=id)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_response(
        db,
        db_product,
        user=current_user,
        attach_group_listing=attach_group_listing,
    )


def _normalize_excel_product_id(product_id: str) -> str:
    return unquote(product_id or "").strip()


def _resolve_admin_product_by_excel_id(db: Session, product_id: str):
    """Tra SP theo cột product_id Excel — dùng cho route query (ID có dấu /)."""
    pid = _normalize_excel_product_id(product_id)
    existing = crud.product.get_product_by_product_id(db, product_id=pid)
    if existing is None:
        existing = crud.product.resolve_product_by_sku(db, sku=pid)
    return existing


def _delete_product_by_excel_id(db: Session, product_id: str, *, admin_force: bool = True) -> Product:
    existing = _resolve_admin_product_by_excel_id(db, product_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Product not found")
    from app.services import warehouse_clearance as wh_clearance_svc

    block = wh_clearance_svc.parent_has_deletion_block(db, existing, admin_force=admin_force)
    if block:
        raise HTTPException(status_code=400, detail=block)
    db_product = crud.product.delete_product(db, product_id=existing.id, admin_force=admin_force)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_response(db, db_product)


class ProductExcelIdBody(BaseModel):
    product_id: str = Field(..., min_length=1, max_length=512)


class BulkDeleteByProductIdBody(BaseModel):
    product_ids: List[str] = Field(..., min_length=1, max_length=200)


@router.post("/by-product-id/delete", response_model=Product)
def delete_product_by_product_id_body(
    body: ProductExcelIdBody,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Xóa SP theo product_id trong JSON body — an toàn khi ID có / hoặc khoảng trắng."""
    return _delete_product_by_excel_id(db, body.product_id)


@router.post("/by-product-id/bulk-delete", response_model=dict)
def bulk_delete_products_by_product_id_body(
    body: BulkDeleteByProductIdBody,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Xóa nhiều SP admin — một transaction, không qua path URL."""
    deleted, errors = crud.product.bulk_delete_products_by_excel_product_ids(
        db, body.product_ids, admin_force=True
    )
    return {"deleted": deleted, "deleted_count": len(deleted), "errors": errors}


@router.put("/by-product-id", response_model=Product)
def update_product_by_product_id_query(
    product_update: ProductUpdate,
    product_id: str = Query(..., description="product_id Excel / mã kho (có thể chứa /)"),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Cập nhật SP khi product_id có dấu / — tránh 404 do path segment."""
    existing = _resolve_admin_product_by_excel_id(db, product_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Product not found")
    db_product = crud.product.update_product(db, product_id=existing.id, product_update=product_update)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_response(db, db_product)


@router.delete("/by-product-id", response_model=Product)
def delete_product_by_product_id_query(
    product_id: str = Query(..., description="product_id Excel / mã kho (có thể chứa /)"),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Xóa SP khi product_id có dấu / — tránh 404 do path segment."""
    return _delete_product_by_excel_id(db, product_id)


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
    """Admin: kiểm tra một URL nguồn qua scrape Hibox hoặc API CSSBuy (quy đổi như nhập Excel)."""
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Thiếu URL.")

    try:
        from app.services.admin_source_stock_batch import run_admin_source_url_scan

        out = run_admin_source_url_scan(
            db,
            url=url,
            domain=str(body.domain),
            dual_alternate_fallback=bool(body.dual_alternate_fallback),
            alternate_sequence_index=int(body.alternate_sequence_index),
        )
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
            sticky_seed_product_id=int(body.sticky_seed_product_id),
            skip_sticky_after_failure=bool(body.skip_sticky_after_failure),
            dual_alternate_fallback=bool(body.dual_alternate_fallback),
            alternate_sequence_index=int(body.alternate_sequence_index),
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

    deleted_db_ids, not_found_db_ids = crud.product.bulk_delete_products_by_db_ids(db, ordered)

    return {
        "ok": True,
        "deleted_count": len(deleted_db_ids),
        "deleted_db_ids": deleted_db_ids,
        "not_found_db_ids": not_found_db_ids,
    }


@router.post("/admin/source-stock-batch/clear-oos-flag", response_model=dict, include_in_schema=False)
def admin_source_stock_clear_oos_flag_route(
    body: AdminSingleProductDbIdBody,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """
    Gỡ cờ hết hàng nguồn (đọc sai / dọn danh sách báo cáo): không xóa sản; không đụng TTL batch admin.
    """
    out = admin_clear_false_source_oos_flag(db, db_id=int(body.db_id))
    if out.get("ok"):
        return out
    detail = str(out.get("detail") or "unknown_error")
    if detail == "product_not_found":
        raise HTTPException(status_code=404, detail=f"Không có product id={body.db_id}")
    raise HTTPException(status_code=400, detail=detail)


@router.post("/admin/source-stock-batch/force-worker-recheck", response_model=dict, include_in_schema=False)
def admin_source_stock_force_worker_recheck_route(
    body: AdminSingleProductDbIdBody,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """
    Xếp lại PDP worker: CSSBuy (/web/item) trước; chỉ scrape Hibox khi CSS blocked/error (chặn/CAPTCHA…);
    kết quả in_stock / out_of_stock cập nhật sau khi worker chạy.
    """
    out = admin_force_worker_source_stock_recheck(db, db_id=int(body.db_id))
    if not out.get("ok"):
        detail = str(out.get("detail") or "unknown_error")
        pid = body.db_id
        if detail == "product_not_found":
            raise HTTPException(status_code=404, detail=f"Không có product id={pid}")
        raise HTTPException(status_code=400, detail=detail)
    return out


@router.post("/admin/source-stock-batch/preview-url", response_model=dict, include_in_schema=False)
def admin_source_stock_preview_url_route(
    body: AdminSourceStockPreviewUrlBody,
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Thử PDP theo một link giống worker (CSSBuy một lần; Hibox chỉ fallback chặn); không sửa bảng products — có thể chậm (~1–3 phút)."""
    try:
        return admin_preview_source_stock_by_url(str(body.url or "").strip())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/admin/source-stock-batch/reset-pdp-cycle", response_model=dict, include_in_schema=False)
def admin_source_stock_reset_pdp_cycle_route(
    body: AdminSourceStockResetPdpBody,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """
    Reset toàn phạm vi: đặt lại các cột ``source_stock_*`` về «chưa biết»
    và xóa hàng chờ RAM của process đang nhận request. Bỏ qua sản ``queued``/``checking``.
    """
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Thiếu xác nhận: đặt «confirm»: true trong body sau khi đã đọc cảnh báo.",
        )
    try:
        out = admin_reset_source_stock_pdp_cycle(
            db,
            domain=str(body.domain),
            active_only=bool(body.active_only),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=str(out.get("detail") or "reset_failed"))
    return out


@router.get("/admin/source-stock-batch/queue-stats", response_model=dict, include_in_schema=False)
def admin_source_stock_batch_queue_stats(
    domain: Literal["hibox", "cssbuy", "vipomall"] = Query(
        "cssbuy",
        description="hibox = scrape hibox.mn; cssbuy = POST /web/item (không cần bấm modal).",
    ),
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Đếm SP trong phạm vi link + miền và tách TTL (sẵn sàng vòng / chờ cooldown)."""
    return admin_source_stock_queue_stats(db, domain=str(domain), active_only=bool(active_only))


@router.get("/admin/source-stock-batch/worker-state", response_model=dict, include_in_schema=False)
def admin_source_stock_worker_state(
    _: AdminUser = Depends(require_module_permission("products")),
):
    """
    Snapshot trạng thái worker PDP (CSSBuy trước, Hibox chỉ khi CSS blocked/error): env, cờ pause DB (chung mọi process), luồng daemon trong process hiện tại,
    và độ sâu hàng chờ in-memory của process đó (không phải tổng cluster).
    """
    return {"ok": True, **get_source_stock_worker_admin_snapshot(force_refresh_pause=True)}


@router.post("/admin/source-stock-batch/worker-pause", response_model=dict, include_in_schema=False)
def admin_source_stock_worker_pause_route(
    body: AdminSourceStockWorkerPauseBody,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """
    Tạm dừng / chạy tiếp kiểm tra nguồn qua CSDL (singleton). Áp ngay trong vòng vài giây cho mọi worker đang chạy.
    """
    set_source_stock_worker_paused(db, paused=bool(body.paused))
    return {"ok": True, **get_source_stock_worker_admin_snapshot(force_refresh_pause=True)}


@router.get("/admin/source-stock-batch/report", response_model=dict, include_in_schema=False)
def admin_source_stock_batch_report(
    domain: Literal["hibox", "cssbuy", "vipomall"] = Query(
        "cssbuy",
        description="hibox = scrape hibox.mn; cssbuy = POST /web/item.",
    ),
    active_only: bool = Query(True),
    window_days: int = Query(30, ge=1, le=366, description="Cửa sổ rolling «30 ngày» cho các đếm thời điểm"),
    samples_oos_page: int = Query(1, ge=1, description="Trang danh sách mẫu OOS (mới nhất trước)"),
    samples_in_stock_page: int = Query(1, ge=1, description="Trang danh sách mẫu in_stock"),
    samples_batch_ttl_page: int = Query(1, ge=1, description="Trang mẫu TTL batch trong cửa sổ"),
    sample_page_size: int = Query(
        200,
        ge=1,
        le=500,
        description="Số SP mỗi trang cho mỗi nhóm mẫu",
    ),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Báo cáo đã kiểm tra / OOS / còn hàng trong cửa sổ + lặp lại block queue-stats để đối chiếu."""
    return admin_source_stock_activity_report(
        db,
        domain=str(domain),
        active_only=bool(active_only),
        window_days=int(window_days),
        samples_oos_page=int(samples_oos_page),
        samples_in_stock_page=int(samples_in_stock_page),
        samples_batch_ttl_page=int(samples_batch_ttl_page),
        sample_page_size=int(sample_page_size),
    )


@router.get("/admin/source-stock-batch/product-urls", response_model=dict, include_in_schema=False)
def admin_source_stock_batch_product_urls(
    domain: Literal["hibox", "cssbuy", "vipomall"] = Query(
        "cssbuy",
        description="Lọc link phù hợp luồng kiểm tra (quy đổi sang Hibox hoặc CSSBuy)",
    ),
    limit: int = Query(6000, ge=1, le=15000),
    active_only: bool = Query(True, description="Chỉ sản phẩm is_active"),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    domain_l = (domain or "cssbuy").strip().lower()
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


# Catch-all product_id (có dấu /) — đăng ký CUỐI để không nuốt /admin/*, /by-id/*, …
@router.get("/{product_id:path}", response_model=Product)
def read_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Get product by product_id, slug, or internal code (SKU)."""
    pid = _normalize_excel_product_id(product_id)
    db_product = _resolve_storefront_product(db, pid)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_response(db, db_product, user=current_user)


@router.put("/{product_id:path}", response_model=Product)
def update_product(
    product_id: str,
    product_update: ProductUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Update product (product_id = Excel column A / product_id string)."""
    existing = _resolve_admin_product_by_excel_id(db, product_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Product not found")
    db_product = crud.product.update_product(db, product_id=existing.id, product_update=product_update)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_response(db, db_product)


@router.delete("/{product_id:path}", response_model=Product)
def delete_product(
    product_id: str,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Delete product (product_id = Excel column A / product_id string)."""
    return _delete_product_by_excel_id(db, product_id)
