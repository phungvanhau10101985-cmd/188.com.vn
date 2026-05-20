"""Job bản địa hóa ảnh — persist để poll sau restart và resume worker."""

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.db.base import Base


class ImageLocalizationJob(Base):
    __tablename__ = "image_localization_jobs"

    job_id = Column(String(64), primary_key=True)
    status = Column(String(32), default="queued", index=True, nullable=False)
    phase = Column(String(64), default="queued")
    message = Column(Text)

    payload = Column(JSON, nullable=True)

    current = Column(Integer, default=0)
    total = Column(Integer, nullable=True)
    done = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    percent = Column(Float, nullable=True)

    current_product_id = Column(String(255), nullable=True, index=True)
    cancel_requested = Column(Boolean, default=False, nullable=False)

    queue_product_ids = Column(JSON, default=list)
    processed_product_ids = Column(JSON, default=list)
    job_queue_truncated = Column(Boolean, default=False)

    recent_results = Column(JSON, default=list)
    skipped_product_reports = Column(JSON, default=list)

    language = Column(String(20), nullable=True)
    force = Column(Boolean, default=False)
    dry_run = Column(Boolean, default=False)
    gemini_mode = Column(String(20), nullable=True)
    local_image_only = Column(Boolean, default=False)

    resume_count = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
