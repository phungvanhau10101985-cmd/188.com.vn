# backend/app/schemas/product.py - COMPLETE FIXED VERSION
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any, Union
from datetime import datetime

class ProductBase(BaseModel):
    """Base schema matching Excel columns A-AJ (36 columns)"""
    
    # Cột 1: id
    product_id: str = Field(..., description="1: id")
    
    # Cột 2: sku
    code: Optional[str] = Field(None, description="2: sku")
    
    # Cột 3: origin
    origin: Optional[str] = Field(None, description="3: origin")
    
    # Cột 4: brand
    brand_name: Optional[str] = Field(None, description="4: brand")
    
    # Cột 5: name
    name: str = Field(..., description="5: name")
    
    # Cột 6: pro_content
    description: Optional[str] = Field(None, description="6: pro_content")
    
    # Cột 7: price
    price: float = Field(0, description="7: price")
    
    # Cột 8: shop_name
    shop_name: Optional[str] = Field(None, description="8: shop_name")
    
    # Cột 9: shop_id
    shop_id: Optional[str] = Field(None, description="9: shop_id")
    
    # Cột 10: pro_lower_price
    pro_lower_price: Optional[str] = Field(None, description="10: pro_lower_price")
    
    # Cột 11: pro_high_price
    pro_high_price: Optional[str] = Field(None, description="11: pro_high_price")
    
    # Cột 12: rating_group_id
    group_rating: int = Field(0, description="12: rating_group_id")
    
    # Cột 13: question_group_id
    group_question: int = Field(0, description="13: question_group_id")
    
    # Cột 14: sizes
    sizes: List[str] = Field(default_factory=list, description="14: sizes")
    
    # Cột 15: Variant (colors)
    colors: List[Dict[str, Any]] = Field(default_factory=list, description="15: Variant (colors)")
    
    # Cột 16: gallery_images
    images: List[str] = Field(default_factory=list, description="16: gallery_images")
    
    # Cột 17: detail_images
    gallery: List[str] = Field(default_factory=list, description="17: detail_images")
    
    # Cột 18: product_url
    link_default: Optional[str] = Field(None, description="18: product_url")
    
    # Cột 19: video_url
    video_link: Optional[str] = Field(None, description="19: video_url")
    
    # Cột 20: main_image
    main_image: Optional[str] = Field(None, description="20: main_image")
    
    # Cột 21: likes_count
    likes: int = Field(0, description="21: likes_count")
    
    # Cột 22: purchases_count
    purchases: int = Field(0, description="22: purchases_count")
    
    # Cột 23: reviews_count
    rating_total: int = Field(0, description="23: reviews_count")
    
    # Cột 24: questions_count
    question_total: int = Field(0, description="24: questions_count")
    
    # Cột 25: rating_score
    rating_point: float = Field(0.0, description="25: rating_score")
    
    # Cột 26: stock_quantity
    available: int = Field(0, description="26: stock_quantity")
    
    # Cột 27: deposit_required
    deposit_require: bool = Field(False, description="27: deposit_required")
    
    # Cột 28: Main Category
    category: Optional[str] = Field(None, description="28: Main Category")
    
    # Cột 29: Subcategory
    subcategory: Optional[str] = Field(None, description="29: Subcategory")
    
    # Cột 30: Sub-subcategory
    sub_subcategory: Optional[str] = Field(None, description="30: Sub-subcategory")
    
    # Cột 31: Material
    material: Optional[str] = Field(None, description="31: Material")
    
    # Cột 32: Style
    style: Optional[str] = Field(None, description="32: Style")
    
    # FIX: Cột 33: Color -> color
    color: Optional[str] = Field(None, description="33: Color")
    
    # FIX: Cột 34: Occasion -> occasion
    occasion: Optional[str] = Field(None, description="34: Occasion")
    
    # Cột 35: Features
    features: List[str] = Field(default_factory=list, description="35: Features")
    
    # Cột 36: Weight
    weight: Optional[str] = Field(None, description="36: Weight")
    
    # Cột AK (37): Thông tin sản phẩm (JSON) - DB/ORM có thể trả về dict hoặc chuỗi JSON
    product_info: Optional[Union[Dict[str, Any], str]] = Field(None, description="AK: Thông tin sản phẩm (JSON)")
    
    # Cột AL (38): Slug (export only; import auto-generated)
    slug: Optional[str] = Field(None, description="AL: Slug (auto-generated khi import)")

    # SEO fields
    meta_title: Optional[str] = Field(None, description="SEO: meta title")
    meta_description: Optional[str] = Field(None, description="SEO: meta description")
    meta_keywords: Optional[str] = Field(None, description="SEO: meta keywords")

class ProductCreate(ProductBase):
    """Schema for creating product"""
    is_active: bool = True

