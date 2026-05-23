from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ShipmentEventResponse(BaseModel):
    step_key: str
    title: str
    status: str
    scheduled_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    note: Optional[str] = None


class EmsTrackingEventResponse(BaseModel):
    status_code: Optional[int] = None
    description: str
    address: Optional[str] = None
    traced_at: Optional[datetime] = None


class EmsTrackingResponse(BaseModel):
    available: bool = False
    tracking_code: Optional[str] = None
    current_status: Optional[int] = None
    current_status_description: Optional[str] = None
    events: List[EmsTrackingEventResponse] = []
    error: Optional[str] = None


class OrderShipmentTimelineResponse(BaseModel):
    order_id: int
    order_code: str
    order_status: str
    tracking_number: Optional[str] = None
    shipping_provider: Optional[str] = None
    footer_note: str
    current_step_key: Optional[str] = None
    waiting_admin_at_customs: bool = False
    waiting_admin_domestic_delivery: bool = False
    can_confirm_received: bool = False
    events: List[ShipmentEventResponse]
    ems_tracking: Optional[EmsTrackingResponse] = None


class AdminClearCustomsIn(BaseModel):
    pass


class AdminApproveReturnReceivedIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class AdminMarkOutForConfirmIn(BaseModel):
    tracking_number: Optional[str] = Field(default=None, max_length=100)
    shipping_provider: Optional[str] = Field(default=None, max_length=100)


class EmsShippingOperationsStatsResponse(BaseModel):
    shipping_orders: int = 0
    delivered_success_orders: int = 0
    returned_orders: int = 0
    cod_success_unpaid_count: int = 0
    cod_success_unpaid_total: int = 0
    cod_success_paid_count: int = 0
    cod_success_paid_total: int = 0
    shipping_cod_unpaid_count: int = 0
    freight_unsettled_count: int = 0


class EmsShippingDeleteRequest(BaseModel):
    ids: List[int] = Field(..., min_length=1)


class EmsShippingDeleteResponse(BaseModel):
    ok: bool = True
    deleted: int


class EmsShippingImportRowResponse(BaseModel):
    id: Optional[int] = None
    row_number: int
    reference_code: str
    recipient_label: str
    order_code: Optional[str] = None
    order_id: Optional[int] = None
    order_status: Optional[str] = None
    current_step_key: Optional[str] = None
    tracking_number_saved: Optional[str] = None
    ems_tracking_code: Optional[str] = None
    ems_reference_code: Optional[str] = None
    ems_status: Optional[str] = None
    ems_phase: Optional[str] = None
    sync_status: str
    sync_message: str
    ems_error: Optional[str] = None
    cod_amount: Optional[int] = None
    cod_paid_amount: Optional[int] = None
    cod_paid_date: Optional[str] = None
    cod_settlement_status: Optional[str] = None
    cod_settlement_message: Optional[str] = None
    freight_amount: Optional[int] = None
    freight_settled_at: Optional[str] = None
    freight_settlement_status: Optional[str] = None
    freight_settlement_message: Optional[str] = None
    freight_high_fee_warning: Optional[str] = None


class EmsShippingBreakdownItem(BaseModel):
    key: str
    count: int
    cod_total: int = 0


class EmsShippingImportSummaryResponse(BaseModel):
    total_rows: int
    matched: int
    in_progress: int
    mismatch: int
    unlinked: int = 0
    order_not_found: int
    ems_not_found: int
    parse_error: int
    total_cod_amount: int = 0
    breakdown: List[EmsShippingBreakdownItem] = []


class EmsShippingImportStatsResponse(BaseModel):
    """Thống kê lần import vừa chạy (upsert theo mã tham chiếu)."""
    file_rows_processed: int = 0
    created: int = 0
    updated: int = 0
    skipped_no_reference: int = 0
    orders_synced: int = 0


