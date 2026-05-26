#!/usr/bin/env python3
"""
backend/app/crud/user.py - FIXED VERSION
ĐÃ THÊM HÀM get_user() để fix lỗi: 
AttributeError: module 'app.crud.user' has no attribute 'get_user'
"""

import random
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import extract, func, or_
from datetime import datetime, date
from typing import List, Optional, Dict, Any, Tuple
from app.models.user import (
    User, UserProductView, UserFavorite, UserCategoryView,
    UserBrandView, UserSearchHistory, UserShopInteraction
)
from app.models.product import Product
from app.core.email_identity import identity_email
from app.utils.video_link import is_playable_product_video_link
from app.schemas.user import (
    UserCreate, UserUpdate, UserAdminUpdate, ProductViewCreate, FavoriteCreate,
    CategoryViewCreate, BrandViewCreate, SearchHistoryCreate, ShopInteractionCreate
)

print("✅ Loading user CRUD module...")

# ==============================
# CORE USER CRUD FUNCTIONS - UPDATED
# ==============================

# ========== FIX: ADD MISSING FUNCTION ==========
def get_user(db: Session, user_id: int) -> Optional[User]:
    """
    Lấy user bằng ID - FIX FOR security.py
    
    Hàm này BẮT BUỘC để security.py hoạt động đúng
    Args:
        db: Database session
        user_id: ID của user
    Returns:
        User object hoặc None
    """
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_phone(db: Session, phone: str) -> Optional[User]:
    """Lấy user bằng số điện thoại"""
    return db.query(User).filter(User.phone == phone).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Lấy user bằng email (Gmail/OTP/Google trùng một tài khoản: identity_email)."""
    if not (email or "").strip():
        return None
    key = identity_email(email)
    if not key:
        return None
    u = db.query(User).filter(User.email == key).first()
    if u:
        return u
    u = db.query(User).filter(func.lower(User.email) == key.lower()).first()
    if u:
        return u
    if key.endswith("@gmail.com"):
        cands = (
            db.query(User)
            .filter(
                or_(
                    User.email.ilike("%@gmail.com"),
                    User.email.ilike("%@googlemail.com"),
                )
            )
            .all()
        )
        for row in cands:
            if row.email and identity_email(row.email) == key:
                return row
    return None


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """Lấy user bằng ID"""
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, user: UserCreate) -> Optional[User]:
    """Tạo user mới (ưu tiên email, lưu email theo identity_email khi là email)."""
    if not user.email and not user.phone:
        return None
    if user.phone and get_user_by_phone(db, user.phone):
        return None
    email_stored: Optional[str] = None
    if user.email:
        email_stored = identity_email(str(user.email))
    if email_stored and get_user_by_email(db, email_stored):
        return None

    db_user = User(
        phone=user.phone,
        date_of_birth=user.date_of_birth,
        email=email_stored,
        full_name=user.full_name,
        gender=user.gender.value if user.gender else None,
        address=user.address,
        is_verified=True,
        is_active=True
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    try:
        from app.services import promotion_grants as grant_svc

        grant_svc.process_signup_grants(db, db_user.id)
    except Exception:
        pass
    return db_user


def update_user(db: Session, user_id: int, user_update: UserUpdate) -> Optional[User]:
    """Cập nhật thông tin user"""
    db_user = get_user_by_id(db, user_id)
    if not db_user:
        return None
    
    update_data = user_update.dict(exclude_unset=True)
    
    if "email" in update_data and update_data["email"] is not None:
        update_data["email"] = identity_email(str(update_data["email"])) or str(update_data["email"]).strip().lower()
    
    # Xử lý gender Enum nếu có
    if 'gender' in update_data and update_data['gender']:
        update_data['gender'] = update_data['gender'].value
    
    for field, value in update_data.items():
        setattr(db_user, field, value)
    
    db.commit()
    db.refresh(db_user)
    return db_user


def verify_user(db: Session, user_id: int) -> Optional[User]:
    """Xác thực user"""
    db_user = get_user_by_id(db, user_id)
    if db_user:
        db_user.is_verified = True
        db.commit()
        db.refresh(db_user)
    return db_user


def update_last_login(db: Session, user_id: int) -> Optional[User]:
    """Cập nhật thời gian đăng nhập cuối"""
    db_user = get_user_by_id(db, user_id)
    if db_user:
        db_user.last_login = datetime.now()
        db.commit()
        db.refresh(db_user)
    return db_user


def get_users(db: Session, skip: int = 0, limit: int = 100) -> List[User]:
    """Lấy danh sách user"""
    return db.query(User).offset(skip).limit(limit).all()


def delete_user(db: Session, user_id: int) -> Optional[User]:
    """Xóa user"""
    db_user = get_user_by_id(db, user_id)
    if db_user:
        db.delete(db_user)
        db.commit()
    return db_user


def get_user_count(db: Session) -> int:
    """Đếm tổng số user"""
    return db.query(User).count()


def search_users(db: Session, keyword: str, skip: int = 0, limit: int = 100) -> List[User]:
    """Tìm kiếm user"""
    return db.query(User).filter(
        (User.phone.contains(keyword)) |
        (User.email.contains(keyword)) |
        (User.full_name.contains(keyword))
    ).offset(skip).limit(limit).all()


def get_search_users_count(db: Session, keyword: str) -> int:
    """Đếm số user khi tìm kiếm"""
    return db.query(User).filter(
        (User.phone.contains(keyword)) |
        (User.email.contains(keyword)) |
        (User.full_name.contains(keyword))
    ).count()


def admin_update_user(db: Session, user_id: int, data: UserAdminUpdate) -> Optional[User]:
    """Admin: cập nhật is_active, full_name, email, address"""
    u = get_user_by_id(db, user_id)
    if not u:
        return None
    update_data = data.model_dump(exclude_unset=True)
    if "email" in update_data and update_data["email"] is not None:
        update_data["email"] = identity_email(str(update_data["email"])) or str(update_data["email"]).strip().lower()
    for field, value in update_data.items():
        setattr(u, field, value)
    db.commit()
    db.refresh(u)
    return u


# ==============================
# USER BEHAVIOR FUNCTIONS (KEEP AS IS)
# ==============================

# PRODUCT VIEWS
def add_product_view_with_data(db: Session, user_id: int, view_data: ProductViewCreate) -> UserProductView:
    """Thêm/xem sản phẩm với dữ liệu chi tiết"""
    existing_view = db.query(UserProductView).filter(
        UserProductView.user_id == user_id,
        UserProductView.product_id == view_data.product_id
    ).first()
    
    if existing_view:
        existing_view.view_count += 1
        existing_view.time_spent_seconds = view_data.time_spent_seconds or 0
        if view_data.product_data:
            existing_view.product_data = view_data.product_data
        existing_view.viewed_at = datetime.now()
        db.commit()
        return existing_view
    else:
        db_view = UserProductView(
            user_id=user_id,
            product_id=view_data.product_id,
            product_data=view_data.product_data,
            time_spent_seconds=view_data.time_spent_seconds or 0,
            viewed_at=datetime.now()
        )
        db.add(db_view)
        db.commit()
        db.refresh(db_view)
        return db_view


def get_user_viewed_products(db: Session, user_id: int, limit: int = 20) -> List[UserProductView]:
    """Lấy danh sách sản phẩm đã xem"""
    return db.query(UserProductView).filter(
        UserProductView.user_id == user_id
    ).order_by(UserProductView.viewed_at.desc()).limit(limit).all()


def get_products_viewed_by_same_age_gender(
    db: Session, user_id: int, limit: int = 24
) -> Tuple[List[Product], str]:
    """
    Gợi ý theo hành vi nhóm cùng tuổi + giới (ưu tiên), có fallback.

    Trả về (products, cohort_mode):
    - profile_incomplete: chưa có ngày sinh hoặc giới tính
    - exact_cohort: từ lượt xem của user cùng năm sinh và cùng giới tính (is_active)
    - gender_peers: chưa đủ lượt xem nhóm tuổi — mở rộng cùng giới tính
    - popular_fallback: chưa có lượt xem để suy luận — SP phổ biến (purchases)

    Luôn trả cohort_mode để frontend hiển thị giải thích phù hợp.
    """
    user = get_user(db, user_id)
    if not user or not user.date_of_birth or not user.gender:
        return [], "profile_incomplete"

    birth_year = user.date_of_birth.year
    gender = user.gender

    def _product_ids_from_views(peer_ids: List[int]) -> List[int]:
        if not peer_ids:
            return []
        rows = (
            db.query(UserProductView.product_id, func.count(UserProductView.id).label("cnt"))
            .filter(UserProductView.user_id.in_(peer_ids))
            .group_by(UserProductView.product_id)
            .order_by(func.count(UserProductView.id).desc())
            .limit(limit * 2)
            .all()
        )
        return [r[0] for r in rows]

    def _hydrate_ordered(product_ids: List[int]) -> List[Product]:
        if not product_ids:
            return []
        rows = (
            db.query(Product)
            .filter(Product.id.in_(product_ids), Product.is_active == True)  # noqa: E712
            .all()
        )
        order_map = {pid: i for i, pid in enumerate(product_ids)}
        rows.sort(key=lambda p: order_map.get(p.id, 999))
        return rows[:limit]

    same_year_gender_ids = [
        r[0]
        for r in db.query(User.id)
        .filter(User.is_active == True)  # noqa: E712
        .filter(User.gender == gender)
        .filter(extract("year", User.date_of_birth) == birth_year)
        .all()
    ]
    product_ids = _product_ids_from_views(same_year_gender_ids)
    if product_ids:
        return _hydrate_ordered(product_ids), "exact_cohort"

    gender_peer_ids = [
        r[0]
        for r in db.query(User.id)
        .filter(User.is_active == True)  # noqa: E712
        .filter(User.gender == gender)
        .all()
    ]
    product_ids = _product_ids_from_views(gender_peer_ids)
    if product_ids:
        return _hydrate_ordered(product_ids), "gender_peers"

    popular = (
        db.query(Product)
        .filter(Product.is_active == True)  # noqa: E712
        .order_by(Product.purchases.desc().nullslast(), Product.id)
        .limit(limit)
        .all()
    )
    return popular, "popular_fallback"


SAME_SHOP_MAX_POOL = 8000
SAME_SHOP_MAX_PER_SHOP_PER_PAGE = 8


def _same_shop_key(product: Product) -> str:
    return (product.shop_name_chinese or "").strip().lower()


def _balance_same_shop_products(
    candidates: List[Product],
    recent_product_ids: List[int],
    product_by_id: Dict[int, Product],
    subs_lower: set[str],
    shops_lower: set[str],
    *,
    seed: int,
    page_size: int,
    offset: int = 0,
    limit: int = 60,
    max_per_shop_per_page: int = SAME_SHOP_MAX_PER_SHOP_PER_PAGE,
    total_items: Optional[int] = None,
) -> tuple[List[Product], int]:
    """
    Round-robin theo shop (trọng số = số lần shop xuất hiện trong 8 SP xem gần nhất).
    Mỗi trang nội bộ (page_size): tối đa max_per_shop_per_page SP/shop; trong shop ưu tiên cùng subcategory.
    Pagination: offset/limit áp dụng theo từng trang nội bộ (không gộp nhiều trang vào một response).
    """
    shop_seen_order: List[str] = []
    shop_freq: Dict[str, int] = {}
    for pid in recent_product_ids:
        recent = product_by_id.get(pid)
        if not recent:
            continue
        shop_cn = _same_shop_key(recent)
        if not shop_cn or shop_cn not in shops_lower:
            continue
        shop_freq[shop_cn] = shop_freq.get(shop_cn, 0) + 1
        if shop_cn not in shop_seen_order:
            shop_seen_order.append(shop_cn)

    weighted_cycle: List[str] = []
    for shop in shop_seen_order:
        weighted_cycle.extend([shop] * shop_freq[shop])
    if not weighted_cycle:
        return [], 0

    shop_tier_same: Dict[str, List[Product]] = defaultdict(list)
    shop_tier_only: Dict[str, List[Product]] = defaultdict(list)
    for product in candidates:
        shop_cn = _same_shop_key(product)
        if shop_cn not in shops_lower:
            continue
        sub = (product.subcategory or "").strip().lower()
        if sub and sub in subs_lower:
            shop_tier_same[shop_cn].append(product)
        else:
            shop_tier_only[shop_cn].append(product)

    rng = random.Random(seed)
    shop_queues: Dict[str, List[Product]] = {}
    for shop in shop_seen_order:
        same = shop_tier_same[shop]
        only = shop_tier_only[shop]
        rng.shuffle(same)
        rng.shuffle(only)
        combined = same + only
        if combined:
            shop_queues[shop] = combined

    if not shop_queues:
        return [], 0

    page_size = max(1, page_size)
    limit = max(1, limit)
    offset = max(0, offset)
    max_per_shop_per_page = max(1, max_per_shop_per_page)
    start_page = offset // page_size

    pages: List[List[Product]] = []
    cycle_idx = 0

    while any(shop_queues.values()):
        page_shop_counts: Dict[str, int] = defaultdict(int)
        page: List[Product] = []
        no_progress_cycles = 0

        while len(page) < page_size:
            if no_progress_cycles >= len(weighted_cycle):
                break

            shop = weighted_cycle[cycle_idx % len(weighted_cycle)]
            cycle_idx += 1

            queue = shop_queues.get(shop)
            if not queue:
                no_progress_cycles += 1
                continue
            if page_shop_counts[shop] >= max_per_shop_per_page:
                no_progress_cycles += 1
                continue

            page.append(queue.pop(0))
            page_shop_counts[shop] += 1
            no_progress_cycles = 0

        if not page:
            break

        pages.append(page)
        if len(pages) >= start_page + 1:
            break

    if not pages or start_page >= len(pages):
        return [], total_items if total_items is not None else 0

    slice_start = offset % page_size
    page_items = pages[start_page]
    flat_total = total_items if total_items is not None else sum(len(p) for p in pages)
    return page_items[slice_start : slice_start + limit], flat_total


def get_products_same_shop_as_recent_views(
    db: Session,
    user_id: Optional[int] = None,
    limit: int = 60,
    offset: int = 0,
    seed: Optional[int] = None,
    guest_session_id: Optional[str] = None,
    require_video: bool = False,
) -> tuple[List[Product], int, Optional[int]]:
    """
    Sản phẩm cùng `shop_name_chinese` (cột AM / Shop Trung Quốc) với các shop của tối đa 8 SP xem gần nhất.
    Cân bằng hiển thị: round-robin theo shop (trọng số lượt xem gần nhất), tối đa 8 SP/shop/trang (`limit`).
    Trong từng shop: ưu tiên cùng `subcategory` (cột AC) rồi trộn ngẫu nhiên (theo `seed`).
    Trả về (danh_sách_slice, total, seed). Không gửi `seed`: random mới mỗi lần; có `seed` + offset: pagination ổn định.
    `require_video`: chỉ SP có link video phát được (YouTube watch/embed/short hoặc URL chứa `.mp4`), khớp frontend.
    Ưu tiên user_id; nếu không có thì guest_session_id (bảng guest_product_views).
    Pool DB tối đa 8000 SP trước khi cân bằng — tránh quá tải bộ nhớ.
    """
    recent_product_ids: List[int] = []
    if user_id is not None:
        recent_views = (
            db.query(UserProductView.product_id)
            .filter(UserProductView.user_id == user_id)
            .order_by(UserProductView.viewed_at.desc())
            .limit(8)
            .all()
        )
        recent_product_ids = [r[0] for r in recent_views]
    elif guest_session_id and str(guest_session_id).strip():
        from app.crud import guest_behavior as guest_behavior_crud

        recent_product_ids = guest_behavior_crud.recent_guest_view_product_ids(
            db, str(guest_session_id).strip(), limit=8
        )
    if not recent_product_ids:
        return [], 0, None

    recent_products = db.query(Product).filter(Product.id.in_(recent_product_ids)).all()
    product_by_id = {p.id: p for p in recent_products}
    shops_lower: set[str] = set()
    subs_lower: set[str] = set()
    for p in recent_products:
        shop_cn = _same_shop_key(p)
        if shop_cn:
            shops_lower.add(shop_cn)
        sub = (p.subcategory or "").strip()
        if sub:
            subs_lower.add(sub.lower())
    if not shops_lower:
        return [], 0, None

    shop_conditions = [
        func.lower(func.trim(Product.shop_name_chinese)) == shop_lower for shop_lower in shops_lower
    ]
    # Tránh .all() không giới hạn — vài shop lớn → OOM / timeout → 500 trên production.
    filt = (
        or_(*shop_conditions),
        Product.is_active == True,  # noqa: E712
    )
    db_total = db.query(Product).filter(*filt).count()
    if db_total <= 0:
        return [], 0, None
    q = db.query(Product).filter(*filt).order_by(Product.id)
    candidates = q.limit(SAME_SHOP_MAX_POOL).all() if db_total > SAME_SHOP_MAX_POOL else q.all()
    if not candidates:
        return [], 0, None
    if require_video:
        candidates = [
            p for p in candidates if is_playable_product_video_link(getattr(p, "video_link", None))
        ]
    if not candidates:
        return [], 0, None

    if seed is None:
        seed = random.randint(0, 2**31 - 1)
    candidate_total = len(candidates)
    page, total = _balance_same_shop_products(
        candidates,
        recent_product_ids,
        product_by_id,
        subs_lower,
        shops_lower,
        seed=seed,
        page_size=max(1, limit),
        offset=offset,
        limit=limit,
        total_items=candidate_total,
    )
    return page, total, seed


# FAVORITES
def add_favorite_product_with_data(db: Session, user_id: int, favorite_data: FavoriteCreate) -> UserFavorite:
    """Thêm sản phẩm vào danh sách yêu thích"""
    existing_fav = db.query(UserFavorite).filter(
        UserFavorite.user_id == user_id,
        UserFavorite.product_id == favorite_data.product_id
    ).first()
    
    if existing_fav:
        if favorite_data.product_data:
            existing_fav.product_data = favorite_data.product_data
        db.commit()
        db.refresh(existing_fav)
        return existing_fav
    
    db_fav = UserFavorite(
        user_id=user_id,
        product_id=favorite_data.product_id,
        product_data=favorite_data.product_data,
        created_at=datetime.now()
    )
    db.add(db_fav)
    # Tăng lượt thích sản phẩm
    product = db.query(Product).filter(Product.id == favorite_data.product_id).first()
    if product:
        product.likes = (product.likes or 0) + 1
    db.commit()
    db.refresh(db_fav)
    return db_fav


def remove_favorite_product(db: Session, user_id: int, product_id: int) -> bool:
    """Xóa sản phẩm khỏi danh sách yêu thích"""
    favorite = db.query(UserFavorite).filter(
        UserFavorite.user_id == user_id,
        UserFavorite.product_id == product_id
    ).first()
    
    if not favorite:
        return False
    
    db.delete(favorite)
    # Giảm lượt thích sản phẩm (không nhỏ hơn 0)
    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        product.likes = max(0, (product.likes or 0) - 1)
    db.commit()
    return True


def get_user_favorites(db: Session, user_id: int, limit: int = 50) -> List[UserFavorite]:
    """Lấy danh sách sản phẩm yêu thích"""
    return db.query(UserFavorite).filter(
        UserFavorite.user_id == user_id
    ).order_by(UserFavorite.created_at.desc()).limit(limit).all()


def is_product_favorited(db: Session, user_id: int, product_id: int) -> bool:
    """Kiểm tra sản phẩm có trong danh sách yêu thích không"""
    favorite = db.query(UserFavorite).filter(
        UserFavorite.user_id == user_id,
        UserFavorite.product_id == product_id
    ).first()
    return favorite is not None


# CATEGORY VIEWS
def add_category_view_with_name(db: Session, user_id: int, category_data: CategoryViewCreate) -> UserCategoryView:
    """Thêm/xem danh mục"""
    existing_view = db.query(UserCategoryView).filter(
        UserCategoryView.user_id == user_id,
        UserCategoryView.category_id == category_data.category_id
    ).first()
    
    if existing_view:
        existing_view.view_count += 1
        if category_data.category_name:
            existing_view.category_name = category_data.category_name
        existing_view.viewed_at = datetime.now()
        db.commit()
        return existing_view
    else:
        db_view = UserCategoryView(
            user_id=user_id,
            category_id=category_data.category_id,
            category_name=category_data.category_name,
            viewed_at=datetime.now()
        )
        db.add(db_view)
        db.commit()
        db.refresh(db_view)
        return db_view


def get_user_viewed_categories(db: Session, user_id: int, limit: int = 10) -> List[UserCategoryView]:
    """Lấy danh sách danh mục đã xem"""
    return db.query(UserCategoryView).filter(
        UserCategoryView.user_id == user_id
    ).order_by(UserCategoryView.viewed_at.desc()).limit(limit).all()


# BRAND VIEWS
def add_brand_view(db: Session, user_id: int, brand_name: str) -> UserBrandView:
    """Thêm/xem thương hiệu"""
    existing_view = db.query(UserBrandView).filter(
        UserBrandView.user_id == user_id,
        UserBrandView.brand_name == brand_name
    ).first()
    
    if existing_view:
        existing_view.view_count += 1
        existing_view.viewed_at = datetime.now()
        db.commit()
        return existing_view
    else:
        db_view = UserBrandView(
            user_id=user_id,
            brand_name=brand_name,
            viewed_at=datetime.now()
        )
        db.add(db_view)
        db.commit()
        db.refresh(db_view)
        return db_view


def get_user_viewed_brands(db: Session, user_id: int, limit: int = 10) -> List[UserBrandView]:
    """Lấy danh sách thương hiệu đã xem"""
    return db.query(UserBrandView).filter(
        UserBrandView.user_id == user_id
    ).order_by(UserBrandView.viewed_at.desc()).limit(limit).all()


# SEARCH HISTORY
def add_search_history(db: Session, user_id: int, search_data: SearchHistoryCreate) -> UserSearchHistory:
    """Lưu lịch sử tìm kiếm"""
    db_search = UserSearchHistory(
        user_id=user_id,
        search_query=search_data.search_query,
        search_filters=search_data.search_filters,
        search_results_count=search_data.search_results_count or 0,
        searched_at=datetime.now()
    )
    db.add(db_search)
    db.commit()
    db.refresh(db_search)
    return db_search


def get_user_search_history(db: Session, user_id: int, limit: int = 20) -> List[UserSearchHistory]:
    """Lấy lịch sử tìm kiếm"""
    return db.query(UserSearchHistory).filter(
        UserSearchHistory.user_id == user_id
    ).order_by(UserSearchHistory.searched_at.desc()).limit(limit).all()


def clear_search_history(db: Session, user_id: int) -> None:
    """Xóa lịch sử tìm kiếm"""
    db.query(UserSearchHistory).filter(
        UserSearchHistory.user_id == user_id
    ).delete()
    db.commit()


def get_search_suggestions(
    db: Session,
    user_id: Optional[int],
    gender: Optional[str],
    birth_year: Optional[int],
    limit: int = 12,
    guest_session_id: Optional[str] = None,
) -> List[str]:
    """
    Gợi ý từ khóa tìm kiếm:
    - 3 cụm đầu: khách đã tìm gần đây nhất (nếu có)
    - Các cụm sau: tìm kiếm của khách khác cùng giới tính + năm sinh
    - Nếu chưa từng tìm: chỉ từ khách cùng giới tính + năm sinh
    """
    result: List[str] = []
    seen = set()

    def add_unique(term: str) -> bool:
        t = (term or "").strip().lower()
        if t and t not in seen:
            seen.add(t)
            result.append(term.strip())
            return True
        return False

    if user_id:
        recent = get_user_search_history(db, user_id, limit=3)
        for h in recent:
            if len(result) >= limit:
                break
            add_unique(h.search_query)
    elif guest_session_id and str(guest_session_id).strip():
        from app.crud import guest_behavior as guest_behavior_crud

        for h in guest_behavior_crud.get_guest_search_history(db, guest_session_id.strip(), limit=3):
            if len(result) >= limit:
                break
            add_unique(h.search_query)

    from sqlalchemy import func
    from app.models.user import User

    subq = (
        db.query(UserSearchHistory.search_query, func.count(UserSearchHistory.id).label("cnt"))
        .join(User, UserSearchHistory.user_id == User.id)
        .filter(UserSearchHistory.search_query.isnot(None))
        .filter(UserSearchHistory.search_query != "")
    )
    if gender:
        subq = subq.filter(User.gender == gender)
    if birth_year is not None:
        from sqlalchemy import extract
        subq = subq.filter(extract("year", User.date_of_birth) == birth_year)
    if user_id:
        subq = subq.filter(UserSearchHistory.user_id != user_id)
    subq = subq.group_by(UserSearchHistory.search_query).order_by(
        func.count(UserSearchHistory.id).desc()
    )
    rows = subq.limit(limit + 20).all()

    for row in rows:
        if len(result) >= limit:
            break
        add_unique(row.search_query)

    return result[:limit]


# SHOP INTERACTIONS
def add_shop_interaction(db: Session, user_id: int, interaction_data: ShopInteractionCreate) -> UserShopInteraction:
    """Thêm tương tác với shop"""
    existing_interaction = db.query(UserShopInteraction).filter(
        UserShopInteraction.user_id == user_id,
        UserShopInteraction.shop_name == interaction_data.shop_name,
        UserShopInteraction.interaction_type == interaction_data.interaction_type
    ).first()
    
    if existing_interaction:
        existing_interaction.interaction_count += 1
        existing_interaction.interacted_at = datetime.now()
        if interaction_data.shop_id:
            existing_interaction.shop_id = interaction_data.shop_id
        if interaction_data.shop_search_url:
            existing_interaction.shop_search_url = interaction_data.shop_search_url
        if interaction_data.shop_id_search_url:
            existing_interaction.shop_id_search_url = interaction_data.shop_id_search_url
        if interaction_data.related_cheaper_search_url:
            existing_interaction.related_cheaper_search_url = interaction_data.related_cheaper_search_url
        if interaction_data.related_expensive_search_url:
            existing_interaction.related_expensive_search_url = interaction_data.related_expensive_search_url
        db.commit()
        return existing_interaction
    else:
        db_interaction = UserShopInteraction(
            user_id=user_id,
            shop_name=interaction_data.shop_name,
            shop_id=interaction_data.shop_id,
            shop_search_url=interaction_data.shop_search_url,
            shop_id_search_url=interaction_data.shop_id_search_url,
            related_cheaper_search_url=interaction_data.related_cheaper_search_url,
            related_expensive_search_url=interaction_data.related_expensive_search_url,
            interaction_type=interaction_data.interaction_type,
            interacted_at=datetime.now()
        )
        db.add(db_interaction)
        db.commit()
        db.refresh(db_interaction)
        return db_interaction


def get_user_shop_interactions(db: Session, user_id: int, limit: int = 20) -> List[UserShopInteraction]:
    """Lấy lịch sử tương tác với shop"""
    return db.query(UserShopInteraction).filter(
        UserShopInteraction.user_id == user_id
    ).order_by(UserShopInteraction.interacted_at.desc()).limit(limit).all()


def get_user_shop_interactions_by_type(db: Session, user_id: int, interaction_type: str, limit: int = 20) -> List[UserShopInteraction]:
    """Lấy tương tác với shop theo loại"""
    return db.query(UserShopInteraction).filter(
        UserShopInteraction.user_id == user_id,
        UserShopInteraction.interaction_type == interaction_type
    ).order_by(UserShopInteraction.interacted_at.desc()).limit(limit).all()


# BEHAVIOR STATS
def get_user_behavior_stats(db: Session, user_id: int) -> Dict[str, Any]:
    """Lấy thống kê hành vi người dùng đầy đủ"""
    total_products_viewed = db.query(UserProductView).filter(
        UserProductView.user_id == user_id
    ).count()
    
    total_favorites = db.query(UserFavorite).filter(
        UserFavorite.user_id == user_id
    ).count()
    
    total_categories_viewed = db.query(UserCategoryView).filter(
        UserCategoryView.user_id == user_id
    ).count()
    
    total_brands_viewed = db.query(UserBrandView).filter(
        UserBrandView.user_id == user_id
    ).count()
    
    total_searches = db.query(UserSearchHistory).filter(
        UserSearchHistory.user_id == user_id
    ).count()
    
    total_shop_interactions = db.query(UserShopInteraction).filter(
        UserShopInteraction.user_id == user_id
    ).count()
    
    recently_viewed_products = get_user_viewed_products(db, user_id, limit=10)
    favorite_products = get_user_favorites(db, user_id, limit=10)
    recently_viewed_categories = get_user_viewed_categories(db, user_id, limit=5)
    recently_viewed_brands = get_user_viewed_brands(db, user_id, limit=5)
    recent_searches = get_user_search_history(db, user_id, limit=10)
    recent_shop_interactions = get_user_shop_interactions(db, user_id, limit=10)
    
    return {
        "total_products_viewed": total_products_viewed,
        "total_favorites": total_favorites,
        "total_categories_viewed": total_categories_viewed,
        "total_brands_viewed": total_brands_viewed,
        "total_searches": total_searches,
        "total_shop_interactions": total_shop_interactions,
        "recently_viewed_products": recently_viewed_products,
        "favorite_products": favorite_products,
        "recently_viewed_categories": recently_viewed_categories,
        "recently_viewed_brands": recently_viewed_brands,
        "recent_searches": recent_searches,
        "recent_shop_interactions": recent_shop_interactions
    }


def _gender_category_suffix(gender: Optional[str]) -> Optional[str]:
    """Hậu tố tên danh mục cấp 1 theo giới (taxonomy: «… Nam» / «… Nữ»)."""
    g = (gender or "").strip().lower()
    if g in ("male", "m", "nam"):
        return " Nam"
    if g in ("female", "f", "nu", "nữ"):
        return " Nữ"
    return None


def get_popular_categories_for_gender(
    db: Session,
    gender: Optional[str],
    *,
    limit: int = 6,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Danh mục cấp 1 phổ biến theo giới tính hồ sơ — xếp theo tổng lượt mua (purchases).
    Trả (danh sách {name, purchases, product_count}, nhãn «Nam»|«Nữ»).
    """
    suffix = _gender_category_suffix(gender)
    if not suffix:
        return [], None
    gender_label = "Nam" if suffix.strip() == "Nam" else "Nữ"
    purchase_sum = func.coalesce(func.sum(Product.purchases), 0)
    rows = (
        db.query(
            Product.category.label("name"),
            purchase_sum.label("purchases"),
            func.count(Product.id).label("product_count"),
        )
        .filter(Product.is_active.is_(True))
        .filter(Product.category.isnot(None))
        .filter(Product.category != "")
        .filter(Product.category.like(f"%{suffix}"))
        .group_by(Product.category)
        .order_by(purchase_sum.desc(), func.count(Product.id).desc(), Product.category)
        .limit(max(1, min(int(limit), 12)))
        .all()
    )
    items: List[Dict[str, Any]] = []
    for r in rows:
        name = (r.name or "").strip()
        if not name:
            continue
        items.append(
            {
                "name": name,
                "purchases": int(r.purchases or 0),
                "product_count": int(r.product_count or 0),
            }
        )
    return items, gender_label


