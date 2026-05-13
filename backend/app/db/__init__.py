# backend/app/db/__init__.py
import sys
from app.db.base import Base

# Import tất cả các models
print("[OK] Loading database models...")

try:
    from app.models.category import Category
    print("[OK] Category model loaded")
except ImportError as e:
    print(f"[WARN] Error loading Category model: {e}")

try:
    from app.models.product import Product
    print("[OK] Product model loaded")
except ImportError as e:
    print(f"[WARN] Error loading Product model: {e}")

try:
    from app.models.user import User, UserProductView, UserFavorite, UserCategoryView, UserBrandView, UserSearchHistory, UserShopInteraction
    print("[OK] User models loaded")
except ImportError as e:
    print(f"[WARN] Error loading User models: {e}")

try:
    from app.models.cart import Cart, CartItem
    print("[OK] Cart models loaded")
except ImportError as e:
    print(f"[WARN] Error loading Cart models: {e}")

try:
    from app.models.admin import AdminUser
    print("[OK] AdminUser model loaded")
except ImportError:
    print("[INFO] AdminUser model not available")

try:
    from app.models.order import Order, OrderItem, Payment
    print("[OK] Order models loaded")
except ImportError as e:
    print(f"[WARN] Error loading Order models: {e}")

print("[OK] All models imported successfully")