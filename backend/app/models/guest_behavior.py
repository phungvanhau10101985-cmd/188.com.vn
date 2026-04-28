# Guest behavior keyed by browser session (X-Guest-Session-Id), merged to user on login.
from sqlalchemy import Column, Integer, String, DateTime, JSON, UniqueConstraint, Index
from sqlalchemy.sql import func
from app.db.base import Base


class GuestProductView(Base):
    __tablename__ = "guest_product_views"
    __table_args__ = (
        UniqueConstraint("session_id", "product_id", name="uq_guest_pv_session_product"),
        Index("ix_guest_pv_session_viewed", "session_id", "viewed_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    product_id = Column(Integer, nullable=False, index=True)
    product_data = Column(JSON, nullable=True)
    viewed_at = Column(DateTime(timezone=True), server_default=func.now())
    view_count = Column(Integer, default=1)
    time_spent_seconds = Column(Integer, default=0)


class GuestFavorite(Base):
    __tablename__ = "guest_favorites"
    __table_args__ = (UniqueConstraint("session_id", "product_id", name="uq_guest_fav_session_product"),)

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    product_id = Column(Integer, nullable=False, index=True)
    product_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class GuestSearchHistory(Base):
    __tablename__ = "guest_search_history"
    __table_args__ = (Index("ix_guest_search_session_searched", "session_id", "searched_at"),)

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    search_query = Column(String(500), nullable=False)
    search_filters = Column(JSON, nullable=True)
    search_results_count = Column(Integer, default=0)
    searched_at = Column(DateTime(timezone=True), server_default=func.now())
