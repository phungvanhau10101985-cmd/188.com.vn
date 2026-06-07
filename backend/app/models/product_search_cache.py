"""Cache kết quả tìm sản phẩm (theo q + filter + skip/limit) — dùng chung mọi khách."""

from sqlalchemy import Column, String, DateTime, Text, func

from app.db.base import Base


class ProductSearchCache(Base):
    __tablename__ = "product_search_cache"

    cache_key = Column(String(64), primary_key=True, index=True)
    response_json = Column(Text, nullable=False)
    # NULL = cache vĩnh viễn (mặc định); có giá trị = TTL legacy.
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    # Từ khóa chuẩn — dùng refresh khi SP liên quan thêm/xóa.
    norm_q = Column(String(500), nullable=True, index=True)
    # Tham số query (q, skip, limit, filter…) — replay khi làm mới cache.
    cache_query_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
