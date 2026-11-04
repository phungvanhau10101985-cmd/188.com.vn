# Mức cọc một phần (singleton id=1). 100% vẫn là lựa chọn riêng khi khách thanh toán.
from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.sql import func

from app.db.base import Base


class DepositSettings(Base):
    __tablename__ = "deposit_settings"

    id = Column(Integer, primary_key=True, index=True)
    partial_percent = Column(Integer, nullable=False, default=30)
    # Sàn tiền cọc một phần (VND). Không thấp hơn 100.000.
    min_amount = Column(Integer, nullable=False, default=100_000)
    # Giá trị hàng từ mốc này thì cọc một phần không thấp hơn 30%.
    high_order_amount = Column(Integer, nullable=False, default=3_000_000)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return (
            f"<DepositSettings id={self.id} partial_percent={self.partial_percent} "
            f"min_amount={self.min_amount}>"
        )
