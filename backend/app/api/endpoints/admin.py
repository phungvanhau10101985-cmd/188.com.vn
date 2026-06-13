# backend/app/api/endpoints/admin.py
import logging
from datetime import datetime, timedelta, timezone
import json
import mimetypes
import os
import re
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import case, func
from typing import List, Optional
from app.db.session import get_db
from app import crud, models
from app.models.admin import AdminUser, AdminRole
from app.schemas.admin import (
    AdminLogin,
    AdminTokenResponse,
    UserLinkedStaffPayload,
    AdminStaffAccountRow,
    AdminStaffAccountListResponse,
    AdminStaffPermissionsPatch,
    StaffRolePresetCrudFlags,
    StaffRolePresetItem,
    StaffRolePresetListResponse,
    StaffRolePresetPutPayload,
)
from app.schemas.bank_account import BankAccountCreate, BankAccountUpdate, BankAccountResponse
from app.schemas.user import (
    UserResponse,
    UserAdminUpdate,
    AdminUsersListResponse,
    AdminMemberImportResponse,
)
from app.schemas.search_mapping import SearchMappingListResponse, SearchMappingResponse, SearchMappingCreateRequest
from app.schemas.search_cache_admin import (
    ClearProductSearchCacheResponse,
    ProductSearchCacheListResponse,
    ProductSearchCacheRowItem,
    SearchKeywordStatItem,
    SearchKeywordStatsResponse,
)
from app.crud import product_search_cache as product_search_cache_crud
from app.schemas.listing_facet_cache_admin import (
    ListingFacetCacheClearResponse,
    ListingFacetCacheDetailResponse,
    ListingFacetCacheListResponse,
    ListingFacetCachePinSearchRequest,
    ListingFacetCacheRebuildRequest,
    ListingFacetCacheRebuildResponse,
    ListingFacetCacheRowItem,
    ListingFacetCacheToggleRequest,
)
from app.crud import listing_facet_cache as listing_facet_cache_crud

logger = logging.getLogger(__name__)
from app.models.search_log import SearchLog
from app.schemas.site_embed_code import (
    SiteEmbedCodeAdminItem,
    SiteEmbedCodeCreate,
    SiteEmbedCodeUpdate,
)
from app.crud import site_embed_code as embed_crud
from app.crud import shop_video_fab as shop_video_fab_crud
from app.schemas.shop_video_fab import ShopVideoFabPublicOut, ShopVideoFabAdminUpdate
from app.schemas.bunny_admin import BunnyCdnStatusOut, BunnyCdnUploadOut
from app.schemas.integrations_admin import (
    AdminIntegrationKeyGroup,
    AdminIntegrationKeyRow,
    AdminIntegrationKeysOverviewOut,
)
from app.services.bunny_storage import build_public_object_url, upload_file_to_zone
from app.services.image_raster_jpeg import raster_bytes_to_jpeg_bytes
from app.services.linked_admin_staff import apply_linked_staff_role
from app.services.user_public_response import admin_panel_user_response, batch_admin_panel_user_responses
from app.core.security import create_admin_token, require_privileged_admin, require_module_permission, require_super_admin
from app.core.config import settings
from app.services.import_scraper_cookies import (
    delete_scraper_cookies,
    save_scraper_cookies_from_text,
    scraper_cookie_settings_dict,
    upsert_scraper_cookie_env_local,
)
from app.core.admin_permissions import (
    effective_module_keys,
    normalize_module_list,
    uses_custom_granular,
    ensure_default_staff_presets,
    get_staff_preset_payload,
    upsert_staff_preset,
    PRESET_STAFF_ROLES,
)

router = APIRouter()


def _restart_process_later() -> None:
    time.sleep(0.8)
    os._exit(0)


class Import1688CookieSettingsIn(BaseModel):
    cookie_text: str


def _import_1688_cookie_settings_out(message: str | None = None) -> dict:
    return scraper_cookie_settings_dict(message)

FIRST_ADMIN_HINT = (
    "Trên server, trong thư mục backend: python create_first_admin.py — "
    "sau đó đăng nhập username admin, mật khẩu admin123 (đổi sau khi vào được)."
)

_BUNNY_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_BUNNY_UPLOAD_MAX_BYTES = 15 * 1024 * 1024


def _bunny_safe_subfolder(raw: str) -> str:
    t = (raw or "").strip().lower().replace("\\", "/")
    t = re.sub(r"[^a-z0-9/_-]", "", t)
    parts = [p for p in t.split("/") if p and p not in (".", "..")]
    return "/".join(parts[:8])


@router.get("/check-setup")
def admin_check_setup(db: Session = Depends(get_db)):
    """Kiểm tra đã có admin chưa (để hiển thị gợi ý trên trang login). Không cần auth."""
    count = db.query(func.count(AdminUser.id)).scalar() or 0
    return {
        "admin_exists": count > 0,
        "hint": FIRST_ADMIN_HINT if count == 0 else None,
    }


