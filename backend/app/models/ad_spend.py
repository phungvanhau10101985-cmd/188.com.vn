"""Khóa đọc chi phí Google Ads và Facebook Ads — một dòng cấu hình."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.sql import func

from app.db.base import Base


class AdSpendSettings(Base):
    __tablename__ = "ad_spend_settings"

    id = Column(Integer, primary_key=True, default=1)
    google_developer_token = Column(Text, nullable=True)
    google_client_id = Column(Text, nullable=True)
    google_client_secret = Column(Text, nullable=True)
    google_refresh_token = Column(Text, nullable=True)
    google_customer_id = Column(Text, nullable=True)
    google_login_customer_id = Column(Text, nullable=True)
    meta_access_token = Column(Text, nullable=True)
    meta_ad_account_id = Column(Text, nullable=True)
    vnd_per_cny = Column(Numeric(14, 4), nullable=True)
    ship_china_domestic_cny = Column(Numeric(14, 2), nullable=True)
    ship_border_to_hanoi_cny = Column(Numeric(14, 2), nullable=True)
    ship_hanoi_to_customer_vnd = Column(Numeric(14, 2), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AdSpendOrderCost(Base):
    """Giá tệ và ship riêng từng đơn — ô trống trên form thì dùng mức chung."""

    __tablename__ = "ad_spend_order_costs"

    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True)
    goods_cny = Column(Numeric(14, 2), nullable=True)
    ship_china_domestic_cny = Column(Numeric(14, 2), nullable=True)
    ship_border_to_hanoi_cny = Column(Numeric(14, 2), nullable=True)
    ship_hanoi_to_customer_vnd = Column(Numeric(14, 2), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
