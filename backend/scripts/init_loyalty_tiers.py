import sys
import os
from decimal import Decimal

# Add backend directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.db.session import SessionLocal
from app.models.loyalty import LoyaltyTier

def init_loyalty_tiers():
    db = SessionLocal()
    
    tiers_data = [
        {
            "name": "L1",
            "min_spend": Decimal(0),
            "discount_percent": 0.0,
            "description": "Giảm 0% trên tổng giá trị đơn hàng cho khách hàng có tổng số tiền mua hàng trong 6 tháng liên tiếp nhỏ hơn 4 triệu."
        },
        {
            "name": "L2",
            "min_spend": Decimal(4000000),
            "discount_percent": 2.0,
            "description": "Giảm 2% trên tổng giá trị đơn hàng cho khách hàng có tổng số tiền mua hàng trong 6 tháng liên tiếp từ 4 triệu đến dưới 8 triệu."
        },
        {
            "name": "L3",
            "min_spend": Decimal(8000000),
            "discount_percent": 4.0,
            "description": "Giảm 4% trên tổng giá trị đơn hàng cho khách hàng có tổng số tiền mua hàng trong 6 tháng liên tiếp từ 8 triệu đến dưới 12 triệu."
        },
        {
            "name": "L4",
            "min_spend": Decimal(12000000),
            "discount_percent": 6.0,
            "description": "Giảm 6% trên tổng giá trị đơn hàng cho khách hàng có tổng số tiền mua hàng trong 6 tháng liên tiếp từ 12 triệu đến dưới 20 triệu."
        },
        {
            "name": "L5",
            "min_spend": Decimal(20000000),
            "discount_percent": 10.0,
            "description": "Giảm 10% trên tổng giá trị đơn hàng cho khách hàng có tổng số tiền mua hàng trong 6 tháng liên tiếp trên 20 triệu."
        }
    ]
    
    for data in tiers_data:
        existing = db.query(LoyaltyTier).filter(LoyaltyTier.name == data["name"]).first()
        if not existing:
            tier = LoyaltyTier(**data)
            db.add(tier)
            print(f"Created tier: {data['name']}")
        else:
            # Update existing
            existing.min_spend = data["min_spend"]
            existing.discount_percent = data["discount_percent"]
            existing.description = data["description"]
            print(f"Updated tier: {data['name']}")
            
    db.commit()
    db.close()

if __name__ == "__main__":
    init_loyalty_tiers()
