from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.product import Product as ProductModel

router = APIRouter()

@router.get("/products/fallback/{product_id}")
def get_product_fallback(product_id: str, db: Session = Depends(get_db)):
    """
    Fallback endpoint để lấy sản phẩm khi slug không hoạt động
    """
    try:
        # Try by product_id
        product = db.query(ProductModel).filter(ProductModel.product_id == product_id).first()
        if product:
            return product
        
        # Try by ID
        if product_id.isdigit():
            product = db.query(ProductModel).filter(ProductModel.id == int(product_id)).first()
            if product:
                return product
        
        raise HTTPException(status_code=404, detail="Product not found")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
