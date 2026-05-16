# Trạng thái pause worker kiểm tra nguồn (singleton id=1 — lưu DB, áp cho mọi process đọc khi có quyền DB)
from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.db.base import Base


class SourceStockWorkerState(Base):
    __tablename__ = "source_stock_worker_state"

    id = Column(Integer, primary_key=True, index=True)  # luôn 1
    paused = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)

    checking_product_db_id = Column(Integer, nullable=True)
    checking_started_at = Column(DateTime(timezone=True), nullable=True)
    last_done_product_db_id = Column(Integer, nullable=True)
    last_done_finished_at = Column(DateTime(timezone=True), nullable=True)
    last_done_source_stock_status = Column(String(64), nullable=True)

    def __repr__(self):
        return f"<SourceStockWorkerState id={self.id} paused={self.paused}>"
