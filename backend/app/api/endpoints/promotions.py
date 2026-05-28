from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user, require_module_permission
from app.crud import promotion as crud_promotion
from app.crud.promotion import PromoValidationError
from app.db.session import get_db
from app.models.admin import AdminUser
from app.models.promotion import UserPromotionGrant
from app.models.user import User
from app.schemas.promotion import (
    AdminDailyPromotionCronResponse,
    AdminGrantSegmentRequest,
    AdminGrantSegmentResponse,
    AdminGrantVoucherRequest,
    AdminPromotionCreate,
    AdminPromotionListResponse,
    AdminPromotionOut,
    AdminPromotionUpdate,
    AdminUserGrantOut,
    AdminWelcomePromoOut,
    AdminWelcomePromoUpdate,
    PromoValidateRequest,
    PromoValidateResponse,
    PromotionVoucherListResponse,
    WelcomeEligibilityResponse,
)
from app.services import promotion_grants as grant_svc
from app.services.promotion_cron import run_daily_promotion_cron, run_daily_voucher_grants

router = APIRouter()


def _require_cron_secret(authorization: str | None) -> None:
    expected = (settings.CRON_SECRET or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="CRON_SECRET is not configured")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or token.strip() != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _welcome_to_eligibility(status: dict) -> WelcomeEligibilityResponse:
    return WelcomeEligibilityResponse(**status)


def _system_template_codes() -> set[str]:
    return {tpl["code"] for tpl in grant_svc.PROMO_TEMPLATES}


def _promotion_to_admin_out(db: Session, promo) -> AdminPromotionOut:
    grants_count, usages_count = crud_promotion.get_promotion_stats(db, promo.id)
    return AdminPromotionOut(
        id=promo.id,
        code=promo.code,
        name=promo.name,
        description=promo.description,
        discount_percent=float(promo.discount_percent),
        max_discount_amount=float(promo.max_discount_amount) if promo.max_discount_amount is not None else None,
        first_order_only=bool(promo.first_order_only),
        stack_with_birthday=bool(promo.stack_with_birthday),
        stack_with_loyalty=bool(promo.stack_with_loyalty),
        is_active=bool(promo.is_active),
        valid_from=promo.valid_from.isoformat() if promo.valid_from else None,
        valid_to=promo.valid_to.isoformat() if promo.valid_to else None,
        usage_limit=promo.usage_limit,
        per_user_limit=int(promo.per_user_limit or 1),
        eligible_within_days=promo.eligible_within_days,
        grant_valid_days=promo.grant_valid_days,
        requires_wallet_grant=bool(promo.requires_wallet_grant),
        auto_grant_trigger=str(promo.auto_grant_trigger or "none"),
        grants_count=grants_count,
        usages_count=usages_count,
        is_system_template=promo.code in _system_template_codes(),
        created_at=promo.created_at.isoformat() if promo.created_at else None,
        updated_at=promo.updated_at.isoformat() if promo.updated_at else None,
    )


