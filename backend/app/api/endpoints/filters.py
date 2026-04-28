# backend/app/api/endpoints/filters.py - NEW FILE
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, List, Any
from app.db.session import get_db
from app.models.product import Product
from app.models.category import Category

router = APIRouter()

@router.get("/filters", response_model=Dict[str, List[str]])
async def get_all_filters(db: Session = Depends(get_db)):
    """
    Lấy tất cả filters available từ database
    """
    try:
        # Lấy categories
        categories = db.query(Category.name).filter(Category.is_active == True).all()
        category_list = [cat[0] for cat in categories if cat[0]]
        
        # Lấy brands từ products
        brands = db.query(Product.brand_name).filter(
            Product.brand_name.isnot(None),
            Product.is_active == True
        ).distinct().all()
        brand_list = [brand[0] for brand in brands if brand[0]]
        
        # Lấy materials
        materials = db.query(Product.material).filter(
            Product.material.isnot(None),
            Product.is_active == True
        ).distinct().all()
        material_list = [mat[0] for mat in materials if mat[0]]
        
        # Lấy styles
        styles = db.query(Product.style).filter(
            Product.style.isnot(None),
            Product.is_active == True
        ).distinct().all()
        style_list = [style[0] for style in styles if style[0]]
        
        # Lấy fashion_styles
        fashion_styles = db.query(Product.fashion_style).filter(
            Product.fashion_style.isnot(None),
            Product.is_active == True
        ).distinct().all()
        fashion_style_list = [fs[0] for fs in fashion_styles if fs[0]]
        
        # Lấy genders
        genders = db.query(Product.gender).filter(
            Product.gender.isnot(None),
            Product.is_active == True
        ).distinct().all()
        gender_list = [gender[0] for gender in genders if gender[0]]
        
        # Lấy origins
        origins = db.query(Product.origin).filter(
            Product.origin.isnot(None),
            Product.is_active == True
        ).distinct().all()
        origin_list = [origin[0] for origin in origins if origin[0]]
        
        # Lấy occasions
        occasions = db.query(Product.occasion).filter(
            Product.occasion.isnot(None),
            Product.is_active == True
        ).distinct().all()
        occasion_list = [occasion[0] for occasion in occasions if occasion[0]]
        
        return {
            "categories": category_list,
            "brands": brand_list,
            "materials": material_list,
            "styles": style_list,
            "fashion_styles": fashion_style_list,
            "genders": gender_list,
            "origins": origin_list,
            "occasions": occasion_list
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching filters: {str(e)}")