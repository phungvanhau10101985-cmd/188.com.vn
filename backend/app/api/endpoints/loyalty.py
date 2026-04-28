from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from decimal import Decimal

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.loyalty import LoyaltyTier, LoyaltyTierCreate, LoyaltyTierUpdate, UserLoyaltyStatus
from app.crud import loyalty as crud_loyalty

router = APIRouter()

@router.get("/my-status", response_model=UserLoyaltyStatus)
def get_my_loyalty_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Lấy thông tin hạng thành viên của user hiện tại.
    """
    # 1. Tính tổng chi tiêu 6 tháng
    total_spent = crud_loyalty.calculate_user_spend_6_months(db, current_user.id)
    
    # 2. Xác định hạng hiện tại
    current_tier = crud_loyalty.get_tier_by_spend(db, total_spent)
    
    # 3. Xác định hạng tiếp theo
    next_tier = None
    remaining_spend = None
    message = ""
    
    if current_tier:
        next_tier = crud_loyalty.get_next_tier(db, current_tier.min_spend)
        message = f"Chào thành viên {current_user.full_name or 'bạn'}, hạng thành viên mình là {current_tier.name}. Bạn được giảm {current_tier.discount_percent}% trên tổng giá trị đơn hàng."
    else:
        # Nếu chưa có hạng nào (ví dụ total_spent < min_spend của hạng thấp nhất)
        # Lấy hạng thấp nhất làm next_tier
        tiers = crud_loyalty.get_all_tiers(db)
        if tiers:
            next_tier = tiers[0]
            message = f"Chào {current_user.full_name or 'bạn'}, bạn chưa đạt hạng thành viên nào."
    
    if next_tier:
        remaining_spend = next_tier.min_spend - total_spent
        if remaining_spend < 0:
            remaining_spend = Decimal(0)
            
    return {
        "current_tier": current_tier,
        "total_spent_6_months": total_spent,
        "next_tier": next_tier,
        "remaining_spend_for_next_tier": remaining_spend,
        "message": message
    }

@router.get("/tiers", response_model=List[LoyaltyTier])
def get_loyalty_tiers(
    db: Session = Depends(get_db)
) -> Any:
    """
    Lấy danh sách tất cả các hạng thành viên.
    """
    return crud_loyalty.get_all_tiers(db)

@router.post("/tiers", response_model=LoyaltyTier)
def create_loyalty_tier(
    tier_in: LoyaltyTierCreate,
    db: Session = Depends(get_db),
    # current_user: User = Depends(get_current_active_superuser) # TODO: Add admin check
) -> Any:
    """
    Tạo hạng thành viên mới (Admin).
    """
    return crud_loyalty.create_tier(db, tier_in)

@router.put("/tiers/{tier_id}", response_model=LoyaltyTier)
def update_loyalty_tier(
    tier_id: int,
    tier_in: LoyaltyTierUpdate,
    db: Session = Depends(get_db),
    # current_user: User = Depends(get_current_active_superuser) # TODO: Add admin check
) -> Any:
    """
    Cập nhật hạng thành viên (Admin).
    """
    tier = db.query(crud_loyalty.LoyaltyTier).filter(crud_loyalty.LoyaltyTier.id == tier_id).first()
    if not tier:
        raise HTTPException(status_code=404, detail="Loyalty tier not found")
    return crud_loyalty.update_tier(db, tier, tier_in)

@router.delete("/tiers/{tier_id}", response_model=LoyaltyTier)
def delete_loyalty_tier(
    tier_id: int,
    db: Session = Depends(get_db),
    # current_user: User = Depends(get_current_active_superuser) # TODO: Add admin check
) -> Any:
    """
    Xóa hạng thành viên (Admin).
    """
    tier = crud_loyalty.delete_tier(db, tier_id)
    if not tier:
        raise HTTPException(status_code=404, detail="Loyalty tier not found")
    return tier
