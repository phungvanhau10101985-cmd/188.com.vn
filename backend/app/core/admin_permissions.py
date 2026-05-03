"""Quyền admin theo mục (granular_permissions JSON) + preset theo AdminRole (DB admin_staff_role_presets)."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models.admin import AdminRole, AdminUser

ALLOWED_MODULE_KEYS: Set[str] = {
    "staff_access",
    "orders",
    "products",
    "taxonomy",
    "search_mappings",
    "search_cache",
    "category_seo",
    "bunny_cdn",
    "product_questions",
    "product_reviews",
    "members",
    "bank_accounts",
    "loyalty",
    "embed_codes",
    "chat_embeds",
    "shop_video_fab",
    "notifications",
}

LEGACY_ROLE_MODULES = {
    AdminRole.ORDER_MANAGER: frozenset({"orders"}),
    AdminRole.PRODUCT_MANAGER: frozenset(
        {
            "products",
            "taxonomy",
            "search_mappings",
            "search_cache",
            "category_seo",
            "bunny_cdn",
        }
    ),
    AdminRole.CONTENT_MANAGER: frozenset(
        {
            "product_questions",
            "product_reviews",
            "category_seo",
            "embed_codes",
            "chat_embeds",
        }
    ),
}

PRESET_STAFF_ROLES = frozenset(
    {AdminRole.ORDER_MANAGER, AdminRole.PRODUCT_MANAGER, AdminRole.CONTENT_MANAGER}
)

AdminCrudNeed = Literal["view", "create", "update", "delete"]


def http_method_to_admin_crud_need(method: str) -> AdminCrudNeed:
    m = (method or "GET").upper()
    if m in ("GET", "HEAD", "OPTIONS"):
        return "view"
    if m == "POST":
        return "create"
    if m in ("PUT", "PATCH"):
        return "update"
    if m == "DELETE":
        return "delete"
    return "view"


def _legacy_default_crud_flags(role: AdminRole, module_key: str) -> Dict[str, bool]:
    v, c, u, d = True, True, True, True
    if role == AdminRole.CONTENT_MANAGER and module_key in ("product_questions", "product_reviews"):
        d = False
    return {"view": v, "create": c, "update": u, "delete": d}


def _build_default_module_crud(role: AdminRole, module_keys: List[str]) -> Dict[str, Dict[str, bool]]:
    out: Dict[str, Dict[str, bool]] = {}
    for k in module_keys:
        out[k] = dict(_legacy_default_crud_flags(role, k))
    return out


def ensure_default_staff_presets(db: Session) -> None:
    """Khởi tạo 3 preset NV nếu chưa có (legacy bundles)."""
    from app.models.admin import AdminStaffRolePreset

    for role in PRESET_STAFF_ROLES:
        rv = role.value if hasattr(role, "value") else str(role)
        exists = db.query(AdminStaffRolePreset).filter(AdminStaffRolePreset.role == rv).first()
        if exists:
            continue
        mods = sorted(LEGACY_ROLE_MODULES.get(role, frozenset()) & ALLOWED_MODULE_KEYS)
        crud_map = _build_default_module_crud(role, mods)
        db.add(AdminStaffRolePreset(role=rv, modules=mods, module_crud=crud_map))
    db.commit()


def _preset_row(db: Session, role: AdminRole):
    from app.models.admin import AdminStaffRolePreset

    if role not in PRESET_STAFF_ROLES:
        return None
    rv = role.value if hasattr(role, "value") else str(role)
    return db.query(AdminStaffRolePreset).filter(AdminStaffRolePreset.role == rv).first()


def preset_module_bundle(db: Session, role: AdminRole) -> frozenset:
    ensure_default_staff_presets(db)
    row = _preset_row(db, role)
    if row and isinstance(row.modules, list) and row.modules:
        keys = normalize_module_list(list(row.modules))
        return frozenset(keys)
    return LEGACY_ROLE_MODULES.get(role, frozenset())


def _stored_crud_cell(row_crud: Any, module_key: str) -> Optional[Dict[str, Any]]:
    if not isinstance(row_crud, dict):
        return None
    raw = row_crud.get(module_key)
    return raw if isinstance(raw, dict) else None


def merged_preset_crud(db: Session, role: AdminRole, module_key: str) -> Dict[str, bool]:
    """CRUD hiệu lực cho một mục (preset NV, không áp dụng granular)."""
    base = _legacy_default_crud_flags(role, module_key)
    row = _preset_row(db, role)
    stored = _stored_crud_cell(getattr(row, "module_crud", None), module_key) if row else None
    if stored:
        for k in ("view", "create", "update", "delete"):
            if k in stored:
                base[k] = bool(stored[k])
    return base


def _parse_granular(raw: Any) -> Optional[Set[str]]:
    if raw is None:
        return None
    if isinstance(raw, list):
        keys = [str(x).strip() for x in raw if str(x).strip()]
        out = {k for k in keys if k in ALLOWED_MODULE_KEYS}
        return out if out else None
    return None


def admin_allowed_operation(admin: AdminUser, db: Session, module_key: str, need: AdminCrudNeed) -> bool:
    if module_key not in ALLOWED_MODULE_KEYS:
        return False
    if admin.role in (AdminRole.SUPER_ADMIN, AdminRole.ADMIN):
        return True
    gp = _parse_granular(getattr(admin, "granular_permissions", None))
    if gp is not None:
        return module_key in gp
    bundle = preset_module_bundle(db, admin.role)
    if module_key not in bundle:
        return False
    flags = merged_preset_crud(db, admin.role, module_key)
    return bool(flags.get(need))


def admin_has_module(admin: AdminUser, db: Session, module_key: str) -> bool:
    """Có quyền xem mục (menu / GET admin)."""
    return admin_allowed_operation(admin, db, module_key, "view")


def effective_module_keys(admin: AdminUser, db: Session) -> List[str]:
    """Danh sách mục hiển thị menu / kiểm tra quyền (đã chuẩn hoá)."""
    if admin.role in (AdminRole.SUPER_ADMIN, AdminRole.ADMIN):
        return sorted(ALLOWED_MODULE_KEYS)
    gp = _parse_granular(getattr(admin, "granular_permissions", None))
    if gp is not None:
        return sorted(gp & ALLOWED_MODULE_KEYS)
    bundle = preset_module_bundle(db, admin.role)
    out = [m for m in bundle if merged_preset_crud(db, admin.role, m).get("view")]
    return sorted(out)


def uses_custom_granular(admin: AdminUser) -> bool:
    """Có granular_permissions JSON hợp lệ và không rỗng (ghi đè preset theo role)."""
    return _parse_granular(getattr(admin, "granular_permissions", None)) is not None


def normalize_module_list(modules: Optional[List[str]]) -> List[str]:
    if not modules:
        return []
    out = sorted({str(m).strip() for m in modules if str(m).strip() and str(m).strip() in ALLOWED_MODULE_KEYS})
    return out


def list_staff_preset_roles_db(db: Session) -> List[str]:
    ensure_default_staff_presets(db)
    from app.models.admin import AdminStaffRolePreset

    rows = db.query(AdminStaffRolePreset.role).order_by(AdminStaffRolePreset.role.asc()).all()
    return [r[0] for r in rows]


def get_staff_preset_payload(db: Session, role_value: str):
    from app.models.admin import AdminStaffRolePreset

    ensure_default_staff_presets(db)
    row = db.query(AdminStaffRolePreset).filter(AdminStaffRolePreset.role == role_value.strip()).first()
    if not row:
        return None
    mods = normalize_module_list(list(row.modules or []))
    merged_crud: Dict[str, Dict[str, bool]] = {}
    role_enum = None
    try:
        role_enum = AdminRole(role_value)
    except ValueError:
        role_enum = None
    for k in mods:
        if role_enum and role_enum in PRESET_STAFF_ROLES:
            merged_crud[k] = merged_preset_crud(db, role_enum, k)
        else:
            merged_crud[k] = {"view": True, "create": True, "update": True, "delete": True}
    return {"role": row.role, "modules": mods, "module_crud": merged_crud}


def upsert_staff_preset(
    db: Session,
    role_value: str,
    modules: List[str],
    module_crud: Dict[str, Dict[str, Any]],
) -> Tuple[List[str], Dict[str, Dict[str, bool]]]:
    from app.models.admin import AdminStaffRolePreset

    rv = role_value.strip()
    try:
        role_enum = AdminRole(rv)
    except ValueError:
        raise ValueError(f"Vai trò preset không hợp lệ: {role_value}")
    if role_enum not in PRESET_STAFF_ROLES:
        raise ValueError("Chỉ chỉnh được preset NV: order_manager, product_manager, content_manager")

    norm_mods = normalize_module_list(modules)
    norm_mods = [x for x in norm_mods if x != "staff_access"]
    if not norm_mods:
        raise ValueError("Danh sách mục không được rỗng")

    built_crud: Dict[str, Dict[str, bool]] = {}
    for k in norm_mods:
        src = module_crud.get(k) if isinstance(module_crud, dict) else None
        base = _legacy_default_crud_flags(role_enum, k)
        if isinstance(src, dict):
            for op in ("view", "create", "update", "delete"):
                if op in src:
                    base[op] = bool(src[op])
        built_crud[k] = base

    row = db.query(AdminStaffRolePreset).filter(AdminStaffRolePreset.role == rv).first()
    if row:
        row.modules = norm_mods
        row.module_crud = built_crud
    else:
        db.add(AdminStaffRolePreset(role=rv, modules=norm_mods, module_crud=built_crud))
    db.commit()
    return norm_mods, built_crud
