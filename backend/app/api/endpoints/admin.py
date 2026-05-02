# backend/app/api/endpoints/admin.py
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import case, func
from typing import List, Optional
from app.db.session import get_db
from app import crud, models
from app.models.admin import AdminUser
from app.schemas.admin import AdminLogin, AdminTokenResponse
from app.schemas.bank_account import BankAccountCreate, BankAccountUpdate, BankAccountResponse
from app.schemas.user import UserResponse, UserAdminUpdate, AdminUsersListResponse
from app.schemas.search_mapping import SearchMappingListResponse, SearchMappingResponse, SearchMappingCreateRequest
from app.schemas.search_cache_admin import (
    ClearProductSearchCacheResponse,
    ProductSearchCacheListResponse,
    ProductSearchCacheRowItem,
    SearchKeywordStatItem,
    SearchKeywordStatsResponse,
)
from app.crud import product_search_cache as product_search_cache_crud
from app.models.search_log import SearchLog
from app.schemas.site_embed_code import (
    SiteEmbedCodeAdminItem,
    SiteEmbedCodeCreate,
    SiteEmbedCodeUpdate,
)
from app.crud import site_embed_code as embed_crud
from app.crud import shop_video_fab as shop_video_fab_crud
from app.schemas.shop_video_fab import ShopVideoFabPublicOut, ShopVideoFabAdminUpdate
from app.core.security import create_admin_token, get_current_admin
from app.core.config import settings

router = APIRouter()

FIRST_ADMIN_HINT = (
    "Trên server, trong thư mục backend: python create_first_admin.py — "
    "sau đó đăng nhập username admin, mật khẩu admin123 (đổi sau khi vào được)."
)


@router.get("/check-setup")
def admin_check_setup(db: Session = Depends(get_db)):
    """Kiểm tra đã có admin chưa (để hiển thị gợi ý trên trang login). Không cần auth."""
    count = db.query(func.count(AdminUser.id)).scalar() or 0
    return {
        "admin_exists": count > 0,
        "hint": FIRST_ADMIN_HINT if count == 0 else None,
    }

@router.post("/login", response_model=AdminTokenResponse)
def admin_login(login_data: AdminLogin, db: Session = Depends(get_db)):
    """Đăng nhập admin - trả về JWT token"""
    admin = crud.verify_admin_password(db, login_data.username, login_data.password)
    if not admin:
        has_any = db.query(func.count(AdminUser.id)).scalar() or 0
        if has_any == 0:
            msg = (
                "Chưa có tài khoản admin trong database. SSH vào VPS, cd backend, "
                "chạy: python create_first_admin.py — rồi đăng nhập username admin và mật khẩu admin123 "
                "(đổi trong trang quản trị)."
            )
        elif settings.DEBUG:
            msg = "Sai tên đăng nhập hoặc mật khẩu. Gợi ý: python reset_admin_password.py trong backend."
        else:
            msg = "Sai tên đăng nhập hoặc mật khẩu."
        raise HTTPException(status_code=401, detail=msg)
    if not admin.is_active:
        raise HTTPException(status_code=403, detail="Tài khoản admin đã bị vô hiệu hóa")
    crud.update_admin_last_login(db, admin.id)
    token = create_admin_token(admin.id)
    role_value = admin.role.value if hasattr(admin.role, "value") else str(admin.role)
    return AdminTokenResponse(
        access_token=token,
        token_type="bearer",
        admin_id=admin.id,
        username=admin.username,
        role=role_value,
    )


# ========== BANK ACCOUNTS (admin) - tránh 404 khi router bank_accounts load lỗi ==========
@router.get("/bank-accounts/all", response_model=List[BankAccountResponse])
def admin_bank_list_all(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
):
    """Danh sách tất cả tài khoản ngân hàng."""
    return crud.bank_account.get_bank_accounts(db, active_only=False)


@router.post("/bank-accounts/", response_model=BankAccountResponse)
def admin_bank_create(
    data: BankAccountCreate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
):
    """Thêm tài khoản ngân hàng."""
    return crud.bank_account.create_bank_account(db, data)


@router.put("/bank-accounts/{account_id}", response_model=BankAccountResponse)
def admin_bank_update(
    account_id: int,
    data: BankAccountUpdate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
):
    """Cập nhật tài khoản ngân hàng."""
    acc = crud.bank_account.update_bank_account(db, account_id, data)
    if not acc:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
    return acc