class EmsShippingImportResponse(BaseModel):
    ok: bool = True
    warnings: List[str] = []
    summary: EmsShippingImportSummaryResponse
    import_stats: Optional[EmsShippingImportStatsResponse] = None
    tracking_refresh_job_id: Optional[str] = None
    rows: List[EmsShippingImportRowResponse]


class EmsTrackingRefreshJobResponse(BaseModel):
    job_id: str
    status: str
    source: Optional[str] = None
    total: int = 0
    processed: int = 0
    ok: int = 0
    errors: int = 0
    message: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class EmsTrackingRefreshEnqueueResponse(BaseModel):
    ok: bool = True
    job_id: Optional[str] = None
    queued: int = 0
    message: str = ""


class EmsCodSettlementRowResponse(BaseModel):
    id: Optional[int] = None
    batch_id: Optional[int] = None
    row_number: int
    ems_reference_code: Optional[str] = None
    ems_tracking_code: Optional[str] = None
    paid_amount: Optional[int] = None
    ems_shipping_record_id: Optional[int] = None
    db_cod_amount: Optional[int] = None
    amount_difference: Optional[int] = None
    reconcile_status: str
    reconcile_message: str = ""


class EmsCodSettlementBreakdownItem(BaseModel):
    key: str
    count: int
    paid_total: int = 0
    db_cod_total: int = 0


class EmsCodSettlementSummaryResponse(BaseModel):
    total_rows: int
    matched: int
    amount_mismatch: int
    record_not_found: int
    parse_error: int
    total_paid_amount: int = 0
    total_db_cod_amount: int = 0
    total_amount_difference: int = 0
    breakdown: List[EmsCodSettlementBreakdownItem] = []


class EmsCodSettlementBatchResponse(BaseModel):
    id: int
    payment_date: Optional[str] = None
    source_filename: Optional[str] = None
    total_rows: int
    matched_count: int
    amount_mismatch_count: int
    record_not_found_count: int
    parse_error_count: int
    total_paid_amount: int = 0
    total_db_cod_amount: int = 0
    total_amount_difference: int = 0
    created_at: Optional[str] = None
    rows: List[EmsCodSettlementRowResponse] = []


class EmsCodSettlementImportResponse(BaseModel):
    ok: bool = True
    warnings: List[str] = []
    summary: EmsCodSettlementSummaryResponse
    import_batch: Optional[EmsCodSettlementBatchResponse] = None
    batches: List[EmsCodSettlementBatchResponse] = []


class EmsFreightSettlementRowResponse(BaseModel):
    id: Optional[int] = None
    batch_id: Optional[int] = None
    row_number: int
    ems_tracking_code: Optional[str] = None
    freight_amount: Optional[int] = None
    ems_shipping_record_id: Optional[int] = None
    high_fee_warning: Optional[str] = None
    reconcile_status: str
    reconcile_message: str = ""


class EmsFreightSettlementBreakdownItem(BaseModel):
    key: str
    count: int
    freight_total: int = 0


class EmsFreightSettlementSummaryResponse(BaseModel):
    total_rows: int
    settled: int
    already_settled: int
    record_not_found: int
    parse_error: int
    high_fee_warning_count: int = 0
    total_freight_amount: int = 0
    breakdown: List[EmsFreightSettlementBreakdownItem] = []


class EmsFreightSettlementBatchResponse(BaseModel):
    id: int
    source_filename: Optional[str] = None
    total_rows: int
    settled_count: int
    record_not_found_count: int
    already_settled_count: int
    parse_error_count: int
    high_fee_warning_count: int = 0
    total_freight_amount: int = 0
    created_at: Optional[str] = None
    rows: List[EmsFreightSettlementRowResponse] = []


class EmsFreightSettlementImportResponse(BaseModel):
    ok: bool = True
    warnings: List[str] = []
    summary: EmsFreightSettlementSummaryResponse
    import_batch: Optional[EmsFreightSettlementBatchResponse] = None
    batches: List[EmsFreightSettlementBatchResponse] = []