class ProductUpdate(BaseModel):
    """Schema for updating product"""
    product_id: Optional[str] = None
    code: Optional[str] = None
    origin: Optional[str] = None
    brand_name: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    shop_name: Optional[str] = None
    shop_id: Optional[str] = None
    pro_lower_price: Optional[str] = None
    pro_high_price: Optional[str] = None
    group_rating: Optional[int] = None
    group_question: Optional[int] = None
    sizes: Optional[List[str]] = None
    colors: Optional[List[Dict[str, Any]]] = None
    images: Optional[List[str]] = None
    gallery: Optional[List[str]] = None
    link_default: Optional[str] = None
    video_link: Optional[str] = None
    main_image: Optional[str] = None
    likes: Optional[int] = None
    purchases: Optional[int] = None
    rating_total: Optional[int] = None
    question_total: Optional[int] = None
    rating_point: Optional[float] = None
    available: Optional[int] = None
    deposit_require: Optional[bool] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    sub_subcategory: Optional[str] = None
    material: Optional[str] = None
    style: Optional[str] = None
    color: Optional[str] = None
    occasion: Optional[str] = None
    features: Optional[List[str]] = None
    weight: Optional[str] = None
    product_info: Optional[Dict[str, Any]] = None
    slug: Optional[str] = None
    is_active: Optional[bool] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None

def _build_fallback_product_info(obj: Any) -> Dict[str, Any]:
    """Khi product_info (cột AK) null, tạo object từ các cột khác để frontend hiển thị đúng tab Thông tin sản phẩm."""
    def _v(name: str) -> Any:
        return getattr(obj, name, None)
    info: Dict[str, Any] = {}
    # product_info (thông tin chung)
    if _v("brand_name") or _v("origin") or _v("name") or _v("code") or _v("category"):
        info["product_info"] = {
            k: v for k, v in {
                "sku": _v("code"),
                "name": _v("name"),
                "brand": _v("brand_name"),
                "origin": _v("origin"),
                "category": {"level_1": _v("category"), "level_2": _v("subcategory"), "level_3": _v("sub_subcategory")}
                if (_v("category") or _v("subcategory") or _v("sub_subcategory")) else None,
            }.items() if v is not None
        }
        if info["product_info"].get("category") is None:
            info["product_info"].pop("category", None)
    # specifications
    if _v("material") or _v("style") or _v("weight") or _v("occasion") or _v("features"):
        spec: Dict[str, Any] = {}
        if _v("material"):
            spec["upper_material"] = _v("material")
        if _v("style"):
            spec["style"] = _v("style")
        if _v("weight"):
            spec["weight_grams"] = _v("weight")
        if _v("occasion"):
            spec["occasion"] = _v("occasion")
        if _v("features") and isinstance(getattr(obj, "features", None), list) and getattr(obj, "features"):
            spec["features"] = getattr(obj, "features")
        if spec:
            info["specifications"] = spec
    # variants (colors, sizes)
    if _v("color") or (_v("sizes") and isinstance(getattr(obj, "sizes", None), list) and getattr(obj, "sizes")):
        variants: Dict[str, Any] = {}
        if _v("color"):
            variants["colors"] = [s.strip() for s in str(_v("color")).split(",") if s.strip()]
        if _v("sizes") and isinstance(getattr(obj, "sizes", None), list):
            variants["sizes"] = getattr(obj, "sizes")
        if variants:
            info["variants"] = variants
    if _v("available") is not None:
        info["market_info"] = {"stock": _v("available")}
    return info if info else {}


class Product(ProductBase):
    """Complete Product schema for response"""
    id: int
    is_active: bool
    created_at: Optional[datetime] = None  # DB có thể trả None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

    @model_validator(mode="after")
    def fill_product_info_from_columns(self):
        """Chuẩn hóa product_info: chuỗi JSON -> dict. Khi null/empty thì điền từ các cột khác."""
        import json
        val = self.product_info
        if val is not None:
            if isinstance(val, dict) and len(val) > 0:
                return self
            if isinstance(val, str) and val.strip():
                s = val.strip()
                # Có thể bị double-encode (chuỗi chứa \" và \\u)
                for _ in range(3):
                    try:
                        parsed = json.loads(s)
                        if isinstance(parsed, dict) and len(parsed) > 0:
                            self.product_info = parsed
                            return self
                        if isinstance(parsed, str) and parsed.strip():
                            s = parsed.strip()
                            continue
                        break
                    except Exception:
                        break
        fallback = _build_fallback_product_info(self)
        if fallback:
            self.product_info = fallback
        return self

class ProductImportRequest(BaseModel):
    """Request for importing Excel"""
    file_path: Optional[str] = None
    overwrite: bool = False

class ProductExportRequest(BaseModel):
    """Request for exporting to Excel"""
    category: Optional[str] = None
    format: str = "excel"