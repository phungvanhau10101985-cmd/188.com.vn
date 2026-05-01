"""Cache kết quả tìm sản phẩm (theo q + filter + skip/limit) — dùng chung mọi khách."""

from sqlalchemy import Column, String, DateTime, Text, func

from app.db.base import Base


class ProductSearchCache(Base):
    __tablename__ = "product_search_cache"

    cache_key = Column(String(64), primary_key=True, index=True)
    response_json = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