@router.post("/restart-api")
def admin_restart_api(
    background_tasks: BackgroundTasks,
    _: AdminUser = Depends(require_privileged_admin),
):
    """Fallback endpoint restart API cho trang cấu hình 1688."""
    background_tasks.add_task(_restart_process_later)
    return {
        "success": True,
        "message": "API sẽ tự thoát trong giây lát. PM2/systemd/Docker cần tự khởi động lại process.",
    }


@router.get("/import-1688-cookie")
def admin_get_import_1688_cookie_settings(
    _: AdminUser = Depends(require_privileged_admin),
):
    """Fallback endpoint đọc cấu hình cookie 1688 khi router import-1688 chưa được load."""
    return _import_1688_cookie_settings_out()


@router.put("/import-1688-cookie")
def admin_save_import_1688_cookie_settings(
    payload: Import1688CookieSettingsIn,
    _: AdminUser = Depends(require_privileged_admin),
):
    """Fallback endpoint lưu cookie 1688 khi router import-1688 chưa được load."""
    try:
        count = save_scraper_cookies_from_text(payload.cookie_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cookie không hợp lệ: {exc}") from exc

    upsert_scraper_cookie_env_local(
        {
            "IMPORT_SCRAPER_COOKIE_FILE": settings.IMPORT_SCRAPER_COOKIE_FILE,
            "IMPORT_SCRAPER_COOKIE_JSON": "",
            "IMPORT_1688_COOKIE_FILE": settings.IMPORT_SCRAPER_COOKIE_FILE,
            "IMPORT_1688_COOKIE_JSON": "",
            "IMPORT_1688_ENABLED": "true",
        }
    )
    settings.IMPORT_1688_ENABLED = True
    return _import_1688_cookie_settings_out(
        f"Đã lưu {count} cookie scrape chung (Hibox, Vipomall, kiểm tra tồn kho)."
    )


@router.delete("/import-1688-cookie")
def admin_delete_import_1688_cookie_settings(
    _: AdminUser = Depends(require_privileged_admin),
):
    """Fallback xóa cookie scrape khi router import-1688 chưa được load."""
    delete_scraper_cookies()
    upsert_scraper_cookie_env_local(
        {
            "IMPORT_SCRAPER_COOKIE_FILE": "",
            "IMPORT_SCRAPER_COOKIE_JSON": "",
            "IMPORT_1688_COOKIE_FILE": "",
            "IMPORT_1688_COOKIE_JSON": "",
        }
    )
    return _import_1688_cookie_settings_out("Đã xóa cookie scrape trên server.")


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
    db.refresh(admin)
    token = create_admin_token(admin.id)
    role_value = admin.role.value if hasattr(admin.role, "value") else str(admin.role)
    return AdminTokenResponse(
        access_token=token,
        token_type="bearer",
        admin_id=admin.id,
        username=admin.username,
        role=role_value,
        modules=effective_module_keys(admin, db),
    )


# ========== BANK ACCOUNTS (admin) - tránh 404 khi router bank_accounts load lỗi ==========
@router.get("/bank-accounts/all", response_model=List[BankAccountResponse])
def admin_bank_list_all(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("bank_accounts")),
):
    """Danh sách tất cả tài khoản ngân hàng."""
    return crud.bank_account.get_bank_accounts(db, active_only=False)


@router.post("/bank-accounts/", response_model=BankAccountResponse)
def admin_bank_create(
    data: BankAccountCreate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("bank_accounts")),
):
    """Thêm tài khoản ngân hàng."""
    return crud.bank_account.create_bank_account(db, data)


