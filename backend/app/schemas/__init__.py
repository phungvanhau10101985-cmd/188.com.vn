# backend/app/schemas/__init__.py
# ============================================
# ORGANIZED SCHEMA EXPORTS FOR EASY IMPORTING
# ============================================

# --- Cart Schemas ---
from .cart import (
    BulkCartUpdate,
    CartItemBase,
    CartItemCreate,
    CartItemResponse,
    CartItemUpdate,
    CartMergeResponse,
    CartResponse,
    GuestCartItem,
    GuestCartMigration,
)

# --- Category Schemas ---
from .category import (
    Category,
    CategoryBase,
    CategoryCreate,
    CategoryInDBBase,
    CategoryUpdate,
    CategoryWithProducts,
)

# --- Order Schemas ---
from .order import (
    AdminOrderResponse,
    AdminOrderStats,
    DepositType,
    DepositType,
    OrderCreate,
    OrderItemCreate,
    OrderItemResponse,
    OrderResponse,
    OrderStatus,
    OrderStatus,
    OrderUpdate,
    PaymentConfirm,
    PaymentCreate,
    PaymentMethod,
    PaymentMethod,
    PaymentResponse,
    PaymentStatus,
    PaymentStatus,
    SepayDepositInfoResponse,
)

# --- Product Schemas ---
from .product import (
    Product,
    ProductBase,
    ProductCreate,
    ProductExportRequest,
    ProductImportRequest,
    ProductUpdate,
)

# --- Address Schemas ---
from .address import AddressCreate, AddressUpdate, AddressResponse

# --- Bank Account Schemas ---
from .bank_account import BankAccountCreate, BankAccountUpdate, BankAccountResponse

# --- Product Question Schemas ---
from .product_question import (
    ProductQuestionBase,
    ProductQuestionCreate,
    ProductQuestionUpdate,
    ProductQuestionResponse,
    ProductQuestionListResponse,
    ProductQuestionAskCreate,
)

# --- User Schemas ---
from .user import (
    BrandViewCreate,
    BrandViewResponse,
    CategoryViewCreate,
    CategoryViewResponse,
    DateOfBirthResponse,
    FavoriteCreate,
    FavoriteResponse,
    Gender,
    Gender,
    InteractionType,
    InteractionType,
    ProductViewCreate,
    ProductViewResponse,
    SearchHistoryCreate,
    SearchHistoryResponse,
    ShopInteractionCreate,
    ShopInteractionResponse,
    Token,
    UserBehaviorStats,
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
)

# --- Notification Schemas ---
from .notification import (
    NotificationBase,
    NotificationCreate,
    NotificationUpdate,
    NotificationResponse,
    NotificationImportRow,
    NotificationImportResponse,
)

# --- Re-export for backward compatibility ---
__all__ = [
    # Cart
    "BulkCartUpdate",
    "CartItemBase",
    "CartItemCreate",
    "CartItemResponse",
    "CartItemUpdate",
    "CartMergeResponse",
    "CartResponse",
    "GuestCartItem",
    "GuestCartMigration",

    # Category
    "Category",
    "CategoryBase",
    "CategoryCreate",
    "CategoryInDBBase",
    "CategoryUpdate",
    "CategoryWithProducts",

    # Order
    "AdminOrderResponse",
    "AdminOrderStats",
    "DepositType",
    "DepositType",
    "OrderCreate",
    "OrderItemCreate",
    "OrderItemResponse",
    "OrderResponse",
    "OrderStatus",
    "OrderStatus",
    "OrderUpdate",
    "PaymentConfirm",
    "PaymentCreate",
    "PaymentMethod",
    "PaymentMethod",
    "PaymentResponse",
    "PaymentStatus",
    "PaymentStatus",
    "SepayDepositInfoResponse",

    # Address
    "AddressCreate",
    "AddressUpdate",
    "AddressResponse",
    # BankAccount
    "BankAccountCreate",
    "BankAccountUpdate",
    "BankAccountResponse",
    # Product
    "Product",
    "ProductBase",
    "ProductCreate",
    "ProductExportRequest",
    "ProductImportRequest",
    "ProductUpdate",

    # ProductQuestion
    "ProductQuestionBase",
    "ProductQuestionCreate",
    "ProductQuestionUpdate",
    "ProductQuestionResponse",
    "ProductQuestionListResponse",
    "ProductQuestionAskCreate",

    # User
    "BrandViewCreate",
    "BrandViewResponse",
    "CategoryViewCreate",
    "CategoryViewResponse",
    "DateOfBirthResponse",
    "FavoriteCreate",
    "FavoriteResponse",
    "Gender",
    "Gender",
    "InteractionType",
    "InteractionType",
    "ProductViewCreate",
    "ProductViewResponse",
    "SearchHistoryCreate",
    "SearchHistoryResponse",
    "ShopInteractionCreate",
    "ShopInteractionResponse",
    "Token",
    "UserBehaviorStats",
    "UserCreate",
    "UserLogin",
    "UserResponse",
    "UserUpdate",

    # Notification
    "NotificationBase",
    "NotificationCreate",
    "NotificationUpdate",
    "NotificationResponse",
    "NotificationImportRow",
    "NotificationImportResponse",
]
