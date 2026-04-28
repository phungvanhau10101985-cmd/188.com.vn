# backend/app/db/__init__.py
import sys
from app.db.base import Base

# Import tất cả các models
print("✅ Loading database models...")

try:
    from app.models.category import Category
    print("✅ Category model loaded")
except ImportError as e:
    print(f"⚠️  Error loading Category model: {e}")

try:
    from app.models.product import Product
    print("✅ Product model loaded")
except ImportError as e:
    print(f"⚠️  Error loading Product model: {e}")

try:
    from app.models.user import User, UserProductView, UserFavorite, UserCategoryView, UserBrandView, UserSearchHistory, UserShopInteraction
    print("✅ User models loaded")
except ImportError as e:
    print(f"⚠️  Error loading User models: {e}")

try:
    from app.models.cart import Cart, CartItem
    print("✅ Cart models loaded")
except ImportError as e:
    print(f"⚠️  Error loading Cart models: {e}")

try:
    from app.models.admin import AdminUser
    print("✅ AdminUser model loaded")
except ImportError:
    print("ℹ️  AdminUser model not available")

try:
    from app.models.order import Order, OrderItem, Payment
    print("✅ Order models loaded")
except ImportError as e:
    print(f"⚠️  Error loading Order models: {e}")

print("📦 All models imported successfully")