@router.delete("/bank-accounts/{account_id}", status_code=204)
def admin_bank_delete(
    account_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
):
    """Xóa tài khoản ngân hàng."""
    ok = crud.bank_account.delete_bank_account(db, account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")


# ========== MEMBERS (thành viên / users) ==========
@router.get("/users", response_model=AdminUsersListResponse)
def admin_list_users(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    keyword: Optional[str] = Query(None),
):
    """Danh sách thành viên (users) với tìm kiếm và phân trang."""
    if keyword and keyword.strip():
        users = crud.user.search_users(db, keyword.strip(), skip=skip, limit=limit)
        total = crud.user.get_search_users_count(db, keyword.strip())
    else:
        users = crud.user.get_users(db, skip=skip, limit=limit)
        total = crud.user.get_user_count(db)
    items = [UserResponse.model_validate(u) for u in users]
    return AdminUsersListResponse(items=items, total=total)


@router.get("/users/{user_id}", response_model=UserResponse)
def admin_get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
):
    """Chi tiết một thành viên."""
    user = crud.user.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy thành viên")
    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
def admin_update_user(
    user_id: int,
    data: UserAdminUpdate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
):
    """Cập nhật thành viên (trạng thái kích hoạt, tên, email, địa chỉ)."""
    user = crud.user.admin_update_user(db, user_id, data)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy thành viên")
    return user


