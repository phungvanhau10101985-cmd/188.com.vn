from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Import1688JobCreate(BaseModel):
    url: str = Field(..., min_length=10)
    download_images: bool = True
    source: Optional[str] = None


class ProductImportDraftUpdate(BaseModel):
    product_data: Dict[str, Any]


class ProductImportDraftOut(BaseModel):
    id: int
    job_id: str
    source: str = "1688"
    source_url: str
    source_offer_id: Optional[str] = None
    status: str
    phase: Optional[str] = None
    message: Optional[str] = None
    percent: Optional[int] = None
    raw_payload: Optional[Dict[str, Any]] = None
    product_data: Optional[Dict[str, Any]] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    published_product_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Import1688JobOut(BaseModel):
    job_id: str
    status: str
    phase: Optional[str] = None
    message: Optional[str] = None
    percent: Optional[int] = None
    draft_id: Optional[int] = None
    product_data: Optional[Dict[str, Any]] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    published_product_id: Optional[str] = None
    created_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class Import1688ExcelBatchOut(BaseModel):
    batch_token: str
    total: int
    draft_ids: List[int] = Field(default_factory=list)
    job_ids: List[str] = Field(default_factory=list)
    skipped: List[str] = Field(default_factory=list)


class Import1688BatchStatusItem(BaseModel):
    draft_id: int
    job_id: str
    excel_row: Optional[int] = None
    status: str
    phase: Optional[str] = None
    message: Optional[str] = None


class Import1688BatchStatusOut(BaseModel):
    batch_token: str
    total: int
    completed: int = 0
    failed: int = 0
    pending: int = 0
    items: List[Import1688BatchStatusItem] = Field(default_factory=list)


class Import1688ExcelBatchSummaryOut(BaseModel):
    """Một đợt upload Excel (theo file meta trên disk)."""

    batch_token: str
    created_at: Optional[str] = None
    total_links: int = 0
    completed: int = 0
    failed: int = 0
    pending: int = 0
    skipped_lines: int = 0


class Import1688ExcelBatchListOut(BaseModel):
    items: List[Import1688ExcelBatchSummaryOut] = Field(default_factory=list)
    limit: int


class Import1688ExcelBatchDeleteOut(BaseModel):
    success: bool = True
    batch_token: str
    draft_ids_deleted: List[int] = Field(default_factory=list)
    meta_removed: bool = False


class Import1688BatchResumeOut(BaseModel):
    """POST resume batch — có thể không còn pending hoặc đã xếp hàng chạy tiếp."""

    success: bool = True
    message: str = ""
    pending: int = 0


class Import1688DraftListOut(BaseModel):
    items: List[ProductImportDraftOut]
    total: int
    limit: int
    offset: int


class Import1688DraftIdsBody(BaseModel):
    draft_ids: List[int] = Field(..., min_length=1, max_length=500)


class ListingImportQueueTaskIn(BaseModel):
    url: str = Field(..., min_length=10)
    source: Optional[str] = "hibox"
    label: Optional[str] = None


class ListingImportQueueEnqueueIn(BaseModel):
    """Thêm link vào hàng đợi server-side; xử lý tuần tự."""

    queue_token: Optional[str] = None
    items: List[ListingImportQueueTaskIn] = Field(..., min_length=1)


class ListingImportQueueEnqueueOut(BaseModel):
    queue_token: str
    added: int
    message: str


class ListingImportQueueActionMessage(BaseModel):
    queue_token: str
    message: str


class ListingImportQueueRunCounts(BaseModel):
    total: int = 0
    done: int = 0
    error: int = 0
    pending: int = 0
    running: int = 0


class ListingImportQueueRunSummary(BaseModel):
    queue_token: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    run_status: str = ""
    pause_requested: bool = False
    stop_requested: bool = False
    worker_alive: bool = False
    counts: ListingImportQueueRunCounts


class ListingImportQueueRunsOut(BaseModel):
    items: List[ListingImportQueueRunSummary]
    total: int
    limit: int
    offset: int


class ListingImportQueueDeleteOut(BaseModel):
    queue_token: str
    deleted: bool = True
