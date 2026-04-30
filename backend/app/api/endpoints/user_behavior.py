# backend/app/api/endpoints/user_behavior.py - COMPLETE VERSION
import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Response
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User
from app.core.security import get_current_user, get_current_user_optional
from app.schemas.user import (
    ProductViewCreate, ProductViewResponse, FavoriteCreate, 
    FavoriteResponse, CategoryViewCreate, CategoryViewResponse,
    BrandViewCreate, BrandViewResponse, SearchHistoryCreate,
    SearchHistoryResponse, ShopInteractionCreate, ShopInteractionResponse,
    UserBehaviorStats
)
from app.crud import guest_behavior as guest_behavior_crud
from app.crud.personalized_feed import get_personalized_home_products
from app.schemas.product import Product as ProductSchema
from app.crud.user import (
    add_product_view_with_data, get_user_viewed_products,
    get_products_viewed_by_same_age_gender, get_products_same_shop_as_recent_views,
    add_favorite_product_with_data, remove_favorite_product,
    get_user_favorites, is_product_favorited,
    add_category_view_with_name, get_user_viewed_categories,
    add_brand_view, get_user_viewed_brands,
    add_search_history, get_user_search_history, clear_search_history, get_search_suggestions,
    add_shop_interaction, get_user_shop_interactions,
    get_user_shop_interactions_by_type, get_user_behavior_stats
)

router = APIRouter()

# Product Views
@router.post("/products/view", response_model=dict)
def track_product_view(
    view_data: ProductViewCreate,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
    x_guest_session_id: Optional[str] = Header(None, alias="X-Guest-Session-Id"),
):
    """Theo dõi sản phẩm đã xem với dữ liệu chi tiết (đăng nhập hoặc phiên khách)."""
    if current_user:
        add_product_view_with_data(db, current_user.id, view_data)
        return {"message": "Đã lưu lịch sử xem sản phẩm"}
    sid = (x_guest_session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="Cần đăng nhập hoặc gửi header X-Guest-Session-Id")
    guest_behavior_crud.add_guest_product_view(db, sid, view_data)
    return {"message": "Đã lưu lịch sử xem sản phẩm (phiên khách)"}

@router.get("/products/viewed", response_model=list[ProductViewResponse])
def get_viewed_products(
    limit: int = 20,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
    x_guest_session_id: Optional[str] = Header(None, alias="X-Guest-Session-Id"),
):
    """Lấy danh sách sản phẩm đã xem"""
    if current_user:
        return get_user_viewed_products(db, current_user.id, limit)
    sid = (x_guest_session_id or "").strip()
    if not sid:
        return []
    rows = guest_behavior_crud.get_guest_viewed_products(db, sid, limit)
    return [
        ProductViewResponse(
            id=r.id,
            user_id=None,
            product_id=r.product_id,
            product_data=r.product_data,
            time_spent_seconds=r.time_spent_seconds or 0,
            viewed_at=r.viewed_at,
        )
        for r in rows
    ]


