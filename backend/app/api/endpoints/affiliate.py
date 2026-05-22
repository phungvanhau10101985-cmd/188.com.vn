from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_module_permission
from app.db.session import get_db
from app.models.admin import AdminUser
from app.models.user import User
from app.schemas import affiliate as schemas
from app.services import affiliate_wallet as svc

router = APIRouter()


@router.get("/me", response_model=schemas.AffiliateMeResponse)
def get_my_affiliate(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.build_me_payload(db, current_user.id)


@router.post("/attribute")
def attribute_referral(
    payload: schemas.AffiliateAttributeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        profile = svc.attribute_referral(db, current_user.id, payload.referral_code)
        db.commit()
        return {
            "ok": True,
            "referred_by_user_id": profile.referred_by_user_id,
        }
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/application", response_model=Optional[schemas.AffiliateApplicationResponse])
def get_my_affiliate_application(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc._application_to_dict(svc.get_affiliate_application(db, current_user.id))


@router.post("/application", response_model=schemas.AffiliateApplicationResponse)
def submit_my_affiliate_application(
    payload: schemas.AffiliateApplicationIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        row = svc.submit_affiliate_application(
            db,
            user_id=current_user.id,
            social_links=payload.social_links,
            note=payload.note,
        )
        db.commit()
        db.refresh(row)
        return svc._application_to_dict(row)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/referred-orders", response_model=List[schemas.AffiliateReferredOrderResponse])
def list_referred_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    if not svc.is_user_approved_affiliate(db, current_user.id):
        return []
    return svc.list_referred_orders_for_affiliate(db, current_user.id, skip=skip, limit=limit)


@router.get("/wallet/transactions", response_model=List[schemas.WalletTransactionResponse])
def list_wallet_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    from app.models.affiliate import WalletTransaction

    rows = (
        db.query(WalletTransaction)
        .filter(WalletTransaction.user_id == current_user.id)
        .order_by(WalletTransaction.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return rows


@router.get("/bank-account", response_model=Optional[schemas.UserBankAccountResponse])
def get_bank_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.affiliate import UserBankAccount

    row = db.query(UserBankAccount).filter(UserBankAccount.user_id == current_user.id).first()
    return row


@router.post("/bank-account/otp", response_model=schemas.BankAccountOtpResponse)
def request_bank_account_otp(
    payload: schemas.UserBankAccountOtpRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = svc.request_bank_account_otp(
            db,
            user_id=current_user.id,
            email=current_user.email,
            bank_name=payload.bank_name,
            bank_account=payload.bank_account,
            account_holder=payload.account_holder,
        )
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Không gửi được OTP. Vui lòng thử lại sau.") from exc


@router.put("/bank-account", response_model=schemas.UserBankAccountResponse)
def upsert_bank_account(
    payload: schemas.UserBankAccountVerifyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        row = svc.save_bank_account_with_otp(
            db,
            user_id=current_user.id,
            bank_name=payload.bank_name,
            bank_account=payload.bank_account,
            account_holder=payload.account_holder,
            otp=payload.otp,
        )
        db.commit()
        db.refresh(row)
        return row
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/wallet/withdraw", response_model=schemas.WalletWithdrawalResponse)
def create_withdrawal(
    payload: schemas.WalletWithdrawIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        row = svc.request_withdrawal(db, current_user.id, payload.amount)
        db.commit()
        db.refresh(row)
        return row
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/wallet/withdrawals", response_model=List[schemas.WalletWithdrawalResponse])
def list_my_withdrawals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    from app.models.affiliate import WalletWithdrawal

    rows = (
        db.query(WalletWithdrawal)
        .filter(WalletWithdrawal.user_id == current_user.id)
        .order_by(WalletWithdrawal.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return rows


@router.get("/admin/commissions", response_model=List[schemas.AdminAffiliateCommissionResponse])
def admin_list_commissions(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("affiliate")),
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    from app.models.affiliate import AffiliateCommission

    q = db.query(AffiliateCommission).order_by(AffiliateCommission.created_at.desc())
    if status:
        q = q.filter(AffiliateCommission.status == status.strip())
    return q.offset(skip).limit(limit).all()


@router.get("/admin/applications", response_model=List[schemas.AffiliateApplicationResponse])
def admin_list_applications(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("affiliate")),
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    return svc.list_affiliate_applications(db, status=status, skip=skip, limit=limit)


@router.post("/admin/applications/{application_id}/approve", response_model=schemas.AffiliateApplicationResponse)
def admin_approve_application(
    application_id: int,
    payload: schemas.AdminAffiliateApplicationDecisionIn,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(require_module_permission("affiliate")),
):
    try:
        row = svc.approve_affiliate_application(db, application_id, current_admin.id, payload.admin_note)
        db.commit()
        db.refresh(row)
        return svc._application_to_dict(row)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/admin/applications/{application_id}/reject", response_model=schemas.AffiliateApplicationResponse)
def admin_reject_application(
    application_id: int,
    payload: schemas.AdminAffiliateApplicationDecisionIn,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(require_module_permission("affiliate")),
):
    try:
        row = svc.reject_affiliate_application(db, application_id, current_admin.id, payload.admin_note)
        db.commit()
        db.refresh(row)
        return svc._application_to_dict(row)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/admin/settings", response_model=schemas.AffiliateSettingsResponse)
def admin_get_settings(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("affiliate")),
):
    return svc.get_or_create_settings(db)


@router.put("/admin/settings", response_model=schemas.AffiliateSettingsResponse)
def admin_update_settings(
    payload: schemas.AffiliateSettingsUpdate,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(require_module_permission("affiliate")),
):
    row = svc.update_settings(
        db,
        enabled=payload.enabled,
        commission_percent_value=payload.commission_percent,
        min_withdrawal_value=payload.min_withdrawal,
        ref_cookie_days=payload.ref_cookie_days,
        commission_policy=payload.commission_policy,
        admin_id=current_admin.id,
    )
    db.commit()
    db.refresh(row)
    return row


@router.get("/admin/withdrawals", response_model=List[schemas.WalletWithdrawalResponse])
def admin_list_withdrawals(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("affiliate")),
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    from app.models.affiliate import WalletWithdrawal

    q = db.query(WalletWithdrawal).order_by(WalletWithdrawal.created_at.desc())
    if status:
        q = q.filter(WalletWithdrawal.status == status.strip())
    return q.offset(skip).limit(limit).all()


@router.post("/admin/withdrawals/{withdrawal_id}/approve", response_model=schemas.WalletWithdrawalResponse)
def admin_approve_withdrawal(
    withdrawal_id: int,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(require_module_permission("affiliate")),
):
    try:
        row = svc.approve_withdrawal(db, withdrawal_id, current_admin.id)
        db.commit()
        db.refresh(row)
        return row
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/admin/withdrawals/{withdrawal_id}/reject", response_model=schemas.WalletWithdrawalResponse)
def admin_reject_withdrawal(
    withdrawal_id: int,
    payload: schemas.AdminWithdrawRejectIn,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(require_module_permission("affiliate")),
):
    try:
        row = svc.reject_withdrawal(db, withdrawal_id, current_admin.id, payload.admin_note)
        db.commit()
        db.refresh(row)
        return row
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
