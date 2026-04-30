# backend/app/models/__init__.py - FIXED VERSION
"""
Models initialization - IMPORT ORDER MATTERS!
Tránh circular import bằng cách import đúng thứ tự
"""

import sys
from app.db.base import Base

# ========== IMPORT ĐÚNG THỨ TỰ ==========

# 1a. Import SeoCluster trước (Category trỏ FK tới seo_clusters)
from app.models.seo_cluster import SeoCluster
print("✅ SeoCluster model loaded")

# 1b. Import Category (phụ thuộc SeoCluster qua seo_cluster_id)
from app.models.category import Category
print("✅ Category model loaded")

# 2. Import Product (phụ thuộc Category)
from app.models.product import Product
print("✅ Product model loaded")

# 3. Import User (không phụ thuộc)
from app.models.user import User, UserProductView, UserFavorite
print("✅ User models loaded")

from app.models.guest_behavior import GuestProductView, GuestFavorite, GuestSearchHistory
print("✅ Guest behavior models loaded")

from app.models.user_trusted_device import UserTrustedDevice
print("✅ UserTrustedDevice model loaded")
from app.models.email_login_challenge import EmailLoginChallenge
from app.models.email_trusted_device import EmailTrustedDevice
print("✅ Email login challenge / trusted device models loaded")
from app.models.push_subscription import UserPushSubscription
print("✅ UserPushSubscription model loaded")

# 3a. Analytics events (phụ thuộc User)
from app.models.analytics_event import AnalyticsEvent
print("✅ AnalyticsEvent model loaded")

# 3b. Import UserAddress (phụ thuộc User)
from app.models.address import UserAddress
print("✅ UserAddress model loaded")

# 4. Import Cart models
from app.models.cart import Cart, CartItem
print("✅ Cart models loaded")

# 5. Import Admin (nếu có)
try:
    from app.models.admin import AdminUser, AdminRole
    print("✅ AdminUser model loaded")
except ImportError:
    AdminUser = None  # type: ignore[misc, assignment]
    AdminRole = None
    print("ℹ️  AdminUser model not available")

# 6. Import Order models (phụ thuộc User, Product)
from app.models.order import Order, OrderItem, Payment
print("✅ Order models loaded")

# 6b. Bank accounts (cài đặt quản trị)
from app.models.bank_account import BankAccount
print("✅ BankAccount model loaded")

# 6b2. Mã nhúng site (GA, Facebook, Zalo…)
from app.models.site_embed_code import SiteEmbedCode
print("✅ SiteEmbedCode model loaded")

# 6c. Product questions (câu hỏi câu trả lời sản phẩm)
from app.models.product_question import ProductQuestion, ProductQuestionUsefulVote
print("✅ ProductQuestion model loaded")

# 6d. Product reviews (đánh giá sản phẩm - chỉ admin trả lời)
from app.models.product_review import ProductReview, ProductReviewUsefulVote
print("✅ ProductReview model loaded")

# 6e. Category SEO mapping (quản lý canonical/redirect cho danh mục)
from app.models.category_seo import CategorySeoMapping, CategorySeoDictionary, CategorySeoMeta
print("✅ CategorySeoMapping model loaded")

# 6f. Category transform rules (lưu lịch sử chỉnh danh mục)
from app.models.category_transform_rule import CategoryTransformRule
print("✅ CategoryTransformRule model loaded")

# 6g. Category final mapping (đầu -> cuối)
from app.models.category_final_mapping import CategoryFinalMapping
print("✅ CategoryFinalMapping model loaded")

# 7. Import các models user behavior còn lại
try:
    from app.models.user import UserCategoryView, UserBrandView, UserSearchHistory, UserShopInteraction
    print("✅ User behavior models loaded")
except ImportError:
    print("ℹ️  Some user behavior models not available")

# 8. Search query mapping
try:
    from app.models.search_query_mapping import SearchQueryMapping
    print("✅ SearchQueryMapping model loaded")
except ImportError:
    print("ℹ️  SearchQueryMapping model not available")

# 9. Search mappings/logs
try:
    from app.models.search_mapping import SearchMapping, SearchMappingType
    from app.models.search_log import SearchLog
    print("✅ SearchMapping/SearchLog model loaded")
except ImportError:
    print("ℹ️  SearchMapping/SearchLog model not available")

# 10. Loyalty
try:
    from app.models.loyalty import LoyaltyTier
    print("✅ LoyaltyTier model loaded")
except ImportError:
    print("ℹ️  LoyaltyTier model not available")

# 11. Notification
try:
    from app.models.notification import Notification
    print("✅ Notification model loaded")
except ImportError:
    print("ℹ️  Notification model not available")

# ========== TẠO DANH SÁCH ==========
__all__ = [
    "SeoCluster",
    "Category",
    "Product",
    "ProductQuestion",
    "ProductQuestionUsefulVote",
    "ProductReview",
    "ProductReviewUsefulVote",
    "User",
    "UserTrustedDevice",
    "EmailLoginChallenge",
    "EmailTrustedDevice",
    "UserPushSubscription",
    "UserAddress",
    "UserProductView",
    "UserFavorite",
    "GuestProductView",
    "GuestFavorite",
    "GuestSearchHistory",
    "AnalyticsEvent",
    "Cart",           
    "CartItem",
    "Order",
    "OrderItem", 
    "Payment",
    "BankAccount",
    "SiteEmbedCode",
    "CategorySeoMapping",
    "CategorySeoDictionary",
    "CategorySeoMeta",
    "CategoryTransformRule",
    "CategoryFinalMapping",
    "SearchQueryMapping",
    "SearchMapping",
    "SearchMappingType",
    "SearchLog",
    "LoyaltyTier",
    "Notification",
]

# Thêm các models user behavior
try:
    __all__.extend(["UserCategoryView", "UserBrandView", "UserSearchHistory", "UserShopInteraction"])
except:
    pass

# Thêm Admin và AdminRole (luôn export để models.AdminRole tồn tại)
__all__.append("AdminUser")
__all__.append("AdminRole")

print(f"📦 Total models loaded: {len(__all__)}")
print(f"   Models: {', '.join(sorted(__all__))}")
