from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Any, Optional
from app.db.session import SessionLocal, get_db
from app.schemas.category import Category, CategoryCreate, CategoryUpdate
from app.crud import category as crud_category
from app.crud import product as crud_product
from app.utils.ttl_cache import cache as ttl_cache

router = APIRouter()

# Cache cây danh mục từ sản phẩm (60s) — endpoint này được Next SSR layout gọi mỗi request,
# query tốn ~1-3s, dễ làm tràn pool DB khi có traffic / bot. Admin sửa danh mục: chờ ≤ 60s.
_CATEGORY_TREE_TTL = 60.0
_CATEGORY_TREE_CACHE_KEY_ACTIVE = "category_tree_v1:from_products:active=true"
_CATEGORY_TREE_CACHE_KEY_ALL = "category_tree_v1:from_products:active=false"


def _fetch_category_tree(is_active: bool):
    """Mở session thủ công — khi cache hit, không cần gọi hàm này, không tốn connection."""
    db = SessionLocal()
    try:
        return crud_product.get_category_tree_from_products(db, is_active=is_active)
    finally:
        db.close()


def _get_category_tree_from_products_impl(db: Session, is_active: bool = True):
    """Shared impl: vẫn nhận `db` để các caller nội bộ tận dụng được session sẵn có."""
    return crud_product.get_category_tree_from_products(db, is_active=is_active)


@router.get("/from-products", response_model=List[Any])
@router.get("/from-products/", response_model=List[Any])
def read_category_tree_from_products(is_active: bool = True):
    """
    Cây danh mục 3 cấp sinh từ sản phẩm:
    - Cấp 1 (cột AB): category
    - Cấp 2 (cột AC): subcategory
    - Cấp 3 (cột AD): sub_subcategory
    Trả về [{ name, slug, children: [{ name, slug, children: [{ name, slug }] }] }]

    Có cache 60s trong process (singleflight). Không nhận `Depends(get_db)` vì
    khi cache hit ta không muốn pool DB cấp connection (đó là nguồn QueuePool tràn ở prod).
    """
    key = _CATEGORY_TREE_CACHE_KEY_ACTIVE if is_active else _CATEGORY_TREE_CACHE_KEY_ALL
    return ttl_cache.get_or_fetch(
        key,
        _CATEGORY_TREE_TTL,
        lambda: _fetch_category_tree(is_active),
    )


@router.get("/from-products/by-path")
def read_category_by_path(
    level1: str = Query(..., description="Slug danh mục cấp 1"),
    level2: Optional[str] = Query(None, description="Slug danh mục cấp 2"),
    level3: Optional[str] = Query(None, description="Slug danh mục cấp 3"),
    is_active: bool = True,
    db: Session = Depends(get_db),
):
    """
    Resolve path slugs thành thông tin danh mục cho SEO.
    Trả về: { level, name, full_name, breadcrumb_names, product_count }
    """
    info = crud_product.get_category_by_path(
        db, level1_slug=level1, level2_slug=level2, level3_slug=level3, is_active=is_active
    )
    if info is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy danh mục")
    return info


@router.get("/from-products/seo-data")
def read_category_seo_data(
    level1: str = Query(..., description="Slug danh mục cấp 1"),
    level2: Optional[str] = Query(None, description="Slug danh mục cấp 2"),
    level3: Optional[str] = Query(None, description="Slug danh mục cấp 3"),
    is_active: bool = True,
    db: Session = Depends(get_db),
):
    """
    Lấy dữ liệu SEO đầy đủ cho danh mục:
    - Thông tin cơ bản (level, name, full_name, breadcrumb_names, product_count)
    - Ảnh (ưu tiên category_seo_meta, không thì từ sản phẩm)
    - seo_description / seo_body nếu đã có trong DB — **không** gọi Gemini tự động.

    Để có đoạn văn SEO (Gemini): dùng admin «Quản lý danh mục SEO» → chạy tạo SEO body, hoặc script/job chủ động.
    """
    data = crud_product.get_category_seo_data(
        db, level1_slug=level1, level2_slug=level2, level3_slug=level3,
        is_active=is_active, image_limit=4
    )
    if data is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy danh mục")

    return {
        "level": data.get("level"),
        "name": data.get("name"),
        "full_name": data.get("full_name"),
        "breadcrumb_names": data.get("breadcrumb_names"),
        "product_count": data.get("product_count"),
        "images": data.get("images", []),
        "seo_description": data.get("seo_description"),
        "seo_body": data.get("seo_body"),
    }


@router.get("", response_model=List[Category], include_in_schema=False)
@router.get("/", response_model=List[Category])
def read_categories(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Lấy danh sách danh mục
    """
    categories = crud_category.get_categories(db, skip=skip, limit=limit)
    return categories

@router.get("/{category_id}", response_model=Category)
def read_category(category_id: int, db: Session = Depends(get_db)):
    """
    Lấy thông tin chi tiết danh mục
    """
    db_category = crud_category.get_category(db, category_id=category_id)
    if db_category is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy danh mục")
    return db_category

@router.get("/slug/{slug}", response_model=Category)
def read_category_by_slug(slug: str, db: Session = Depends(get_db)):
    """
    Lấy thông tin danh mục theo slug
    """
    db_category = crud_category.get_category_by_slug(db, slug=slug)
    if db_category is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy danh mục")
    return db_category

@router.post("", response_model=Category, include_in_schema=False)
@router.post("/", response_model=Category)
def create_category(category: CategoryCreate, db: Session = Depends(get_db)):
    """
    Tạo danh mục mới
    """
    return crud_category.create_category(db=db, category=category)

@router.put("/{category_id}", response_model=Category)
def update_category(category_id: int, category: CategoryUpdate, db: Session = Depends(get_db)):
    """
    Cập nhật thông tin danh mục
    """
    db_category = crud_category.update_category(db, category_id=category_id, category_update=category)
    if db_category is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy danh mục")
    return db_category

@router.delete("/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db)):
    """
    Xóa danh mục
    """
    db_category = crud_category.delete_category(db, category_id=category_id)
    if db_category is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy danh mục")
    return {"message": "Đã xóa danh mục thành công"}