@router.put("/bank-accounts/{account_id}", response_model=BankAccountResponse)
def admin_bank_update(
    account_id: int,
    data: BankAccountUpdate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("bank_accounts")),
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
    current_admin: models.AdminUser = Depends(require_module_permission("bank_accounts")),
):
    """Xóa tài khoản ngân hàng."""
    ok = crud.bank_account.delete_bank_account(db, account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")


# ========== MEMBERS (thành viên / users) ==========
@router.get("/users", response_model=AdminUsersListResponse)
def admin_list_users(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("members")),
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
    items = batch_admin_panel_user_responses(db, users)
    return AdminUsersListResponse(items=items, total=total)


@router.post("/users/import-file", response_model=AdminMemberImportResponse)
async def admin_import_legacy_members(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(require_module_permission("members")),
):
    """
    Import khách hàng cũ từ CSV/Excel: name, gender, email, birthday, phone.
    Tự sửa email gõ nhầm; tạo tài khoản thành viên (đăng nhập OTP email sau).
    """
    filename = file.filename or ""
    if not filename.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ .csv, .xlsx hoặc .xls")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File trống.")

    from app.services.customer_list_import import parse_customer_upload

    try:
        parsed = parse_customer_upload(filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Không đọc được file: {exc}") from exc

    importable = [r for r in parsed.rows if r.email or r.phone]
    if not importable:
        raise HTTPException(
            status_code=400,
            detail="Không có dòng hợp lệ — cần ít nhất email hoặc SĐT đúng định dạng.",
        )

    try:
        result = crud.user.import_legacy_customers_bulk(db, importable)
    except Exception as exc:
        db.rollback()
        logger.exception("admin import legacy members failed")
        raise HTTPException(
            status_code=500,
            detail=f"Import thất bại: {exc}. Kiểm tra email/SĐT trùng trong file hoặc thử file nhỏ hơn.",
        ) from exc

    corrections = [
        {
            "row": r.row_number,
            "original": r.email_original or "",
            "fixed": r.email or "",
            "fixes": r.email_fixes,
        }
        for r in parsed.rows
        if r.email and r.email_corrected
    ][:100]

    invalid_rows = [
        {
            "row": r.row_number,
            "email": r.email_original or "",
            "name": r.name or "",
            "reason": r.invalid_reason or "Thiếu email/SĐT hoặc trùng dữ liệu",
        }
        for r in parsed.rows
        if not r.email and not r.phone
    ][:100]

    msg = (
        f"Import xong: {result['created']} thành viên mới, "
        f"{result['updated']} cập nhật hồ sơ, {result['skipped']} không đổi / bỏ qua, "
        f"{parsed.invalid_count} không hợp lệ."
    )
    if parsed.corrected_count:
        msg += f" Đã sửa {parsed.corrected_count} email gõ nhầm."

    return AdminMemberImportResponse(
        created=result["created"],
        updated=result["updated"],
        skipped=result["skipped"],
        invalid=parsed.invalid_count + int(result.get("invalid") or 0),
        corrected=parsed.corrected_count,
        duplicate_in_file=parsed.duplicate_in_file,
        total_input=parsed.total_input,
        parsed=len(importable),
        corrections=corrections,
        invalid_rows=invalid_rows,
        message=msg,
    )


@router.get("/users/{user_id}", response_model=UserResponse)
def admin_get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("members")),
):
    """Chi tiết một thành viên."""
    user = crud.user.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy thành viên")
    return admin_panel_user_response(db, user)


@router.patch("/users/{user_id}", response_model=UserResponse)
def admin_update_user(
    user_id: int,
    data: UserAdminUpdate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("members")),
):
    """Cập nhật thành viên (trạng thái kích hoạt, tên, email, địa chỉ)."""
    user = crud.user.admin_update_user(db, user_id, data)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy thành viên")
    return admin_panel_user_response(db, user)


@router.delete("/users/{user_id}", status_code=204)
def admin_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: models.AdminUser = Depends(require_module_permission("members")),
):
    """Xóa vĩnh viễn tài khoản thành viên."""
    user = crud.user.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy thành viên")
    try:
        crud.user.delete_user(db, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        logger.exception("admin delete user %s failed", user_id)
        raise HTTPException(
            status_code=500,
            detail=f"Không thể xóa thành viên: {exc}",
        ) from exc


_LINK_STAFF_PAYLOAD_TO_ROLE = {
    "none": None,
    "order_manager": AdminRole.ORDER_MANAGER,
    "admin": AdminRole.ADMIN,
    "product_manager": AdminRole.PRODUCT_MANAGER,
    "content_manager": AdminRole.CONTENT_MANAGER,
}


@router.patch("/users/{user_id}/linked-staff", response_model=UserResponse)
def admin_patch_user_linked_staff(
    user_id: int,
    payload: UserLinkedStaffPayload,
    db: Session = Depends(get_db),
    _: models.AdminUser = Depends(require_privileged_admin),
):
    """Gán hoặc gỡ quyền vào admin qua đăng nhập shop (menu Quản trị web)."""
    user = crud.user.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy thành viên")
    target_role = _LINK_STAFF_PAYLOAD_TO_ROLE[payload.staff_role]
    try:
        apply_linked_staff_role(db, user, target_role, payload.modules)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.refresh(user)
    return admin_panel_user_response(db, user)


def _resolve_patch_admin_role(role_str: str) -> AdminRole:
    key = (role_str or "").strip().upper()
    if not key:
        raise HTTPException(status_code=400, detail="Thiếu vai trò")
    try:
        return AdminRole[key]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Vai trò không hợp lệ: {role_str}")


@router.get("/admin-users", response_model=AdminStaffAccountListResponse)
def admin_list_staff_accounts(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_privileged_admin),
):
    """Danh sách tài khoản admin (đăng nhập /admin) — chỉ quản trị chính."""
    rows = db.query(AdminUser).order_by(AdminUser.id.asc()).all()
    items: List[AdminStaffAccountRow] = []
    for u in rows:
        rv = u.role.value if hasattr(u.role, "value") else str(u.role)
        items.append(
            AdminStaffAccountRow(
                id=u.id,
                username=u.username,
                email=u.email or "",
                full_name=u.full_name,
                phone=u.phone,
                role=rv,
                is_active=bool(u.is_active),
                linked_user_id=u.linked_user_id,
                modules=effective_module_keys(u, db),
                uses_custom_modules=uses_custom_granular(u),
            )
        )
    return AdminStaffAccountListResponse(items=items)


