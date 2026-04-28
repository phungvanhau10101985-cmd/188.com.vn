from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from urllib.parse import unquote
from app.db.session import get_db
from app.models.product import Product as ProductModel

router = APIRouter()

@router.get("/debug/slug-test/{slug:path}")
def debug_slug(slug: str, db: Session = Depends(get_db)):
    """
    Debug endpoint để test slug encoding
    """
    results = {
        "original_slug": slug,
        "decoded_once": unquote(slug),
        "decoded_twice": unquote(unquote(slug)),
        "decoded_thrice": unquote(unquote(unquote(slug))),
        "manual_replace": slug.replace('%20', ' ').replace('%2F', '/').replace('%3A', ':')
    }
    
    # Try to find product
    product_found = None
    for attempt_slug in [
        unquote(slug),
        unquote(unquote(slug)),
        unquote(unquote(unquote(slug))),
        slug.replace('%20', ' ').replace('%2F', '/').replace('%3A', ':')
    ]:
        product = db.query(ProductModel).filter(ProductModel.slug == attempt_slug).first()
        if product:
            product_found = {
                "id": product.id,
                "name": product.name,
                "slug": product.slug,
                "found_with": attempt_slug
            }
            break
    
    results["product_found"] = product_found
    
    return results

@router.get("/debug/products/count")
def debug_products_count(db: Session = Depends(get_db)):
    """
    Debug: Đếm số lượng products
    """
    total = db.query(ProductModel).count()
    active = db.query(ProductModel).filter(ProductModel.is_active == True).count()
    with_slugs = db.query(ProductModel).filter(ProductModel.slug.isnot(None)).count()
    
    return {
        "total_products": total,
        "active_products": active,
        "products_with_slugs": with_slugs
    }

@router.get("/debug/products/sample-slugs")
def debug_sample_slugs(db: Session = Depends(get_db)):
    """
    Debug: Lấy danh sách slugs mẫu
    """
    products = db.query(ProductModel.slug, ProductModel.name).filter(
        ProductModel.slug.isnot(None),
        ProductModel.is_active == True
    ).limit(5).all()
    
    slugs = [{"slug": product[0], "name": product[1]} for product in products if product[0]]
    
    return {
        "sample_slugs": slugs,
        "count": len(slugs)
    }

@router.get("/debug/products/search-by-slug/{slug_part:path}")
def debug_search_by_slug(slug_part: str, db: Session = Depends(get_db)):
    """
    Debug: Tìm products bằng slug part
    """
    decoded_slug = unquote(slug_part)
    
    # Exact match
    exact_match = db.query(ProductModel).filter(ProductModel.slug == decoded_slug).first()
    
    # Partial match
    partial_matches = db.query(ProductModel).filter(
        ProductModel.slug.contains(decoded_slug)
    ).limit(10).all()
    
    partial_results = []
    for product in partial_matches:
        partial_results.append({
            "id": product.id,
            "name": product.name,
            "slug": product.slug,
            "match_type": "contains"
        })
    
    return {
        "search_term": decoded_slug,
        "exact_match": {
            "found": exact_match is not None,
            "product": {
                "id": exact_match.id if exact_match else None,
                "name": exact_match.name if exact_match else None,
                "slug": exact_match.slug if exact_match else None
            }
        },
        "partial_matches": partial_results
    }