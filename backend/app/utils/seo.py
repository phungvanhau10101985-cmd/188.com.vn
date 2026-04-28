from typing import Dict, Any
from app.models.product import Product

def generate_product_meta(product: Product) -> Dict[str, Any]:
    """
    Tạo thẻ meta SEO cho sản phẩm
    """
    if not product.meta_title:
        product.meta_title = f"{product.name} - {product.brand_name} | 188.com.vn"
    
    if not product.meta_description:
        product.meta_description = f"{product.name} - {product.description[:160]}..." if product.description else f"Mua {product.name} chính hãng tại 188.com.vn"
    
    if not product.meta_keywords:
        keywords = [
            product.name,
            product.brand_name,
            product.category,
            product.subcategory,
            "giày da nam",
            "thời trang nam"
        ]
        if product.style:
            keywords.append(product.style)
        if product.material:
            keywords.append(product.material)
        
        product.meta_keywords = ", ".join([kw for kw in keywords if kw])
    
    return {
        "title": product.meta_title,
        "description": product.meta_description,
        "keywords": product.meta_keywords,
        "og_title": product.meta_title,
        "og_description": product.meta_description,
        "og_image": product.main_image,
        "og_url": f"/products/{product.slug}"
    }

def generate_category_meta(category) -> Dict[str, Any]:
    """
    Tạo thẻ meta SEO cho danh mục
    """
    return {
        "title": f"{category.name} - Danh mục sản phẩm | 188.com.vn",
        "description": f"Khám phá {category.name} chất lượng cao tại 188.com.vn. {category.description or 'Sản phẩm chính hãng, giá tốt.'}",
        "keywords": f"{category.name}, giày dép nam, thời trang nam, 188.com.vn"
    }
