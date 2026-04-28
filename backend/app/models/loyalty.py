from sqlalchemy import Column, Integer, String, Float, Numeric, Text
from app.db.base import Base

class LoyaltyTier(Base):
    __tablename__ = "loyalty_tiers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, index=True, nullable=False)  # L1, L2, ...
    min_spend = Column(Numeric(12, 2), nullable=False, default=0)       # Mức chi tiêu tối thiểu
    discount_percent = Column(Float, nullable=False, default=0.0)       # Phần trăm giảm giá (0-100)
    description = Column(Text, nullable=True)                           # Mô tả ưu đãi
    
    def __repr__(self):
        return f"<LoyaltyTier {self.name} - Min: {self.min_spend}>"
