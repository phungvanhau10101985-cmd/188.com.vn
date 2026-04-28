"""
backend/app/crud/__init__.py - CRUD module exports
File này BẮT BUỘC để import module crud hoạt động đúng
"""

import os
import sys

print(f"📦 Loading CRUD module from: {os.path.dirname(__file__)}")

# ========== IMPORT USER MODULE ==========
try:
    from .user import (
        # Core user functions
        get_user, get_user_by_phone, get_user_by_email, get_user_by_id,
        create_user, update_user, verify_user, update_last_login,
        get_users, delete_user, get_user_count, search_users,
        
        # User behavior functions
        add_product_view_with_data, get_user_viewed_products,
        add_favorite_product_with_data, remove_favorite_product,
        get_user_favorites, is_product_favorited,
        add_category_view_with_name, get_user_viewed_categories,
        add_brand_view, get_user_viewed_brands,
        add_search_history, get_user_search_history, clear_search_history, get_search_suggestions,
        add_shop_interaction, get_user_shop_interactions,
        get_user_shop_interactions_by_type, get_user_behavior_stats
    )
    print("  ✅ User CRUD: Loaded successfully")
except ImportError as e:
    print(f"  ❌ User CRUD: Import error - {e}")
    # Tạo placeholder functions để tránh crash
    def get_user(*args, **kwargs):
        raise NotImplementedError("User module not loaded")
    get_user_by_phone = get_user_by_email = get_user_by_id = get_user
    create_user = update_user = verify_user = update_last_login = get_user
    get_users = delete_user = get_user_count = search_users = get_user
    add_product_view_with_data = get_user_viewed_products = get_user
    add_favorite_product_with_data = remove_favorite_product = get_user
    get_user_favorites = is_product_favorited = get_user
    add_category_view_with_name = get_user_viewed_categories = get_user
    add_brand_view = get_user_viewed_brands = get_user
    add_search_history = get_user_search_history = clear_search_history = get_search_suggestions = get_user
    add_shop_interaction = get_user_shop_interactions = get_user
    get_user_shop_interactions_by_type = get_user_behavior_stats = get_user

# ========== IMPORT CATEGORY MODULE ==========
try:
    from .category import (
        get_category, get_category_by_slug, get_categories,
        create_category, update_category, delete_category,
        get_category_products, get_category_count
    )
    print("  ✅ Category CRUD: Loaded successfully")
except ImportError:
    print("  ⚠️  Category CRUD: Module not found (may be normal)")
    # Placeholder functions
    def get_category(*args, **kwargs):
        raise NotImplementedError("Category module not loaded")
    get_category_by_slug = get_categories = get_category
    create_category = update_category = delete_category = get_category
    get_category_products = get_category_count = get_category

# ========== IMPORT PRODUCT MODULE ==========
try:
    from .product import (
        get_product, get_product_by_slug, get_products,
        create_product, update_product, delete_product,
        search_products, filter_products, get_product_count,
        get_products_by_category, get_products_by_ids
    )
    print("  ✅ Product CRUD: Loaded successfully")
except ImportError:
    print("  ⚠️  Product CRUD: Module not found (may be normal)")
    def get_product(*args, **kwargs):
        raise NotImplementedError("Product module not loaded")
    get_product_by_slug = get_products = get_product
    create_product = update_product = delete_product = get_product
    search_products = filter_products = get_product_count = get_product
    get_products_by_category = get_products_by_ids = get_product

# ========== IMPORT CART MODULE ==========
try:
    from .cart import (
        get_cart, get_cart_items, add_cart_item,
        update_cart_item, remove_cart_item, clear_cart,
        get_cart_item_count, migrate_guest_cart
    )
    print("  ✅ Cart CRUD: Loaded successfully")
except ImportError:
    print("  ⚠️  Cart CRUD: Module not found (may be normal)")
    def get_cart(*args, **kwargs):
        raise NotImplementedError("Cart module not loaded")
    get_cart_items = add_cart_item = update_cart_item = get_cart
    remove_cart_item = clear_cart = get_cart_item_count = get_cart
    migrate_guest_cart = get_cart

# ========== IMPORT ORDER MODULE ==========
try:
    from .order import (
        create_order, get_orders, get_order,
        update_order_status, cancel_order, confirm_received, update_order_deposit_type, pay_deposit,
        get_user_orders, get_order_count
    )
    print("  ✅ Order CRUD: Loaded successfully")
