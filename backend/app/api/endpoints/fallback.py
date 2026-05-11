from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.product import Product as ProductModel

router = APIRouter()

def _serialize_product(product: ProductModel) -> dict:
    return {col.key: getattr(product, col.key, None) for col in ProductModel.__table__.columns}


@router.get("/products/fallback/{product_id}")
def get_product_fallback(product_id: str, db: Session = Depends(get_db)):
    """
    Fallback endpoint để lấy sản phẩm khi slug không hoạt động
    """
    key = (product_id or "").strip()
    if not key:
        raise HTTPException(status_code=404, detail="Product not found")
    try:
        # Try by product_id (Excel/import id)
        product = db.query(ProductModel).filter(ProductModel.product_id == key).first()
        if product:
            return _serialize_product(product)
        
        # Try by slug (frontend/product URLs often pass this value)
        product = db.query(ProductModel).filter(ProductModel.slug == key).first()
        if product:
            return _serialize_product(product)

        # Try by ID
        if key.isdigit():
            product = db.query(ProductModel).filter(ProductModel.id == int(key)).first()
            if product:
                return _serialize_product(product)
        
        raise HTTPException(status_code=404, detail="Product not found")
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
