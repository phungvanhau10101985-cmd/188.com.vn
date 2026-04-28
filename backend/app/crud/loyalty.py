from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timedelta
from decimal import Decimal

from app.models.loyalty import LoyaltyTier
from app.models.order import Order, OrderStatus
from app.schemas.loyalty import LoyaltyTierCreate, LoyaltyTierUpdate

def get_all_tiers(db: Session) -> List[LoyaltyTier]:
    return db.query(LoyaltyTier).order_by(LoyaltyTier.min_spend.asc()).all()

def get_tier_by_spend(db: Session, total_spend: Decimal) -> Optional[LoyaltyTier]:
    # Lấy hạng cao nhất mà total_spend >= min_spend
    return db.query(LoyaltyTier)\
        .filter(LoyaltyTier.min_spend <= total_spend)\
        .order_by(LoyaltyTier.min_spend.desc())\
        .first()

def get_next_tier(db: Session, current_tier_min_spend: Decimal) -> Optional[LoyaltyTier]:
    # Lấy hạng tiếp theo (min_spend > current_tier_min_spend)
    return db.query(LoyaltyTier)\
        .filter(LoyaltyTier.min_spend > current_tier_min_spend)\
        .order_by(LoyaltyTier.min_spend.asc())\
        .first()

def calculate_user_spend_6_months(db: Session, user_id: int) -> Decimal:
    six_months_ago = datetime.now() - timedelta(days=180)
    
    # Chỉ tính đơn hàng đã giao hoặc hoàn thành
    valid_statuses = [OrderStatus.DELIVERED, OrderStatus.COMPLETED]
    
    result = db.query(func.sum(Order.total_amount))\
        .filter(Order.user_id == user_id)\
        .filter(Order.status.in_(valid_statuses))\
        .filter(Order.created_at >= six_months_ago)\
        .scalar()
        
    return result if result else Decimal(0)

def create_tier(db: Session, tier: LoyaltyTierCreate) -> LoyaltyTier:
    db_tier = LoyaltyTier(
        name=tier.name,
        min_spend=tier.min_spend,
        discount_percent=tier.discount_percent,
        description=tier.description
    )
    db.add(db_tier)
    db.commit()
    db.refresh(db_tier)
    return db_tier

def update_tier(db: Session, db_tier: LoyaltyTier, tier_in: LoyaltyTierUpdate) -> LoyaltyTier:
    update_data = tier_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_tier, field, value)
    db.add(db_tier)
    db.commit()
    db.refresh(db_tier)
    return db_tier

def delete_tier(db: Session, tier_id: int) -> LoyaltyTier:
    tier = db.query(LoyaltyTier).filter(LoyaltyTier.id == tier_id).first()
    if tier:
        db.delete(tier)
        db.commit()
    return tier