@router.get("/my-vouchers", response_model=PromotionVoucherListResponse)
def get_my_promo_vouchers(
    subtotal: Optional[float] = Query(default=None, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ví mã khuyến mãi cá nhân — chỉ mã đã được shop tặng."""
    subtotal_decimal = Decimal(str(subtotal)) if subtotal is not None else None
    items = crud_promotion.list_user_vouchers(db, current_user, subtotal=subtotal_decimal)
    return PromotionVoucherListResponse(items=items)


@router.get("/welcome-eligibility", response_model=WelcomeEligibilityResponse)
def get_welcome_eligibility(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    status = crud_promotion.build_welcome_status(db, current_user)
    return _welcome_to_eligibility(status)


@router.get("/welcome", response_model=PromotionVoucherListResponse)
def get_welcome_program(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trang khuyến mãi — toàn bộ ví mã cá nhân."""
    items = crud_promotion.list_user_vouchers(db, current_user)
    return PromotionVoucherListResponse(items=items)


@router.post("/validate", response_model=PromoValidateResponse)
def validate_promo_code(
    payload: PromoValidateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    subtotal = Decimal(str(payload.subtotal or 0))
    try:
        promo, amount, message, _grant = crud_promotion.validate_welcome_promo(
            db,
            user_id=current_user.id,
            code=payload.code,
            subtotal=subtotal,
        )
    except PromoValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    return PromoValidateResponse(
        valid=True,
        code=promo.code,
        discount_percent=float(promo.discount_percent),
        max_discount_amount=float(promo.max_discount_amount or 0),
        estimated_discount=float(amount),
        message=message,
    )


@router.get("/admin/promotions", response_model=AdminPromotionListResponse)
def admin_list_promotions(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("promotions")),
):
    rows = crud_promotion.list_all_promotions(db)
    return AdminPromotionListResponse(
        items=[_promotion_to_admin_out(db, promo) for promo in rows]
    )


@router.get("/admin/promotions/{promotion_id}", response_model=AdminPromotionOut)
def admin_get_promotion(
    promotion_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("promotions")),
):
    promo = crud_promotion.get_promotion_by_id(db, promotion_id)
    if not promo:
        raise HTTPException(status_code=404, detail="Không tìm thấy mã khuyến mãi.")
    return _promotion_to_admin_out(db, promo)


@router.post("/admin/promotions", response_model=AdminPromotionOut)
def admin_create_promotion(
    payload: AdminPromotionCreate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("promotions")),
):
    try:
        promo = crud_promotion.create_promotion(db, payload.model_dump())
    except PromoValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    return _promotion_to_admin_out(db, promo)


@router.patch("/admin/promotions/{promotion_id}", response_model=AdminPromotionOut)
def admin_update_promotion(
    promotion_id: int,
    payload: AdminPromotionUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("promotions")),
):
    try:
        promo = crud_promotion.update_promotion(
            db,
            promotion_id,
            payload.model_dump(exclude_unset=True),
        )
    except PromoValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    return _promotion_to_admin_out(db, promo)


@router.get("/admin/welcome", response_model=AdminWelcomePromoOut)
def admin_get_welcome_promo(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("promotions")),
):
    grant_svc.ensure_promotion_templates(db)
    promo = crud_promotion.ensure_welcome_promotion(db)
    days = promo.grant_valid_days or promo.eligible_within_days
    has_day_limit = days is not None and int(days) > 0
    return AdminWelcomePromoOut(
        code=promo.code,
        name=promo.name,
        description=promo.description,
        discount_percent=float(promo.discount_percent),
        max_discount_amount=float(promo.max_discount_amount or 0),
        eligible_within_days=int(days) if has_day_limit else None,
        show_days_remaining=has_day_limit,
        is_active=bool(promo.is_active),
        first_order_only=bool(promo.first_order_only),
    )


@router.patch("/admin/welcome", response_model=AdminWelcomePromoOut)
def admin_update_welcome_promo(
    payload: AdminWelcomePromoUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("promotions")),
):
    promo = crud_promotion.update_welcome_promotion(
        db,
        payload.model_dump(exclude_unset=True),
    )
    days = promo.grant_valid_days or promo.eligible_within_days
    has_day_limit = days is not None and int(days) > 0
    return AdminWelcomePromoOut(
        code=promo.code,
        name=promo.name,
        description=promo.description,
        discount_percent=float(promo.discount_percent),
        max_discount_amount=float(promo.max_discount_amount or 0),
        eligible_within_days=int(days) if has_day_limit else None,
        show_days_remaining=has_day_limit,
        is_active=bool(promo.is_active),
        first_order_only=bool(promo.first_order_only),
    )


@router.post("/admin/grant", response_model=AdminUserGrantOut)
def admin_grant_voucher_to_user(
    payload: AdminGrantVoucherRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("promotions")),
):
    grant_svc.ensure_promotion_templates(db)
    grant = grant_svc.grant_voucher(
        db,
        user_id=payload.user_id,
        promo_code=payload.promo_code,
        source="admin",
        expires_in_days=payload.expires_in_days,
        grant_message=payload.message,
        notify=payload.notify,
        skip_if_active=False,
    )
    if not grant:
        raise HTTPException(status_code=400, detail="Không thể tặng mã. Kiểm tra user_id và mã khuyến mãi.")
    promo = grant.promotion
    return AdminUserGrantOut(
        id=grant.id,
        user_id=grant.user_id,
        code=promo.code if promo else payload.promo_code,
        name=promo.name if promo else payload.promo_code,
        status=grant.status.value if hasattr(grant.status, "value") else str(grant.status),
        source=grant.source,
        granted_at=grant.granted_at.isoformat() if grant.granted_at else None,
        expires_at=grant.expires_at.isoformat() if grant.expires_at else None,
    )