@router.get("/products/viewed-by-same-age-gender", response_model=dict)
def get_products_viewed_by_same_age_gender_endpoint(
    limit: int = 24,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Sản phẩm mà khách cùng tuổi (cùng năm sinh) và cùng giới tính đã xem.
    Nếu chưa đăng nhập hoặc user chưa có tuổi/giới tính thì trả về danh sách rỗng.
    """
    if not current_user:
        return {"products": []}
    products = get_products_viewed_by_same_age_gender(db, current_user.id, limit=limit)
    products_list = []
    for p in products:
        if hasattr(p, "__dict__"):
            d = {k: v for k, v in p.__dict__.items() if not k.startswith("_")}
            products_list.append(d)
        else:
            products_list.append(p)
    return {"products": products_list}


@router.get("/products/same-shop-as-recent-views", response_model=dict)
def get_products_same_shop_as_recent_views_endpoint(
    limit: int = 60,
    offset: int = 0,
    seed: Optional[int] = None,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
    x_guest_session_id: Optional[str] = Header(None, alias="X-Guest-Session-Id"),
):
    """
    Sản phẩm cùng shop_name với 8 sản phẩm khách xem gần nhất.
    Phân trang: limit (mặc định 60), offset, seed (từ lần gọi đầu để load thêm giữ thứ tự).
    Trả về: { products, total, seed }.
    Khách: cần header X-Guest-Session-Id và đã xem sản phẩm trong phiên.
    """
    sid = (x_guest_session_id or "").strip()
    if current_user:
        products, total, returned_seed = get_products_same_shop_as_recent_views(
            db, user_id=current_user.id, limit=limit, offset=offset, seed=seed
        )
    elif sid:
        products, total, returned_seed = get_products_same_shop_as_recent_views(
            db,
            user_id=None,
            limit=limit,
            offset=offset,
            seed=seed,
            guest_session_id=sid,
        )
    else:
        return {"products": [], "total": 0, "seed": None}
    products_list = []
    for p in products:
        if hasattr(p, "__dict__"):
            d = {k: v for k, v in p.__dict__.items() if not k.startswith("_")}
            products_list.append(d)
        else:
            products_list.append(p)
    return {"products": products_list, "total": total, "seed": returned_seed}


@router.get("/products/home-feed", response_model=dict)
def get_home_feed_products(
    response: Response,
    skip: int = 0,
    limit: int = 48,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
    x_guest_session_id: Optional[str] = Header(None, alias="X-Guest-Session-Id"),
):
    """
    Danh sách trang chủ (không lọc): ưu tiên danh mục / shop trùng với sản phẩm đã xem & đã thích.
    Khách: header X-Guest-Session-Id (frontend luôn gửi). Không tín hiệu → sắp xếp theo purchases.
    """
    response.headers["Cache-Control"] = "private, no-store"
    lim = max(1, min(limit, 100))
    sk = max(0, skip)
    uid = current_user.id if current_user else None
    sid = None if uid else (x_guest_session_id or "").strip() or None

    products, total, personalized = get_personalized_home_products(
        db,
        user_id=uid,
        guest_session_id=sid,
        skip=sk,
        limit=lim,
    )
    products_list = []
    for product in products:
        try:
            products_list.append(ProductSchema.model_validate(product).model_dump())
        except Exception:
            products_list.append(product)

    total_pages = math.ceil(total / lim) if lim > 0 else 1
    page = sk // lim + 1 if lim > 0 else 1
    return {
        "products": products_list,
        "total": total,
        "page": page,
        "size": lim,
        "total_pages": total_pages,
        "personalized": personalized,
    }


# Favorites
@router.post("/products/favorite", response_model=FavoriteResponse)
def add_to_favorites(
    favorite_data: FavoriteCreate,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
    x_guest_session_id: Optional[str] = Header(None, alias="X-Guest-Session-Id"),
):
    """Thêm sản phẩm vào danh sách yêu thích với dữ liệu sản phẩm"""
    if current_user:
        return add_favorite_product_with_data(db, current_user.id, favorite_data)
    sid = (x_guest_session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="Cần đăng nhập hoặc gửi header X-Guest-Session-Id")
    r = guest_behavior_crud.add_guest_favorite(db, sid, favorite_data)
    return FavoriteResponse(
        id=r.id,
        user_id=None,
        product_id=r.product_id,
        product_data=r.product_data,
        created_at=r.created_at,
    )

@router.delete("/products/favorite/{product_id}")
def remove_from_favorites(
    product_id: int,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
    x_guest_session_id: Optional[str] = Header(None, alias="X-Guest-Session-Id"),
):
    """Xóa sản phẩm khỏi danh sách yêu thích"""
    if current_user:
        success = remove_favorite_product(db, current_user.id, product_id)
        if not success:
            raise HTTPException(status_code=404, detail="Sản phẩm không có trong danh sách yêu thích")
        return {"message": "Đã xóa khỏi danh sách yêu thích"}
    sid = (x_guest_session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="Cần đăng nhập hoặc gửi header X-Guest-Session-Id")
    if not guest_behavior_crud.remove_guest_favorite(db, sid, product_id):
        raise HTTPException(status_code=404, detail="Sản phẩm không có trong danh sách yêu thích")
    return {"message": "Đã xóa khỏi danh sách yêu thích"}

@router.get("/products/favorites", response_model=list[FavoriteResponse])
def get_favorite_products(
    limit: int = 50,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
    x_guest_session_id: Optional[str] = Header(None, alias="X-Guest-Session-Id"),
):
    """Lấy danh sách sản phẩm yêu thích"""
    if current_user:
        return get_user_favorites(db, current_user.id, limit)
    sid = (x_guest_session_id or "").strip()
    if not sid:
        return []
    rows = guest_behavior_crud.get_guest_favorites(db, sid, limit)
    return [
        FavoriteResponse(
            id=r.id,
            user_id=None,
            product_id=r.product_id,
            product_data=r.product_data,
            created_at=r.created_at,
        )
        for r in rows
    ]

@router.get("/products/{product_id}/is-favorited")
def check_product_favorited(
    product_id: int,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
    x_guest_session_id: Optional[str] = Header(None, alias="X-Guest-Session-Id"),
):
    """Kiểm tra sản phẩm có trong danh sách yêu thích không"""
    if current_user:
        return {"is_favorited": is_product_favorited(db, current_user.id, product_id)}
    sid = (x_guest_session_id or "").strip()
    if not sid:
        return {"is_favorited": False}
    return {"is_favorited": guest_behavior_crud.is_guest_product_favorited(db, sid, product_id)}

# Category Views
@router.post("/categories/view", response_model=dict)
def track_category_view(
    category_data: CategoryViewCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Theo dõi danh mục đã xem"""
    add_category_view_with_name(db, current_user.id, category_data)
    return {"message": "Đã lưu lịch sử xem danh mục"}

@router.get("/categories/viewed", response_model=list[CategoryViewResponse])
def get_viewed_categories(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lấy danh sách danh mục đã xem"""
    return get_user_viewed_categories(db, current_user.id, limit)

# Brand Views
@router.post("/brands/view", response_model=dict)
def track_brand_view(
    brand_data: BrandViewCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Theo dõi thương hiệu đã xem"""
    add_brand_view(db, current_user.id, brand_data.brand_name)
    return {"message": "Đã lưu lịch sử xem thương hiệu"}

@router.get("/brands/viewed", response_model=list[BrandViewResponse])
def get_viewed_brands(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lấy danh sách thương hiệu đã xem"""
    return get_user_viewed_brands(db, current_user.id, limit)

# Search History
@router.post("/search/history", response_model=SearchHistoryResponse)
def add_search(
    search_data: SearchHistoryCreate,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
    x_guest_session_id: Optional[str] = Header(None, alias="X-Guest-Session-Id"),
):
    """Lưu lịch sử tìm kiếm"""
    if current_user:
        return add_search_history(db, current_user.id, search_data)
    sid = (x_guest_session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="Cần đăng nhập hoặc gửi header X-Guest-Session-Id")
    r = guest_behavior_crud.add_guest_search_history(db, sid, search_data)
    return SearchHistoryResponse(
        id=r.id,
        user_id=None,
        search_query=r.search_query,
        search_filters=r.search_filters,
        search_results_count=r.search_results_count or 0,
        searched_at=r.searched_at,
    )

@router.get("/search/history", response_model=list[SearchHistoryResponse])
def get_search_history(
    limit: int = 20,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
    x_guest_session_id: Optional[str] = Header(None, alias="X-Guest-Session-Id"),
):
    """Lấy lịch sử tìm kiếm"""
    if current_user:
        return get_user_search_history(db, current_user.id, limit)
    sid = (x_guest_session_id or "").strip()
    if not sid:
        return []
    rows = guest_behavior_crud.get_guest_search_history(db, sid, limit)
    return [
        SearchHistoryResponse(
            id=r.id,
            user_id=None,
            search_query=r.search_query,
            search_filters=r.search_filters,
            search_results_count=r.search_results_count or 0,
            searched_at=r.searched_at,
        )
        for r in rows
    ]

@router.delete("/search/history")
def clear_user_search_history(
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
    x_guest_session_id: Optional[str] = Header(None, alias="X-Guest-Session-Id"),
):
    """Xóa lịch sử tìm kiếm"""
    if current_user:
        clear_search_history(db, current_user.id)
        return {"message": "Đã xóa lịch sử tìm kiếm"}
    sid = (x_guest_session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="Cần đăng nhập hoặc gửi header X-Guest-Session-Id")
    guest_behavior_crud.clear_guest_search_history(db, sid)
    return {"message": "Đã xóa lịch sử tìm kiếm"}


@router.get("/search/suggestions")
def get_search_suggestions_endpoint(
    limit: int = 12,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
    x_guest_session_id: Optional[str] = Header(None, alias="X-Guest-Session-Id"),
):
    """
    Gợi ý từ khóa: 3 đầu = tìm kiếm gần đây của user, còn lại = tìm kiếm của khách cùng giới tính + năm sinh.
    Khách (có X-Guest-Session-Id): 3 đầu lấy từ lịch sử phiên khách.
    Nếu chưa đăng nhập hoặc không có gender/birth: trả về popular từ tất cả.
    """
    user_id = current_user.id if current_user else None
    gender = getattr(current_user, "gender", None) if current_user else None
    birth_year = None
    if current_user and hasattr(current_user, "date_of_birth") and current_user.date_of_birth:
        birth_year = current_user.date_of_birth.year
    guest_sid = None if current_user else (x_guest_session_id or "").strip() or None
    terms = get_search_suggestions(
        db,
        user_id=user_id,
        gender=gender,
        birth_year=birth_year,
        limit=limit,
        guest_session_id=guest_sid,
    )
    return {"suggestions": terms}


@router.post("/session/merge", response_model=dict)
def merge_guest_behavior_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_guest_session_id: Optional[str] = Header(None, alias="X-Guest-Session-Id"),
):
    """Sau đăng nhập: gộp hành vi đã lưu theo phiên khách vào tài khoản."""
    sid = (x_guest_session_id or "").strip()
    if not sid:
        return {"message": "Không có phiên khách", "merged_views": 0, "merged_favorites": 0, "merged_searches": 0}
    stats = guest_behavior_crud.merge_guest_session_to_user(db, current_user.id, sid)
    return {"message": "Đã gộp hành vi phiên khách", **stats}


# Shop Interactions
@router.post("/shop/interaction", response_model=ShopInteractionResponse)
def track_shop_interaction(
    interaction_data: ShopInteractionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Theo dõi tương tác với shop"""
    return add_shop_interaction(db, current_user.id, interaction_data)

@router.get("/shop/interactions", response_model=list[ShopInteractionResponse])
def get_shop_interactions(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lấy lịch sử tương tác với shop"""
    return get_user_shop_interactions(db, current_user.id, limit)

@router.get("/shop/interactions/{interaction_type}", response_model=list[ShopInteractionResponse])
def get_shop_interactions_by_type(
    interaction_type: str,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lấy tương tác với shop theo loại"""
    return get_user_shop_interactions_by_type(db, current_user.id, interaction_type, limit)

# Behavior Stats
@router.get("/behavior/stats", response_model=UserBehaviorStats)
def get_behavior_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lấy thống kê hành vi người dùng đầy đủ"""
    return get_user_behavior_stats(db, current_user.id)