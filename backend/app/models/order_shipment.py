from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.sql import func

from app.db.base import Base


class OrderShipmentEvent(Base):
    __tablename__ = "order_shipment_events"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    step_key = Column(String(40), nullable=False, index=True)
    title = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending", index=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=True, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    note = Column(Text, nullable=True)
    updated_by_admin_id = Column(Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EmsShippingRecord(Base):
    """Bảng quản lý vận chuyển EMS — import từ file gui ems.xlsx."""

    __tablename__ = "ems_shipping_records"

    id = Column(Integer, primary_key=True, index=True)
    reference_code = Column(String(50), nullable=False, unique=True, index=True)
    recipient_label = Column(Text, nullable=True)
    order_code = Column(String(50), nullable=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True)
    excel_row_number = Column(Integer, nullable=True)
    order_status = Column(String(40), nullable=True)
    current_step_key = Column(String(40), nullable=True)
    tracking_number_saved = Column(String(100), nullable=True)
    ems_tracking_code = Column(String(50), nullable=True, index=True)
    ems_reference_code = Column(String(50), nullable=True)
    ems_status = Column(Text, nullable=True)
    ems_phase = Column(String(40), nullable=True)
    sync_status = Column(String(40), nullable=False, default="pending", index=True)
    sync_message = Column(Text, nullable=True)
    ems_error = Column(Text, nullable=True)
    cod_amount = Column(Numeric(15, 0), nullable=True)
    cod_paid_amount = Column(Numeric(15, 0), nullable=True)
    cod_paid_date = Column(Date, nullable=True, index=True)
    cod_settlement_status = Column(String(40), nullable=True, index=True)
    cod_settlement_message = Column(Text, nullable=True)
    freight_amount = Column(Numeric(15, 0), nullable=True)
    freight_settled_at = Column(DateTime(timezone=True), nullable=True, index=True)
    freight_settlement_status = Column(String(40), nullable=True, index=True)
    freight_settlement_message = Column(Text, nullable=True)
    freight_high_fee_warning = Column(String(5), nullable=True)
    import_source_filename = Column(String(255), nullable=True)
    imported_by_admin_id = Column(Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class EmsShippingImportBatch(Base):
    """Lần import file gửi EMS (file gui ems.xlsx) — báo cáo có thể mở lại."""

    __tablename__ = "ems_shipping_import_batches"

    id = Column(Integer, primary_key=True, index=True)
    source_filename = Column(String(255), nullable=True)
    imported_by_admin_id = Column(Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    file_rows_processed = Column(Integer, nullable=False, default=0)
    order_count = Column(Integer, nullable=False, default=0)
    created_count = Column(Integer, nullable=False, default=0)
    updated_count = Column(Integer, nullable=False, default=0)
    skipped_no_reference_count = Column(Integer, nullable=False, default=0)
    orders_synced_count = Column(Integer, nullable=False, default=0)
    total_cod_amount = Column(Numeric(15, 0), nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EmsShippingImportBatchRow(Base):
    """Từng dòng trong báo cáo một lần import EMS."""

    __tablename__ = "ems_shipping_import_batch_rows"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(
        Integer,
        ForeignKey("ems_shipping_import_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ems_shipping_record_id = Column(
        Integer,
        ForeignKey("ems_shipping_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    excel_row_number = Column(Integer, nullable=True)
    reference_code = Column(String(50), nullable=True, index=True)
    recipient_label = Column(Text, nullable=True)
    order_code = Column(String(50), nullable=True)
    order_id = Column(Integer, nullable=True)
    cod_amount = Column(Numeric(15, 0), nullable=True)
    import_action = Column(String(20), nullable=True)
    sync_status = Column(String(40), nullable=True)
    sync_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EmsCodSettlementBatch(Base):
    """Lần import file đối soát COD đã thanh toán (Doi soat cod)."""

    __tablename__ = "ems_cod_settlement_batches"

    id = Column(Integer, primary_key=True, index=True)
    payment_date = Column(Date, nullable=False, index=True)
    source_filename = Column(String(255), nullable=True)
    imported_by_admin_id = Column(Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    total_rows = Column(Integer, nullable=False, default=0)
    matched_count = Column(Integer, nullable=False, default=0)
    amount_mismatch_count = Column(Integer, nullable=False, default=0)
    record_not_found_count = Column(Integer, nullable=False, default=0)
    parse_error_count = Column(Integer, nullable=False, default=0)
    total_paid_amount = Column(Numeric(15, 0), nullable=False, default=0)
    total_db_cod_amount = Column(Numeric(15, 0), nullable=False, default=0)
    total_amount_difference = Column(Numeric(15, 0), nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EmsCodSettlementRow(Base):
    """Từng dòng đối soát COD trong một lần import."""

    __tablename__ = "ems_cod_settlement_rows"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(
        Integer,
        ForeignKey("ems_cod_settlement_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    excel_row_number = Column(Integer, nullable=True)
    ems_reference_code = Column(String(50), nullable=True, index=True)
    ems_tracking_code = Column(String(50), nullable=True, index=True)
    paid_amount = Column(Numeric(15, 0), nullable=True)
    ems_shipping_record_id = Column(
        Integer,
        ForeignKey("ems_shipping_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    db_cod_amount = Column(Numeric(15, 0), nullable=True)
    amount_difference = Column(Numeric(15, 0), nullable=True)
    reconcile_status = Column(String(40), nullable=False, default="pending", index=True)
    reconcile_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EmsFreightSettlementBatch(Base):
    """Lần import file đối soát cước EMS (Doi soat cuoc)."""

    __tablename__ = "ems_freight_settlement_batches"

    id = Column(Integer, primary_key=True, index=True)
    source_filename = Column(String(255), nullable=True)
    imported_by_admin_id = Column(Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    total_rows = Column(Integer, nullable=False, default=0)
    settled_count = Column(Integer, nullable=False, default=0)
    record_not_found_count = Column(Integer, nullable=False, default=0)
    already_settled_count = Column(Integer, nullable=False, default=0)
    parse_error_count = Column(Integer, nullable=False, default=0)
    high_fee_warning_count = Column(Integer, nullable=False, default=0)
    total_freight_amount = Column(Numeric(15, 0), nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EmsFreightSettlementRow(Base):
    """Từng dòng đối soát cước trong một lần import."""

    __tablename__ = "ems_freight_settlement_rows"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(
        Integer,
        ForeignKey("ems_freight_settlement_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    excel_row_number = Column(Integer, nullable=True)
    ems_tracking_code = Column(String(50), nullable=True, index=True)
    freight_amount = Column(Numeric(15, 0), nullable=True)
    ems_shipping_record_id = Column(
        Integer,
        ForeignKey("ems_shipping_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    high_fee_warning = Column(String(5), nullable=True)
    reconcile_status = Column(String(40), nullable=False, default="pending", index=True)
    reconcile_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
