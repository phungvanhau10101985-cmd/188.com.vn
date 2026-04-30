# backend/app/models/seo_cluster.py - SEO landing cluster
"""
SeoCluster: nhóm các cat3 trùng ý định tìm kiếm về 1 landing duy nhất.
- URL chính: /c/<slug>
- Cat3 nào có cluster sẽ noindex + redirect 301 về /c/<slug>.
- Mỗi cat3 mặc định 1 cluster (1:1), admin có thể gom thủ công sau.

Khoá ổn định:
- `external_id`: id chuỗi từ taxonomy_import.xlsx (vd `cluster__giay-chay-bo-nam-road`).
  Dùng để upsert lúc re-import — không phụ thuộc auto-increment id.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.base import Base


class SeoCluster(Base):
    __tablename__ = "seo_clusters"

    id = Column(Integer, primary_key=True, index=True)

    external_id = Column(String(200), unique=True, index=True, nullable=False)
    slug = Column(String(300), unique=True, index=True, nullable=False)
    name = Column(String(500), nullable=False)
    canonical_path = Column(String(500), nullable=False)
    index_policy = Column(String(20), default="index", nullable=False)
    source = Column(String(50), default="auto_from_cat3")
    notes = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    categories = relationship(
        "Category",
        back_populates="seo_cluster",
        foreign_keys="[Category.seo_cluster_id]",
    )

    def __repr__(self):
        return f"<SeoCluster {self.slug} ({self.index_policy})>"
