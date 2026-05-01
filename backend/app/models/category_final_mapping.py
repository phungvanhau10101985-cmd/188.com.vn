from sqlalchemy import Boolean, Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.db.base import Base


class CategoryFinalMapping(Base):
    __tablename__ = "category_final_mappings"

    id = Column(Integer, primary_key=True, index=True)
    from_category = Column(String(255), nullable=False, index=True)
    from_subcategory = Column(String(255), nullable=True, index=True)
    from_sub_subcategory = Column(String(255), nullable=True, index=True)
    to_category = Column(String(255), nullable=False)
    to_subcategory = Column(String(255), nullable=True)
    to_sub_subcategory = Column(String(255), nullable=True)
    # True: vẫn áp khi import Excel + khi dựng cây danh mục (hành vi cũ). False: chỉ dùng lúc admin
    # POST/PUT mapping để cập nhật SP một lần; SP / import mới không đi theo rule này nữa.
    apply_to_future_imports = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
