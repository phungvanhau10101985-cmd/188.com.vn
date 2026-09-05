from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.db.base import Base


class MarketingBannerAsset(Base):
    """Ảnh banner AI dùng lại theo ngày-tháng và mức giảm thực tế."""

    __tablename__ = "marketing_banner_assets"
    __table_args__ = (
        UniqueConstraint(
            "kind",
            "campaign_key",
            "version",
            name="uq_marketing_banner_campaign_version",
        ),
        Index(
            "ix_marketing_banner_active_campaign",
            "kind",
            "campaign_key",
            "is_active",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(20), nullable=False, index=True)  # sale | birthday
    campaign_key = Column(String(100), nullable=False, index=True)
    date_key = Column(String(5), nullable=False, index=True)  # MM-DD
    discount_percent = Column(Numeric(5, 2), nullable=False)
    image_url = Column(String(1000), nullable=True)
    aspect_ratio = Column(String(10), nullable=False, default="21:9")
    image_width = Column(Integer, nullable=True)
    image_height = Column(Integer, nullable=True)
    prompt = Column(Text, nullable=False)
    provider = Column(String(30), nullable=False, default="gemini")
    model = Column(String(120), nullable=False)
    status = Column(String(20), nullable=False, default="generating", index=True)
    error_message = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=False, index=True)
    generated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