def get_popular_categories_from_recent_views(
    db: Session,
    *,
    user_id: Optional[int] = None,
    guest_session_id: Optional[str] = None,
    recent_limit: int = 8,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    """
    Danh mục cấp 1 gợi ý từ tối đa `recent_limit` sản phẩm xem gần nhất (user hoặc phiên khách).
    Ưu tiên danh mục xuất hiện nhiều / gần đây trong lượt xem; hòa theo purchases tổng danh mục.
    """
    product_ids: List[int] = []
    if user_id is not None:
        rows = (
            db.query(UserProductView.product_id)
            .filter(UserProductView.user_id == user_id)
            .order_by(UserProductView.viewed_at.desc())
            .limit(max(1, min(int(recent_limit), 24)))
            .all()
        )
        product_ids = [int(r[0]) for r in rows if r[0] is not None]
    else:
        sid = (guest_session_id or "").strip()
        if not sid:
            return []
        from app.crud import guest_behavior as guest_behavior_crud

        product_ids = guest_behavior_crud.recent_guest_view_product_ids(
            db, sid, limit=max(1, min(int(recent_limit), 24))
        )

    if not product_ids:
        return []

    products = (
        db.query(Product)
        .filter(Product.id.in_(product_ids), Product.is_active.is_(True))  # noqa: E712
        .all()
    )
    by_id = {p.id: p for p in products}
    cap = max(1, min(int(recent_limit), 24))

    scores: Dict[str, Dict[str, Any]] = {}
    for i, pid in enumerate(product_ids):
        p = by_id.get(pid)
        if not p:
            continue
        cat = (p.category or "").strip()
        if not cat:
            continue
        if cat not in scores:
            scores[cat] = {"name": cat, "view_hits": 0, "recency_score": 0}
        scores[cat]["view_hits"] += 1
        scores[cat]["recency_score"] += cap - i

    if not scores:
        return []

    purchase_sum = func.coalesce(func.sum(Product.purchases), 0)
    for cat, row in scores.items():
        agg = (
            db.query(
                purchase_sum.label("purchases"),
                func.count(Product.id).label("product_count"),
            )
            .filter(Product.is_active.is_(True), Product.category == cat)  # noqa: E712
            .first()
        )
        row["purchases"] = int((agg.purchases if agg else 0) or 0)
        row["product_count"] = int((agg.product_count if agg else 0) or 0)

    ranked = sorted(
        scores.values(),
        key=lambda x: (x["recency_score"], x["view_hits"], x["purchases"]),
        reverse=True,
    )
    out: List[Dict[str, Any]] = []
    for row in ranked[: max(1, min(int(limit), 12))]:
        out.append(
            {
                "name": row["name"],
                "purchases": row["purchases"],
                "product_count": row["product_count"],
                "view_hits": row["view_hits"],
            }
        )
    return out


print("✅ User CRUD module loaded successfully with get_user() function")