except ImportError:
    print("  ⚠️  Order CRUD: Module not found (may be normal)")
    def create_order(*args, **kwargs):
        raise NotImplementedError("Order module not loaded")
    get_orders = get_order = update_order_status = create_order
    cancel_order = confirm_received = update_order_deposit_type = pay_deposit = get_user_orders = get_order_count = create_order

# ========== SUBMODULES (for crud.address, crud.bank_account) ==========
from . import address
from . import bank_account
from . import payment

# ========== PRODUCT QUESTION MODULE ==========
try:
    from . import product_question
    from .product_question import (
        get_question,
        get_questions,
        get_questions_count,
        create_question,
        update_question,
        delete_question,
        get_questions_for_product,
        create_customer_question,
    )
    print("  ✅ ProductQuestion CRUD: Loaded successfully")
except ImportError as e:
    print(f"  ⚠️  ProductQuestion CRUD: Import failed - {e}")
    def get_question(*args, **kwargs):
        raise NotImplementedError("ProductQuestion module not loaded")
    get_questions = get_questions_count = create_question = get_question
    update_question = delete_question = get_questions_for_product = get_question
    create_customer_question = get_question

# ========== PRODUCT REVIEW MODULE ==========
try:
    from . import product_review
    print("  ✅ ProductReview CRUD: Loaded successfully")
except ImportError as e:
    print(f"  ⚠️  ProductReview CRUD: Import failed - {e}")
    product_review = None

# ========== IMPORT ADMIN MODULE ==========
try:
    from .admin import (
        get_admin, get_admin_by_username, create_admin,
        update_admin, delete_admin, get_admins,
        verify_admin_password, update_admin_last_login
    )
    print("  ✅ Admin CRUD: Loaded successfully")
except ImportError as e:
    print(f"  ⚠️  Admin CRUD: Import failed - {e}")
    def get_admin(*args, **kwargs):
        raise NotImplementedError("Admin module not loaded")
    get_admin_by_username = create_admin = update_admin = get_admin
    delete_admin = get_admins = verify_admin_password = get_admin
    update_admin_last_login = get_admin

# ========== EXPORT EVERYTHING ==========
print("✅ CRUD module initialization complete")

# Export để có thể import từ app.crud
__all__ = [
    # Modules
    'user', 'category', 'product', 'cart', 'order', 'admin', 'product_question', 'product_review',
    
    # User functions
    'get_user', 'get_user_by_phone', 'get_user_by_email', 'get_user_by_id',
    'create_user', 'update_user', 'verify_user', 'update_last_login',
    'get_users', 'delete_user', 'get_user_count', 'search_users',
    'add_product_view_with_data', 'get_user_viewed_products',
    'add_favorite_product_with_data', 'remove_favorite_product',
    'get_user_favorites', 'is_product_favorited',
    'add_category_view_with_name', 'get_user_viewed_categories',
    'add_brand_view', 'get_user_viewed_brands',
    'add_search_history', 'get_user_search_history', 'clear_search_history',
    'add_shop_interaction', 'get_user_shop_interactions',
    'get_user_shop_interactions_by_type', 'get_user_behavior_stats',
    
    # Category functions
    'get_category', 'get_category_by_slug', 'get_categories',
    'create_category', 'update_category', 'delete_category',
    'get_category_products', 'get_category_count',
    
    # Product functions
    'get_product', 'get_product_by_slug', 'get_products',
    'create_product', 'update_product', 'delete_product',
    'search_products', 'filter_products', 'get_product_count',
    'get_products_by_category', 'get_products_by_ids',
    
    # Cart functions
    'get_cart', 'get_cart_items', 'add_cart_item',
    'update_cart_item', 'remove_cart_item', 'clear_cart',
    'get_cart_item_count', 'migrate_guest_cart',
    
    # Order functions
    'create_order', 'get_orders', 'get_order',
    'update_order_status',     'cancel_order', 'confirm_received', 'update_order_deposit_type', 'pay_deposit',
    'get_user_orders', 'get_order_count',
    
    # Admin functions
    'get_admin', 'get_admin_by_username', 'create_admin',
    'update_admin', 'delete_admin', 'get_admins',
    'verify_admin_password', 'update_admin_last_login',

    # ProductQuestion functions
    'get_question', 'get_questions', 'get_questions_count',
    'create_question', 'update_question', 'delete_question',
    'get_questions_for_product', 'create_customer_question',
]