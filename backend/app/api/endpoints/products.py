# backend/app/api/endpoints/products.py - COMPLETE FIXED VERSION WITH BOTH ENDPOINTS
from datetime import datetime
import io

import pandas as pd
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app import crud
from app.crud import product_search_cache as product_search_cache_crud
from app.models.search_mapping import SearchMapping, SearchMappingType
from app.utils.vietnamese import normalize_for_search_no_accent
from difflib import SequenceMatcher
import json
from app.schemas.product import Product, ProductCreate, ProductUpdate, PurgeDeadMediaUrlBody
from app.crud.product_category_size_guide import enrich_product_payloads_with_category_size_guide
from app.models.admin import AdminUser
from app.core.security import require_module_permission
from app.core.config import settings
from app.crud import product_media_purge

router = APIRouter()


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
):
    """
    Get products with filtering and search (by name; the product_id filter matches Excel id or SKU code).
    """
    try:
        raw_q = (q or "").strip()
        pid = (product_id or "").strip()
        if order_random and not raw_q and not pid:
            response.headers["Cache-Control"] = "private, no-store"
        else:
            response.headers["Cache-Control"] = "public, max-age=60"
        cache_key = None
        if raw_q and not pid:
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
                pro_lower_price=pro_lower_price,
                pro_high_price=pro_high_price,
                min_price=min_price,
                max_price=max_price,
                is_active=is_active,
                sort=crud.product.normalize_product_list_sort(sort),
            )
            cached = product_search_cache_crud.get_cached_result(db, cache_key)
            if cached is not None:
                return cached

        result = crud.product.get_products(
            db, skip=skip, limit=limit,
            category=category, subcategory=subcategory, sub_subcategory=sub_subcategory,
            shop_name=shop_name, shop_id=shop_id,
            pro_lower_price=pro_lower_price, pro_high_price=pro_high_price,
            min_price=min_price, max_price=max_price, is_active=is_active,
            q=q, product_id=product_id,
            order_random=order_random,
            sort=sort,
        )
        
        # Convert SQLAlchemy objects to dicts
        if result and "products" in result:
            result["products"] = _serialize_products_for_api(db, result["products"])

        if cache_key and raw_q and not pid and not result.get("redirect_path") and not result.get("error"):
            try:
                product_search_cache_crud.set_cached_result(db, cache_key, result)
            except Exception:
                pass
        
        return result
    except Exception as e:
        return {"error": str(e), "status": "serialization_error"}


@router.get("/export-unused-internal-skus/available-count", response_model=dict)
def get_unused_internal_sku_available_count(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """Số lượng mã SKU còn có thể export (và tổng dải) — phục vụ form admin."""
    from app.services.product_internal_sku import count_available_internal_skus_for_export

    return count_available_internal_skus_for_export(db)


@router.post("/export-unused-internal-skus")
def export_unused_internal_skus(
    count: int = Query(100, ge=1, le=10_000, description="Số mã SKU cần lấy (A0001–Z9999, không gồm X0000)"),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("products")),
):
    """
    Xuất Excel một cột `sku`: các mã chưa dùng cho sản phẩm và chưa từng export trước đó.
    Mã được ghi vào bảng `internal_sku_exports` để không trùng ở lần export sau và không bị tự sinh trùng khi import.
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