@router.patch("/admin-users/{admin_id}/permissions", response_model=AdminStaffAccountRow)
def admin_patch_staff_account_permissions(
    admin_id: int,
    payload: AdminStaffPermissionsPatch,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(require_privileged_admin),
):
    """Đổi vai trò và/hoặc quyền mục (granular) cho một admin_users."""
    target = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản admin")
    if target.role == AdminRole.SUPER_ADMIN and current_admin.role != AdminRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Chỉ super_admin được chỉnh tài khoản super_admin")

    old_role = target.role
    role_changed = False
    if payload.role is not None and str(payload.role).strip():
        new_role = _resolve_patch_admin_role(str(payload.role))
        if new_role == AdminRole.SUPER_ADMIN and current_admin.role != AdminRole.SUPER_ADMIN:
            raise HTTPException(status_code=403, detail="Chỉ super_admin được gán vai trò super_admin")
        if new_role != old_role:
            role_changed = True
        target.role = new_role

    if target.role in (AdminRole.SUPER_ADMIN, AdminRole.ADMIN):
        target.granular_permissions = None
    elif payload.modules_mode == "custom":
        norm = normalize_module_list(payload.modules or [])
        if target.role not in (AdminRole.SUPER_ADMIN, AdminRole.ADMIN):
            norm = [x for x in norm if x != "staff_access"]
        target.granular_permissions = norm if norm else None
    elif payload.modules_mode == "preset" or role_changed:
        target.granular_permissions = None

    db.commit()
    db.refresh(target)

    rv = target.role.value if hasattr(target.role, "value") else str(target.role)
    return AdminStaffAccountRow(
        id=target.id,
        username=target.username,
        email=target.email or "",
        full_name=target.full_name,
        phone=target.phone,
        role=rv,
        is_active=bool(target.is_active),
        linked_user_id=target.linked_user_id,
        modules=effective_module_keys(target, db),
        uses_custom_modules=uses_custom_granular(target),
    )


@router.get("/staff-role-presets", response_model=StaffRolePresetListResponse)
def admin_list_staff_role_presets(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_privileged_admin),
):
    """Preset mục + CRUD cho NV — đọc được bởi quản trị chính; chỉnh bằng PUT (super_admin)."""
    ensure_default_staff_presets(db)
    items: List[StaffRolePresetItem] = []
    for role in sorted(PRESET_STAFF_ROLES, key=lambda r: r.value):
        data = get_staff_preset_payload(db, role.value)
        if data:
            items.append(
                StaffRolePresetItem(
                    role=data["role"],
                    modules=data["modules"],
                    module_crud={k: StaffRolePresetCrudFlags(**v) for k, v in data["module_crud"].items()},
                )
            )
    return StaffRolePresetListResponse(items=items)


@router.put("/staff-role-presets/{role}", response_model=StaffRolePresetItem)
def admin_put_staff_role_preset(
    role: str,
    payload: StaffRolePresetPutPayload,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_super_admin),
):
    raw_crud = {k: v.model_dump() for k, v in payload.module_crud.items()}
    try:
        upsert_staff_preset(db, role, payload.modules, raw_crud)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    data = get_staff_preset_payload(db, role.strip())
    if not data:
        raise HTTPException(status_code=404, detail="Không đọc lại được preset sau khi lưu")
    return StaffRolePresetItem(
        role=data["role"],
        modules=data["modules"],
        module_crud={k: StaffRolePresetCrudFlags(**v) for k, v in data["module_crud"].items()},
    )


# ========== SEARCH MAPPINGS ==========
@router.get("/search-mappings", response_model=SearchMappingListResponse)
def admin_list_search_mappings(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("search_mappings")),
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
    current_admin: models.AdminUser = Depends(require_module_permission("search_mappings")),
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
    current_admin: models.AdminUser = Depends(require_module_permission("search_mappings")),
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
    current_admin: models.AdminUser = Depends(require_module_permission("search_cache")),
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
    current_admin: models.AdminUser = Depends(require_module_permission("search_cache")),
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
                hint_query=(row.norm_q or "").strip()
                or product_search_cache_crud.hint_from_cached_json(body),
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
    current_admin: models.AdminUser = Depends(require_module_permission("search_cache")),
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


