# backend/app/schemas/admin.py
from pydantic import BaseModel, Field
from typing import Optional, Literal, List

class AdminLogin(BaseModel):
    username: str = Field(..., description="Tên đăng nhập")
    password: str = Field(..., description="Mật khẩu")

class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    admin_id: int
    username: str
    role: str
    modules: Optional[List[str]] = Field(None, description="Mục được phép (menu); null nếu không trả")

class AdminCreate(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: str = "admin"
    linked_user_id: Optional[int] = Field(None, description="users.id — đăng nhập khách có thể vào admin qua menu")

class AdminUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class AdminStaffAccountRow(BaseModel):
    """Một dòng tài khoản trong bảng admin_users (quản trị viên / nhân viên)."""

    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: str
    is_active: bool
    linked_user_id: Optional[int] = Field(None, description="Liên kết users.id nếu đăng nhập qua shop")
    modules: List[str] = Field(default_factory=list, description="Quyền mục hiệu lực (menu)")
    uses_custom_modules: bool = Field(False, description="True nếu đang dùng granular_permissions")


class AdminStaffAccountListResponse(BaseModel):
    items: List[AdminStaffAccountRow]


class AdminStaffPermissionsPatch(BaseModel):
    """Đổi vai trò và/hoặc quyền mục cho admin_users — chỉ super_admin/admin."""

    role: Optional[str] = Field(None, description="Để trống = giữ vai trò")
    modules_mode: Literal["unchanged", "preset", "custom"] = "unchanged"
    modules: Optional[List[str]] = Field(
        None,
        description='modules_mode="custom": danh sách khóa trong ALLOWED_MODULE_KEYS (trừ staff_access thường không cần)',
    )


class UserLinkedStaffPayload(BaseModel):
    """Gán quyền quản trị web cho thành viên (đăng nhập shop → menu Quản trị). Chỉ super_admin/admin gọi được."""
    staff_role: Literal["none", "order_manager", "admin", "product_manager", "content_manager"]
    modules: Optional[List[str]] = Field(
        None,
        description="null = preset theo staff_role; danh sách khác rỗng = tùy chỉnh từng mục (khóa ALLOWED_MODULE_KEYS)",
    )


class StaffRolePresetCrudFlags(BaseModel):
    view: bool = True
    create: bool = True
    update: bool = True
    delete: bool = True


class StaffRolePresetItem(BaseModel):
    role: str
    modules: List[str]
    module_crud: dict[str, StaffRolePresetCrudFlags]


class StaffRolePresetListResponse(BaseModel):
    items: List[StaffRolePresetItem]


class StaffRolePresetPutPayload(BaseModel):
    modules: List[str]
    module_crud: dict[str, StaffRolePresetCrudFlags]