# ========== SEARCH MAPPINGS ==========
@router.get("/search-mappings", response_model=SearchMappingListResponse)
def admin_list_search_mappings(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    keyword: Optional[str] = Query(None, description="Tìm theo keyword_input/keyword_target"),
    mapping_type: Optional[str] = Query(None, description="product_search | category_redirect"),
):
    query = db.query(models.SearchMapping)
    if mapping_type in ("product_search", "category_redirect"):
        query = query.filter(models.SearchMapping.type == mapping_type)
    if keyword and keyword.strip():
        key = f"%{keyword.strip()}%"
        query = query.filter(
            models.SearchMapping.keyword_input.ilike(key) |
            models.SearchMapping.keyword_target.ilike(key)
        )
    total = query.count()
    items = query.order_by(models.SearchMapping.updated_at.desc().nullslast(), models.SearchMapping.id.desc()) \
        .offset(skip).limit(limit).all()
    return SearchMappingListResponse(
        items=[SearchMappingResponse.model_validate(i) for i in items],
        total=total,
        page=skip // limit + 1 if limit > 0 else 1,
        size=limit,
        total_pages=(total // limit + (1 if total % limit else 0)) if limit > 0 else 1,
    )


@router.post("/search-mappings", response_model=SearchMappingResponse)
def admin_create_search_mapping(
    payload: SearchMappingCreateRequest,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
):
    keyword_input = payload.keyword_input.strip()
    keyword_target = payload.keyword_target.strip()
    if not keyword_input or not keyword_target:
        raise HTTPException(status_code=400, detail="Thiếu keyword_input hoặc keyword_target")
    if payload.type not in ("product_search", "category_redirect"):
        raise HTTPException(status_code=400, detail="type không hợp lệ")
    normalized_key = crud.product._normalize_search_key(keyword_input)
    mapping = db.query(models.SearchMapping).filter(models.SearchMapping.keyword_input == normalized_key).first()
    if mapping:
        mapping.keyword_target = keyword_target
        mapping.type = payload.type
    else:
        mapping = models.SearchMapping(
            keyword_input=normalized_key,
            keyword_target=keyword_target,
            type=payload.type,
        )
        db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return SearchMappingResponse.model_validate(mapping)


@router.delete("/search-mappings/{mapping_id}", status_code=204)
def admin_delete_search_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
):
    mapping = db.query(models.SearchMapping).filter(models.SearchMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Không tìm thấy mapping")
    db.delete(mapping)
    db.commit()


# ========== THỐNG KÊ TÌM KIẾM + CACHE GET /products/?q=... ==========
@router.get("/search-analytics/keywords", response_model=SearchKeywordStatsResponse)
def admin_search_keyword_stats(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
    days: int = Query(30, ge=1, le=366, description="Chỉ tính log trong N ngày gần đây"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    """
    Từ khóa được tìm nhiều (theo bảng search_logs — mỗi lần gọi get_products có q thường ghi 1 dòng).
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    base_filter = SearchLog.created_at >= since

    total_distinct = (
        db.query(func.count(func.distinct(SearchLog.keyword)))
        .filter(base_filter)
        .scalar()
        or 0
    )

    ai_sum = func.coalesce(
        func.sum(case((SearchLog.ai_processed.is_(True), 1), else_=0)), 0
    )
    rows = (
        db.query(
            SearchLog.keyword,
            func.count(SearchLog.id).label("cnt"),
            func.avg(SearchLog.result_count).label("avg_res"),
            ai_sum.label("ai_cnt"),
        )
        .filter(base_filter)
        .group_by(SearchLog.keyword)
        .order_by(func.count(SearchLog.id).desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = [
        SearchKeywordStatItem(
            keyword=r[0],
            search_count=int(r[1] or 0),
            avg_result_count=float(r[2] or 0),
            ai_processed_count=int(r[3] or 0),
        )
        for r in rows
    ]
    return SearchKeywordStatsResponse(
        days=days,
        total_distinct_keywords=int(total_distinct),
        items=items,
    )


@router.get("/product-search-cache", response_model=ProductSearchCacheListResponse)
def admin_list_product_search_cache(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """Danh sách cache JSON (khóa là hash; cột gợi ý lấy từ normalized_query/applied_query trong JSON nếu có)."""
    total_rows, active_rows, expired_rows = product_search_cache_crud.count_cache_by_state(db)
    rows = product_search_cache_crud.list_cache_rows_admin(db, skip=skip, limit=limit)
    items = []
    for row in rows:
        body = row.response_json or ""
        items.append(
            ProductSearchCacheRowItem(
                cache_key=row.cache_key,
                expires_at=row.expires_at,
                created_at=row.created_at,
                response_size_bytes=len(body.encode("utf-8")),
                hint_query=product_search_cache_crud.hint_from_cached_json(body),
            )
        )
    return ProductSearchCacheListResponse(
        total_rows=total_rows,
        active_rows=active_rows,
        expired_rows=expired_rows,
        items=items,
    )


@router.delete("/product-search-cache", response_model=ClearProductSearchCacheResponse)
def admin_clear_product_search_cache(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
    scope: str = Query(
        "expired",
        description="expired = chỉ xóa đã hết hạn; all = xóa toàn bộ cache",
    ),
):
    s = (scope or "").strip().lower()
    if s not in ("expired", "all"):
        raise HTTPException(status_code=400, detail='scope phải là "expired" hoặc "all"')
    deleted = product_search_cache_crud.clear_product_search_cache(db, expired_only=(s == "expired"))
    return ClearProductSearchCacheResponse(deleted=deleted, scope=s)


# ========== MÃ NHÚNG (Google, Facebook, Zalo, GA4, GTM, Pixel...) ==========
@router.get("/site-embed-codes", response_model=List[SiteEmbedCodeAdminItem])
def admin_list_site_embed_codes(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
):
    rows = embed_crud.list_embed_codes(db, include_inactive=True)
    return [embed_crud.row_to_admin_item(r) for r in rows]


@router.post("/site-embed-codes", response_model=SiteEmbedCodeAdminItem)
def admin_create_site_embed_code(
    data: SiteEmbedCodeCreate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
):
    if not data.title or not data.title.strip():
        raise HTTPException(status_code=400, detail="Tiêu đề không được để trống")
    row = embed_crud.create_embed_code(db, data)
    return embed_crud.row_to_admin_item(row)


@router.put("/site-embed-codes/{embed_id}", response_model=SiteEmbedCodeAdminItem)
def admin_update_site_embed_code(
    embed_id: int,
    data: SiteEmbedCodeUpdate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
):
    row = embed_crud.update_embed_code(db, embed_id, data)
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy mã nhúng")
    return embed_crud.row_to_admin_item(row)


@router.delete("/site-embed-codes/{embed_id}", status_code=204)
def admin_delete_site_embed_code(
    embed_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
):
    ok = embed_crud.delete_embed_code(db, embed_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy mã nhúng")


# ========== Vị trí nút lướt video shop (FAB) ==========
@router.get("/shop-video-fab-settings", response_model=ShopVideoFabPublicOut)
def admin_get_shop_video_fab_settings(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
):
    row = shop_video_fab_crud.get_or_create_singleton(db)
    return shop_video_fab_crud.row_to_public_out(row)


@router.put("/shop-video-fab-settings", response_model=ShopVideoFabPublicOut)
def admin_put_shop_video_fab_settings(
    data: ShopVideoFabAdminUpdate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_admin),
):
    if not data.model_dump(exclude_unset=True):
        row = shop_video_fab_crud.get_or_create_singleton(db)
        return shop_video_fab_crud.row_to_public_out(row)
    return shop_video_fab_crud.update_singleton(db, data)