# ========== CACHE BỘ LỌC LISTING (danh mục / tìm kiếm / SEO cluster) ==========
def _facet_cache_row_item(row) -> ListingFacetCacheRowItem:
    return ListingFacetCacheRowItem(
        id=row.id,
        scope_type=row.scope_type,
        scope_key=row.scope_key,
        display_label=row.display_label,
        product_count=int(row.product_count or 0),
        sizes_count=len(row.sizes_json or []),
        colors_count=len(row.colors_json or []),
        style_tags_count=len(row.style_tags_json or []),
        price_min=row.price_min,
        price_max=row.price_max,
        is_manual=bool(row.is_manual),
        is_enabled=bool(row.is_enabled),
        is_stale=bool(row.is_stale),
        updated_at=row.updated_at,
        created_at=row.created_at,
    )


@router.get("/listing-facet-cache", response_model=ListingFacetCacheListResponse)
def admin_list_listing_facet_cache(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("listing_facet_cache")),
    scope_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    total, rows = listing_facet_cache_crud.list_rows_admin(
        db, scope_type=scope_type, skip=skip, limit=limit
    )
    counts = listing_facet_cache_crud.count_by_scope_type(db)
    return ListingFacetCacheListResponse(
        total_rows=total,
        counts_by_type=counts,
        items=[_facet_cache_row_item(r) for r in rows],
    )


@router.get("/listing-facet-cache/{row_id}", response_model=ListingFacetCacheDetailResponse)
def admin_get_listing_facet_cache(
    row_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("listing_facet_cache")),
):
    row = listing_facet_cache_crud.get_by_id(db, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy cache bộ lọc")
    facets = listing_facet_cache_crud.row_to_facets(row)
    return ListingFacetCacheDetailResponse(
        id=row.id,
        scope_type=row.scope_type,
        scope_key=row.scope_key,
        display_label=row.display_label,
        product_count=int(row.product_count or 0),
        facets=facets,
        is_manual=bool(row.is_manual),
        is_enabled=bool(row.is_enabled),
        is_stale=bool(row.is_stale),
        updated_at=row.updated_at,
        created_at=row.created_at,
    )


@router.post("/listing-facet-cache/rebuild", response_model=ListingFacetCacheRebuildResponse)
def admin_rebuild_listing_facet_cache(
    body: ListingFacetCacheRebuildRequest,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("listing_facet_cache")),
):
    from app.services import listing_facet_cache as lfc_service

    scope = (body.scope or "all").strip().lower()
    rebuilt = 0

    if scope == "single":
        st = (body.scope_type or "").strip()
        sk = (body.scope_key or "").strip()
        if not st or not sk:
            raise HTTPException(status_code=400, detail="scope_type và scope_key bắt buộc khi scope=single")
        if st == listing_facet_cache_crud.SCOPE_SEARCH_Q:
            if lfc_service.rebuild_search_scope(db, sk, is_manual=True):
                rebuilt = 1
        elif st.startswith("category_"):
            parts = sk.split("|")
            c1 = parts[0] if parts else ""
            c2 = parts[1] if len(parts) > 1 else None
            c3 = parts[2] if len(parts) > 2 else None
            if lfc_service.rebuild_category_scope(db, category=c1, subcategory=c2, sub_subcategory=c3):
                rebuilt = 1
        elif st == listing_facet_cache_crud.SCOPE_SEO_CLUSTER:
            if lfc_service.rebuild_seo_cluster_scope(db, sk):
                rebuilt = 1
        else:
            raise HTTPException(status_code=400, detail=f"scope_type không hỗ trợ: {st}")
        return ListingFacetCacheRebuildResponse(
            rebuilt=rebuilt,
            scope=scope,
            message=f"Đã rebuild {rebuilt} bộ lọc.",
        )

    if scope in ("category", "categories", "all"):
        rebuilt += lfc_service.rebuild_all_category_caches(db)
    if scope in ("search", "all"):
        rebuilt += lfc_service.rebuild_all_search_caches(db)
    if scope in ("seo_cluster", "seo", "all"):
        rebuilt += lfc_service.rebuild_all_seo_cluster_caches(db)

    if scope not in ("category", "categories", "search", "seo_cluster", "seo", "all"):
        raise HTTPException(
            status_code=400,
            detail='scope phải là category | search | seo_cluster | all | single',
        )

    return ListingFacetCacheRebuildResponse(
        rebuilt=rebuilt,
        scope=scope,
        message=f"Đã rebuild {rebuilt} bộ lọc ({scope}).",
    )


