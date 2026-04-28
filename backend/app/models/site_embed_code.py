# Mã nhúng site (GA4, GTM, Pixel, Zalo, xác minh...) — quản trị trong admin
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base


class SiteEmbedCode(Base):
    __tablename__ = "site_embed_codes"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(32), nullable=False, index=True)  # google | facebook | tiktok | zalo | other
    category = Column(String(64), nullable=False, default="custom")  # ga4, gtm, pixel, verification, ...
    title = Column(String(255), nullable=False)
    placement = Column(String(32), nullable=False)  # head | body_open | body_close
    content = Column(Text, nullable=True, default="")
    hint = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<SiteEmbedCode {self.platform} {self.title}>"
