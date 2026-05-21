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
print("[OK] SeoCluster model loaded")

# 1b. Import Category (phụ thuộc SeoCluster qua seo_cluster_id)
from app.models.category import Category
print("[OK] Category model loaded")

# 2. Import Product (phụ thuộc Category)
from app.models.product import Product
print("[OK] Product model loaded")

from app.models.internal_sku_export import InternalSkuExport
print("[OK] InternalSkuExport model loaded")

from app.models.product_import_draft import ProductImportDraft
print("[OK] ProductImportDraft model loaded")

from app.models.image_localization_job import ImageLocalizationJob
print("[OK] ImageLocalizationJob model loaded")

from app.models.listing_import_queue_snapshot import ListingImportQueueRevocation, ListingImportQueueSnapshot
print("[OK] ListingImportQueueSnapshot model loaded")

# 3. Import User (không phụ thuộc)
from app.models.user import User, UserProductView, UserFavorite
print("[OK] User models loaded")

from app.models.guest_behavior import GuestProductView, GuestFavorite, GuestSearchHistory
print("[OK] Guest behavior models loaded")

from app.models.user_trusted_device import UserTrustedDevice
print("[OK] UserTrustedDevice model loaded")
from app.models.email_login_challenge import EmailLoginChallenge
from app.models.email_trusted_device import EmailTrustedDevice
print("[OK] Email login challenge / trusted device models loaded")
from app.models.birthday_promo import BirthdayPromoEmailLog
print("[OK] BirthdayPromoEmailLog model loaded")
from app.models.admin_feature_test import AdminFeatureTestSetting
print("[OK] AdminFeatureTestSetting model loaded")
from app.models.push_subscription import UserPushSubscription
print("[OK] UserPushSubscription model loaded")

# 3a. Analytics events (phụ thuộc User)
from app.models.analytics_event import AnalyticsEvent
print("[OK] AnalyticsEvent model loaded")

# 3b. Import UserAddress (phụ thuộc User)
from app.models.address import UserAddress
print("[OK] UserAddress model loaded")

# 4. Import Cart models
from app.models.cart import Cart, CartItem
print("[OK] Cart models loaded")

# 5. Import Admin (nếu có)
try:
    from app.models.admin import AdminUser, AdminRole, AdminStaffRolePreset
    print("[OK] AdminUser model loaded")
except ImportError:
    AdminUser = None  # type: ignore[misc, assignment]
    AdminRole = None
    print("[INFO] AdminUser model not available")

# 6. Import Order models (phụ thuộc User, Product)
from app.models.order import Order, OrderItem, Payment
print("[OK] Order models loaded")

# 6b. Bank accounts (cài đặt quản trị)
from app.models.bank_account import BankAccount
print("[OK] BankAccount model loaded")

# 6b2. Mã nhúng site (GA, Facebook, Zalo…)
from app.models.site_embed_code import SiteEmbedCode
print("[OK] SiteEmbedCode model loaded")

# 6b3. Vị trí nút nổi lướt video shop (singleton)
from app.models.shop_video_fab_setting import ShopVideoFabSetting
print("[OK] ShopVideoFabSetting model loaded")

# 6c. Product questions (câu hỏi câu trả lời sản phẩm)
from app.models.product_question import ProductQuestion, ProductQuestionUsefulVote
print("[OK] ProductQuestion model loaded")

# 6d. Product reviews (đánh giá sản phẩm - chỉ admin trả lời)
from app.models.product_review import ProductReview, ProductReviewUsefulVote
print("[OK] ProductReview model loaded")

# 6e. Category SEO mapping (quản lý canonical/redirect cho danh mục)
from app.models.category_seo import CategorySeoMapping, CategorySeoDictionary, CategorySeoMeta, CategorySeoGeminiTarget, CategorySeoSettings
print("[OK] CategorySeoMapping model loaded")

# 6f. Category transform rules (lưu lịch sử chỉnh danh mục)
from app.models.category_transform_rule import CategoryTransformRule
print("[OK] CategoryTransformRule model loaded")

# 6g. Category final mapping (đầu -> cuối)
from app.models.category_final_mapping import CategoryFinalMapping
print("[OK] CategoryFinalMapping model loaded")

# 7. Import các models user behavior còn lại
try:
    from app.models.user import UserCategoryView, UserBrandView, UserSearchHistory, UserShopInteraction
    print("[OK] User behavior models loaded")
except ImportError:
    print("[INFO] Some user behavior models not available")

# 8. Search query mapping
try:
    from app.models.search_query_mapping import SearchQueryMapping
    print("[OK] SearchQueryMapping model loaded")
except ImportError:
    print("[INFO] SearchQueryMapping model not available")

from app.models.product_search_cache import ProductSearchCache
print("[OK] ProductSearchCache model loaded")

# 9. Search mappings/logs
try:
    from app.models.search_mapping import SearchMapping, SearchMappingType
    from app.models.search_log import SearchLog
    print("[OK] SearchMapping/SearchLog model loaded")
except ImportError:
    print("[INFO] SearchMapping/SearchLog model not available")

# 10. Loyalty
try:
    from app.models.loyalty import LoyaltyTier
    print("[OK] LoyaltyTier model loaded")
except ImportError:
    print("[INFO] LoyaltyTier model not available")

# 10b. Affiliate / Wallet
try:
    from app.models.affiliate import (
        AffiliateApplication,
        AffiliateBankAccountOtp,
        AffiliateCommission,
        AffiliateProfile,
        AffiliateSettings,
        UserBankAccount,
        UserWallet,
        WalletTransaction,
        WalletWithdrawal,
    )
    print("[OK] Affiliate/Wallet models loaded")
except ImportError:
    print("[INFO] Affiliate/Wallet models not available")

# 11. Notification
try:
    from app.models.notification import Notification
    print("[OK] Notification model loaded")
except ImportError:
    print("[INFO] Notification model not available")

# ========== TẠO DANH SÁCH ==========
__all__ = [
    "SeoCluster",
    "Category",
    "Product",
    "InternalSkuExport",
    "ProductImportDraft",
    "ImageLocalizationJob",
    "ListingImportQueueSnapshot",
    "ListingImportQueueRevocation",
    "ProductQuestion",
    "ProductQuestionUsefulVote",
    "ProductReview",
    "ProductReviewUsefulVote",
    "User",
    "UserTrustedDevice",
    "EmailLoginChallenge",
    "EmailTrustedDevice",
    "BirthdayPromoEmailLog",
    "AdminFeatureTestSetting",
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
    "ShopVideoFabSetting",
    "CategorySeoMapping",
    "CategorySeoDictionary",
    "CategorySeoMeta",
    "CategorySeoGeminiTarget",
    "CategorySeoSettings",
    "CategoryTransformRule",
    "CategoryFinalMapping",
    "SearchQueryMapping",
    "ProductSearchCache",
    "SearchMapping",
    "SearchMappingType",
    "SearchLog",
    "LoyaltyTier",
    "AffiliateSettings",
    "AffiliateApplication",
    "AffiliateBankAccountOtp",
    "AffiliateProfile",
    "UserWallet",
    "WalletTransaction",
    "AffiliateCommission",
    "UserBankAccount",
    "WalletWithdrawal",
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

print(f"[INFO] Total models loaded: {len(__all__)}")
print(f"   Models: {', '.join(sorted(__all__))}")
