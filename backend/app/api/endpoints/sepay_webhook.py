# backend/app/api/endpoints/sepay_webhook.py — Webhook SePay (server-to-server)
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import sepay as sepay_svc
from app.services.email_service import send_deposit_confirmed_email_task

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhook")
async def sepay_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    URL đăng ký trên SePay: https://<domain>/api/v1/sepay/webhook
    Luôn trả HTTP 200 + JSON success để SePay không retry vô hạn; chi tiết trong `detail`.
    """
    raw = await request.body()
    if not sepay_svc.verify_webhook(request, raw):
        logger.warning("SePay webhook rejected: xác thực thất bại")
        return JSONResponse({"success": False, "message": "unauthorized"}, status_code=401)

    data = sepay_svc.parse_webhook_payload(raw, request.headers.get("content-type", ""))
    ok, msg, order_id = sepay_svc.apply_sepay_incoming_transfer(db, data)
    logger.info("SePay webhook processed applied=%s detail=%s order_id=%s", ok, msg, order_id)
    if ok and msg == "ok" and order_id:
        background_tasks.add_task(send_deposit_confirmed_email_task, order_id)
    return JSONResponse({"success": True, "applied": ok, "detail": msg}, status_code=200)
