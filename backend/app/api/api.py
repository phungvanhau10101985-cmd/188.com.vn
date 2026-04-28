# backend/app/api/api.py
from fastapi import APIRouter
from app.api.endpoints import (
    auth, products, categories, cart, 
    debug, fallback, filters, 
    import_export, user_behavior, analytics,
    orders, category_seo, loyalty,
    notifications, push, nanoai_search
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(loyalty.router, prefix="/loyalty", tags=["loyalty"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(push.router, prefix="/push", tags=["push"])
api_router.include_router(products.router, prefix="/products", tags=["products"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(category_seo.router, prefix="/category-seo", tags=["category-seo"])
api_router.include_router(cart.router, prefix="/cart", tags=["cart"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"]) 
api_router.include_router(debug.router, prefix="/debug", tags=["debug"])
api_router.include_router(fallback.router, prefix="/fallback", tags=["fallback"])
api_router.include_router(filters.router, prefix="/filters", tags=["filters"])
api_router.include_router(import_export.router, prefix="/import-export", tags=["import-export"])
api_router.include_router(user_behavior.router, prefix="/user-behavior", tags=["user-behavior"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(nanoai_search.router, prefix="/nanoai", tags=["nanoai"])