@router.post("/listing-facet-cache/pin-search", response_model=ListingFacetCacheDetailResponse)
def admin_pin_search_facet_cache(
    body: ListingFacetCachePinSearchRequest,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("listing_facet_cache")),
):
    from app.services import listing_facet_cache as lfc_service

    row = lfc_service.rebuild_search_scope(db, body.keyword.strip(), is_manual=True)
    if not row:
        raise HTTPException(
            status_code=400,
            detail="Không tạo được cache — kiểm tra từ khóa hoặc số sản phẩm (<200 nếu chưa pin thủ công).",
        )
    facets = listing_facet_cache_crud.row_to_facets(row)
    return ListingFacetCacheDetailResponse(
        id=row.id,
        scope_type=row.scope_type,
        scope_key=row.scope_key,
        display_label=row.display_label,
        product_count=int(row.product_count or 0),
        facets=facets,
        is_manual=bool(row.is_manual),
        is_enabled=bool(row.is_enabled),
        is_stale=bool(row.is_stale),
        updated_at=row.updated_at,
        created_at=row.created_at,
    )


@router.patch("/listing-facet-cache/{row_id}", response_model=ListingFacetCacheRowItem)
def admin_toggle_listing_facet_cache(
    row_id: int,
    body: ListingFacetCacheToggleRequest,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("listing_facet_cache")),
):
    row = listing_facet_cache_crud.set_enabled(db, row_id, body.is_enabled)
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy cache bộ lọc")
    return _facet_cache_row_item(row)


@router.delete("/listing-facet-cache/{row_id}", response_model=ListingFacetCacheClearResponse)
def admin_delete_listing_facet_cache_row(
    row_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("listing_facet_cache")),
):
    ok = listing_facet_cache_crud.delete_row(db, row_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy cache bộ lọc")
    return ListingFacetCacheClearResponse(deleted=1, scope_type=None)


@router.delete("/listing-facet-cache", response_model=ListingFacetCacheClearResponse)
def admin_clear_listing_facet_cache(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("listing_facet_cache")),
    scope_type: Optional[str] = Query(None),
):
    deleted = listing_facet_cache_crud.clear_by_scope_type(db, scope_type=scope_type)
    return ListingFacetCacheClearResponse(deleted=deleted, scope_type=scope_type)


# ========== MÃ NHÚNG (Google, Facebook, Zalo, GA4, GTM, Pixel...) ==========
@router.get("/site-embed-codes", response_model=List[SiteEmbedCodeAdminItem])
def admin_list_site_embed_codes(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("embed_codes")),
):
    rows = embed_crud.list_embed_codes(db, include_inactive=True)
    return [embed_crud.row_to_admin_item(r) for r in rows]


@router.post("/site-embed-codes", response_model=SiteEmbedCodeAdminItem)
def admin_create_site_embed_code(
    data: SiteEmbedCodeCreate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("embed_codes")),
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
    current_admin: models.AdminUser = Depends(require_module_permission("embed_codes")),
):
    row = embed_crud.update_embed_code(db, embed_id, data)
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy mã nhúng")
    return embed_crud.row_to_admin_item(row)


@router.delete("/site-embed-codes/{embed_id}", status_code=204)
def admin_delete_site_embed_code(
    embed_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("embed_codes")),
):
    ok = embed_crud.delete_embed_code(db, embed_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy mã nhúng")


# ========== Vị trí nút lướt video shop (FAB) ==========
@router.get("/shop-video-fab-settings", response_model=ShopVideoFabPublicOut)
def admin_get_shop_video_fab_settings(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("shop_video_fab")),
):
    row = shop_video_fab_crud.get_or_create_singleton(db)
    return shop_video_fab_crud.row_to_public_out(row)


@router.put("/shop-video-fab-settings", response_model=ShopVideoFabPublicOut)
def admin_put_shop_video_fab_settings(
    data: ShopVideoFabAdminUpdate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("shop_video_fab")),
):
    if not data.model_dump(exclude_unset=True):
        row = shop_video_fab_crud.get_or_create_singleton(db)
        return shop_video_fab_crud.row_to_public_out(row)
    return shop_video_fab_crud.update_singleton(db, data)


# ========== Bunny CDN — đăng ảnh lên Storage Zone ==========
@router.get("/bunny-cdn/status", response_model=BunnyCdnStatusOut)
def admin_bunny_cdn_status(current_admin: models.AdminUser = Depends(require_module_permission("bunny_cdn"))):
    z = (settings.BUNNY_STORAGE_ZONE_NAME or "").strip()
    k = (settings.BUNNY_STORAGE_ACCESS_KEY or "").strip()
    base = (settings.BUNNY_CDN_PUBLIC_BASE or "").strip()
    return BunnyCdnStatusOut(
        configured=bool(z and k and base),
        cdn_public_base=base,
        upload_path_prefix=(settings.BUNNY_UPLOAD_PATH_PREFIX or "").strip(),
    )