@router.post("/admin/grant-segment", response_model=AdminGrantSegmentResponse)
def admin_grant_segment(
    payload: AdminGrantSegmentRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("promotions")),
):
    segment = (payload.segment or "").strip().lower()
    if segment == "comeback":
        result = grant_svc.process_comeback_grants_for_all(
            db,
            inactive_days=payload.inactive_days or 30,
        )
    elif segment == "welcome_backfill":
        result = grant_svc.process_welcome_backfill(db)
    elif segment == "cart_abandon":
        result = grant_svc.process_cart_abandon_grants_for_all(
            db,
            abandon_hours=payload.abandon_hours or 24,
        )
    else:
        raise HTTPException(status_code=400, detail="Segment không hỗ trợ.")
    return AdminGrantSegmentResponse(**result)


@router.get("/cron/cart-abandon", response_model=AdminGrantSegmentResponse)
def cron_cart_abandon_grants(
    abandon_hours: int = Query(24, ge=6, le=168),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Cron: tặng mã nhắc giỏ hàng. Authorization: Bearer CRON_SECRET."""
    _require_cron_secret(authorization)
    result = grant_svc.process_cart_abandon_grants_for_all(db, abandon_hours=abandon_hours)
    return AdminGrantSegmentResponse(**result)


@router.get("/cron/comeback", response_model=AdminGrantSegmentResponse)
def cron_comeback_grants(
    inactive_days: int = Query(30, ge=7, le=180),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Cron: tặng COMEBACK10 cho khách lâu chưa mua. Authorization: Bearer CRON_SECRET."""
    _require_cron_secret(authorization)
    result = grant_svc.process_comeback_grants_for_all(db, inactive_days=inactive_days)
    return AdminGrantSegmentResponse(**result)


@router.get("/cron/daily-voucher-grants")
def cron_daily_voucher_grants(
    inactive_days: int = Query(30, ge=7, le=180),
    abandon_hours: int = Query(24, ge=6, le=168),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Cron: CARTSAVE + COMEBACK + backfill WELCOME. Authorization: Bearer CRON_SECRET."""
    _require_cron_secret(authorization)
    return run_daily_voucher_grants(
        db,
        inactive_days=inactive_days,
        abandon_hours=abandon_hours,
        include_welcome_backfill=True,
    )


@router.get("/cron/daily-all", response_model=AdminDailyPromotionCronResponse)
def cron_daily_all_promotions(
    inactive_days: int = Query(30, ge=7, le=180),
    abandon_hours: int = Query(24, ge=6, le=168),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Cron gộp hàng ngày — khuyến nghị 1 dòng crontab duy nhất:
    voucher grants (cart/comeback/welcome backfill) + email CMSN sinh nhật.
    Authorization: Bearer CRON_SECRET
    """
    _require_cron_secret(authorization)
    result = run_daily_promotion_cron(
        db,
        inactive_days=inactive_days,
        abandon_hours=abandon_hours,
        include_welcome_backfill=True,
        include_birthday_emails=True,
    )
    return AdminDailyPromotionCronResponse(**result)


@router.get("/admin/grants", response_model=list[AdminUserGrantOut])
def admin_list_user_grants(
    user_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("promotions")),
):
    rows = (
        db.query(UserPromotionGrant)
        .filter(UserPromotionGrant.user_id == user_id)
        .order_by(UserPromotionGrant.granted_at.desc())
        .limit(50)
        .all()
    )
    out: list[AdminUserGrantOut] = []
    for grant in rows:
        promo = grant.promotion
        out.append(
            AdminUserGrantOut(
                id=grant.id,
                user_id=grant.user_id,
                code=promo.code if promo else "",
                name=promo.name if promo else "",
                status=grant.status.value if hasattr(grant.status, "value") else str(grant.status),
                source=grant.source,
                granted_at=grant.granted_at.isoformat() if grant.granted_at else None,
                expires_at=grant.expires_at.isoformat() if grant.expires_at else None,
            )
        )
    return out
