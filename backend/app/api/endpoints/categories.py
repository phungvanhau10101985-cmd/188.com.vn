from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Any, Optional
from app.db.session import get_db
from app.schemas.category import Category, CategoryCreate, CategoryUpdate
from app.crud import category as crud_category
from app.crud import product as crud_product

router = APIRouter()


def _get_category_tree_from_products_impl(db: Session, is_active: bool = True):
    """Shared impl để dùng cho cả /from-products và /from-products/."""
    return crud_product.get_category_tree_from_products(db, is_active=is_active)


@router.get("/from-products", response_model=List[Any])
@router.get("/from-products/", response_model=List[Any])
def read_category_tree_from_products(
    is_active: bool = True,
    db: Session = Depends(get_db),
):
    """
    Cây danh mục 3 cấp sinh từ sản phẩm:
    - Cấp 1 (cột AB): category
    - Cấp 2 (cột AC): subcategory
    - Cấp 3 (cột AD): sub_subcategory
    Trả về [{ name, slug, children: [{ name, slug, children: [{ name, slug }] }] }]
    """
    return _get_category_tree_from_products_impl(db, is_active=is_active)


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
    - 4 ảnh sản phẩm đầu tiên (cho og:image)
    - Mô tả SEO được viết bởi AI
    
    Trả về: {
        level, name, full_name, breadcrumb_names, product_count,
        images: [url1, url2, url3, url4],
        seo_description: "Mô tả SEO chuẩn 150-160 ký tự"
    }
    """
    from app.services.category_seo_service import (
        generate_category_seo_description,
        generate_category_seo_body,
    )

    # Lấy dữ liệu: ưu tiên từ category_seo_meta (4 ảnh + mô tả cố định), không thì từ products
    data = crud_product.get_category_seo_data(
        db, level1_slug=level1, level2_slug=level2, level3_slug=level3,
        is_active=is_active, image_limit=4
    )
    if data is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy danh mục")

    # Mô tả SEO ngắn: nếu đã có trong data thì dùng luôn, không gọi AI
    seo_description = data.get("seo_description")
    if not seo_description:
        seo_description = generate_category_seo_description(
            category_name=data.get("full_name", ""),
            breadcrumb_names=data.get("breadcrumb_names", []),
            product_count=data.get("product_count", 0),
            sample_product_names=data.get("sample_product_names", [])
        )

    # Đoạn văn SEO 150-300 từ (cuối trang): nếu chưa có thì gọi Gemini và lưu
    seo_body = data.get("seo_body")
    if not seo_body:
        sibling_names = crud_product.get_category_sibling_names(
            db, level1_slug=level1, level2_slug=level2, level3_slug=level3, is_active=is_active
        )
        seo_body = generate_category_seo_body(
            category_name=data.get("full_name", ""),
            breadcrumb_names=data.get("breadcrumb_names", []),
            product_count=data.get("product_count", 0),
            sample_product_names=data.get("sample_product_names", []),
            related_category_names=sibling_names if sibling_names else None,
        )
        if seo_body:
            path_parts = [level1]
            if level2:
                path_parts.append(level2)
            if level3:
                path_parts.append(level3)
            category_path = "/".join(path_parts)
            crud_product.set_category_seo_body(db, category_path=category_path, seo_body=seo_body)

    return {
        "level": data.get("level"),
        "name": data.get("name"),
        "full_name": data.get("full_name"),
        "breadcrumb_names": data.get("breadcrumb_names"),
        "product_count": data.get("product_count"),
        "images": data.get("images", []),
        "seo_description": seo_description,
        "seo_body": seo_body,
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
