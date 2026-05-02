# Cài đặt vị trí nút nổi "lướt video shop" (singleton id=1).
from sqlalchemy import Column, Integer, DateTime
from sqlalchemy.sql import func

from app.db.base import Base


class ShopVideoFabSetting(Base):
    __tablename__ = "shop_video_fab_settings"

    id = Column(Integer, primary_key=True, index=True)
    right_mobile_px = Column(Integer, nullable=False, default=16)
    bottom_mobile_px_no_nav = Column(Integer, nullable=False, default=16)
    bottom_mobile_px_with_nav = Column(Integer, nullable=False, default=144)
    right_desktop_px = Column(Integer, nullable=False, default=32)
    bottom_desktop_px = Column(Integer, nullable=False, default=40)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<ShopVideoFabSetting id={self.id}>"
