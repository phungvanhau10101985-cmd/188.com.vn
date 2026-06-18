from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class VpsBackupSettingsResponse(BaseModel):
    enabled: bool
    hour: int
    minute: int
    days_of_week: List[int]
    keep_count: int = 2
    include_cache: bool
    notify_on_complete: bool = True
    last_triggered_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    backup_available: bool
    backup_root: str
    script_path: str
    drive_upload_enabled: bool = False
    drive_upload_configured: bool = False
    drive_folder_id: Optional[str] = None
    drive_keep_count: int = 5
    drive_credentials_configured: bool = False
    drive_service_account_email: Optional[str] = None


class VpsBackupSettingsUpdate(BaseModel):
    enabled: bool = False
    hour: int = Field(ge=0, le=23, default=3)
    minute: int = Field(ge=0, le=59, default=0)
    days_of_week: List[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    include_cache: bool = False


class VpsBackupRunItem(BaseModel):
    id: int
    trigger: str
    status: str
    archive_filename: Optional[str] = None
    archive_path: Optional[str] = None
    archive_size_bytes: Optional[int] = None
    archive_size_pretty: Optional[str] = None
    keep_count: Optional[int] = None
    include_cache: bool
    error_message: Optional[str] = None
    drive_upload_status: Optional[str] = None
    drive_web_link: Optional[str] = None
    drive_upload_error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime


class VpsBackupRunListResponse(BaseModel):
    total: int
    items: List[VpsBackupRunItem]


class VpsBackupArchiveItem(BaseModel):
    filename: str
    path: str
    size_bytes: int
    size_pretty: str
    modified_at: datetime
    linked_run_id: Optional[int] = None


class VpsBackupArchiveListResponse(BaseModel):
    total: int
    total_size_bytes: int
    total_size_pretty: str
    items: List[VpsBackupArchiveItem]


class VpsBackupTriggerResponse(BaseModel):
    run_id: int
    status: str
    message: str


class VpsBackupDeleteArchiveResponse(BaseModel):
    deleted: bool
    filename: str