@router.post("/bunny-cdn/upload", response_model=BunnyCdnUploadOut)
async def admin_bunny_cdn_upload(
    file: UploadFile = File(...),
    subfolder: str = Form(""),
    current_admin: models.AdminUser = Depends(require_module_permission("bunny_cdn")),
):
    zone = (settings.BUNNY_STORAGE_ZONE_NAME or "").strip()
    key = (settings.BUNNY_STORAGE_ACCESS_KEY or "").strip()
    cdn_base = (settings.BUNNY_CDN_PUBLIC_BASE or "").strip()
    if not zone or not key or not cdn_base:
        raise HTTPException(
            status_code=503,
            detail="Chưa cấu hình Bunny: BUNNY_STORAGE_ZONE_NAME, BUNNY_STORAGE_ACCESS_KEY, BUNNY_CDN_PUBLIC_BASE trong .env backend.",
        )
    raw = await file.read()
    if len(raw) > _BUNNY_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Ảnh quá lớn (tối đa 15MB)")
    orig_name = file.filename or "image.png"
    ext = Path(orig_name).suffix.lower()
    if ext not in _BUNNY_IMAGE_EXT:
        raise HTTPException(
            status_code=400,
            detail="Chỉ chấp nhận ảnh: JPG, JPEG, PNG, GIF, WEBP",
        )
    if ext == ".webp":
        conv = raster_bytes_to_jpeg_bytes(raw)
        if not conv:
            raise HTTPException(
                status_code=400,
                detail="Không giải mã / chuyển WebP sang JPEG được — thử file khác hoặc xuất JPG từ máy.",
            )
        raw = conv
        ext = ".jpg"
        orig_name = f"{Path(orig_name).stem}.jpg"
    folder = _bunny_safe_subfolder(subfolder)
    prefix = (settings.BUNNY_UPLOAD_PATH_PREFIX or "site").strip().strip("/") or "site"
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    unique = uuid.uuid4().hex[:12]
    stem = Path(orig_name).stem.lower()
    stem_safe = re.sub(r"[^a-z0-9._-]", "_", stem)[:80] or "image"
    fname = f"{stem_safe}_{unique}{ext}"
    parts = [prefix]
    if folder:
        parts.append(folder)
    parts.extend([day, fname])
    remote = "/".join(parts)
    if ext in (".jpg", ".jpeg"):
        ct = "image/jpeg"
    else:
        ct = file.content_type or mimetypes.guess_type(fname)[0] or "application/octet-stream"
    try:
        upload_file_to_zone(
            zone_name=zone,
            access_key=key,
            remote_path=remote,
            data=raw,
            content_type=ct,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    url = build_public_object_url(cdn_base, remote)
    if not url:
        raise HTTPException(status_code=500, detail="Không tạo được URL public")
    return BunnyCdnUploadOut(public_url=url, remote_path=remote, bytes=len(raw))


def _integration_secret_configured(val: Optional[str], min_len: int = 8) -> bool:
    return len((val or "").strip()) >= min_len


def _google_sheets_credentials_configured() -> bool:
    raw = (settings.GOOGLE_SHEETS_SKU_CREDENTIALS_PATH or "").strip()
    if not raw:
        return False
    p = Path(raw)
    if p.is_file():
        return True
    p2 = _backend_root() / raw
    return p2.is_file()


@router.get("/integrations/api-keys-overview", response_model=AdminIntegrationKeysOverviewOut)
def admin_integrations_api_keys_overview(
    _: models.AdminUser = Depends(require_privileged_admin),
):
    """
    Trạng thái cấu hình các API key / bí mật tích hợp (chỉ super_admin / admin).
    Không bao giờ trả giá trị thật — chỉ có/không đủ cấu hình để vận hành.
    """
    z_bunny = (settings.BUNNY_STORAGE_ZONE_NAME or "").strip()
    k_bunny = (settings.BUNNY_STORAGE_ACCESS_KEY or "").strip()
    base_bunny = (settings.BUNNY_CDN_PUBLIC_BASE or "").strip()
    bunny_ok = bool(z_bunny and k_bunny and base_bunny)

    groups = [
        AdminIntegrationKeyGroup(
            title="AI & xử lý nội dung",
            items=[
                AdminIntegrationKeyRow(
                    env_var="DEEPSEEK_API_KEY",
                    label="DeepSeek (chat, taxonomy import, dịch variant…)",
                    configured=_integration_secret_configured(settings.DEEPSEEK_API_KEY),
                    hint="backend/.env",
                ),
                AdminIntegrationKeyRow(
                    env_var="GEMINI_API_KEY",
                    label="Google Gemini (SEO danh mục, gợi ý tìm kiếm, ảnh…)",
                    configured=_integration_secret_configured(settings.GEMINI_API_KEY),
                    hint="backend/.env",
                ),
                AdminIntegrationKeyRow(
                    env_var="OPENAI_API_KEY",
                    label="OpenAI (GPT Image — bản địa hóa ảnh)",
                    configured=_integration_secret_configured(settings.OPENAI_API_KEY),
                    hint="backend/.env",
                ),
            ],
        ),
        AdminIntegrationKeyGroup(
            title="Thanh toán SePay",
            items=[
                AdminIntegrationKeyRow(
                    env_var="SEPAY_WEBHOOK_API_KEY",
                    label="Webhook — Apikey / ?token= trên URL",
                    configured=_integration_secret_configured(settings.SEPAY_WEBHOOK_API_KEY, min_len=6)
                    or _integration_secret_configured(
                        next(
                            (
                                v
                                for vals in parse_qs(urlparse(settings.SEPAY_WEBHOOK_PUBLIC_URL or "").query).values()
                                for v in vals
                            ),
                            "",
                        ),
                        min_len=6,
                    ),
                    hint="Khớp token trên SePay (Authorization Apikey hoặc ?token=); có thể ghi token trong SEPAY_WEBHOOK_PUBLIC_URL.",
                ),
                AdminIntegrationKeyRow(
                    env_var="SEPAY_SECRET_KEY",
                    label="Secret merchant / ký API",
                    configured=_integration_secret_configured(settings.SEPAY_SECRET_KEY, min_len=6),
                    hint="backend/.env",
                ),
            ],
        ),
        AdminIntegrationKeyGroup(
            title="Lưu trữ & CDN",
            items=[
                AdminIntegrationKeyRow(
                    env_var="BUNNY_STORAGE_ACCESS_KEY",
                    label="Bunny Storage + Pull Zone",
                    configured=bunny_ok,
                    hint="Cần đủ: BUNNY_STORAGE_ZONE_NAME, BUNNY_STORAGE_ACCESS_KEY, BUNNY_CDN_PUBLIC_BASE",
                ),
            ],
        ),
        AdminIntegrationKeyGroup(
            title="Đăng nhập & OTP",
            items=[
                AdminIntegrationKeyRow(
                    env_var="GOOGLE_CLIENT_ID",
                    label="Google OAuth (đăng nhập web)",
                    configured=_integration_secret_configured(settings.GOOGLE_CLIENT_ID, min_len=16),
                    hint="backend/.env",
                ),
                AdminIntegrationKeyRow(
                    env_var="ZALO_OA_ACCESS_TOKEN",
                    label="Zalo OA — gửi OTP / template",
                    configured=_integration_secret_configured(settings.ZALO_OA_ACCESS_TOKEN, min_len=24),
                    hint="Nên cấu hình qua .env trên production.",
                ),
                AdminIntegrationKeyRow(
                    env_var="FIREBASE_PRIVATE_KEY",
                    label="Firebase Admin (private key service account)",
                    configured=_integration_secret_configured(settings.FIREBASE_PRIVATE_KEY, min_len=64),
                    hint="Dùng cho OTP Firebase phía server.",
                ),
            ],
        ),
        AdminIntegrationKeyGroup(
            title="Email & công cụ",
            items=[
                AdminIntegrationKeyRow(
                    env_var="SMTP_PASS",
                    label="SMTP — mật khẩu gửi email (SMTP_PASS hoặc SMTP_PASSWORD)",
                    configured=_integration_secret_configured(settings.SMTP_PASS, min_len=4),
                    hint="Cần kèm SMTP_HOST, SMTP_USER và địa chỉ gửi (SMTP_FROM / SENDER_EMAIL).",
                ),
                AdminIntegrationKeyRow(
                    env_var="GOOGLE_SHEETS_SKU_CREDENTIALS_PATH",
                    label="Google Sheets — file credentials đồng bộ SKU",
                    configured=_google_sheets_credentials_configured(),
                    hint="Đường dẫn file JSON (tuyệt đối hoặc tương đối thư mục backend).",
                ),
                AdminIntegrationKeyRow(
                    env_var="BROKEN_MEDIA_PURGE_SECRET",
                    label="Purge ảnh 404 — header X-Broken-Media-Purge-Key",
                    configured=_integration_secret_configured(settings.BROKEN_MEDIA_PURGE_SECRET, min_len=8),
                    hint="Chỉ cần nếu gọi API purge từ Next/server.",
                ),
            ],
        ),
    ]

    return AdminIntegrationKeysOverviewOut(
        groups=groups,
        disclaimer="Trang chỉ hiển thị đã cấu hình hay chưa — không đọc và không hiển thị giá trị bí mật. Sau khi sửa .env, cần khởi động lại backend.",
    )
