"""Admin — đọc chi phí Google Ads và Facebook Ads."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_privileged_admin
from app.db.session import get_db
from app.models.admin import AdminUser
from app.schemas.ad_spend import (
    AdSpendProfitInputsUpdate,
    AdSpendProfitSheet,
    AdSpendReport,
    AdSpendSettingsUpdate,
    AdSpendSettingsView,
)
from app.services import ad_spend_profit, ad_spend_service as svc

router = APIRouter()


@router.get("/settings", response_model=AdSpendSettingsView)
def get_ad_spend_settings(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_privileged_admin),
):
    row = svc.get_or_create_settings(db)
    return svc.settings_to_view(row)


@router.put("/settings", response_model=AdSpendSettingsView)
def update_ad_spend_settings(
    payload: AdSpendSettingsUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_privileged_admin),
):
    row = svc.get_or_create_settings(db)
    svc.apply_settings_update(row, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(row)
    svc.clear_report_cache()
    return svc.settings_to_view(row)


@router.get("/report", response_model=AdSpendReport)
def get_ad_spend_report(
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_privileged_admin),
):
    try:
        return svc.load_report(db, date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/profit", response_model=AdSpendProfitSheet)
def get_ad_spend_profit(
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_privileged_admin),
):
    try:
        return ad_spend_profit.load_profit_sheet(db, date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/profit", response_model=AdSpendProfitSheet)
def update_ad_spend_profit(
    payload: AdSpendProfitInputsUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_privileged_admin),
):
    try:
        ad_spend_profit.save_profit_inputs(db, payload.model_dump())
        return ad_spend_profit.load_profit_sheet(db, payload.date_from, payload.date_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
