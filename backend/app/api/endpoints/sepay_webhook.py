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


async def _handle_sepay_webhook_post(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session,
) -> JSONResponse:
    """
    URL chuẩn: https://<domain>/api/v1/sepay/webhook
    Alias khi chỉ có backend (Nginx ``/api/*`` → FastAPI): ``.../api/sepay-webhook`` (đăng ký trong ``main.load_api_routes``).
    """
    raw = await request.body()
    peer = request.client.host if request.client else "?"
    xff = (request.headers.get("x-forwarded-for") or "").strip()
    logger.info(
        "SePay webhook POST received bytes=%s peer=%s x_forwarded_for=%s",
        len(raw) if raw else 0,
        peer,
        (xff[:256] or "-"),
    )
    if not sepay_svc.verify_webhook(request, raw):
        logger.warning("SePay webhook rejected: xác thực thất bại")
        return JSONResponse({"success": False, "message": "unauthorized"}, status_code=401)

    data = sepay_svc.parse_webhook_payload(raw, request.headers.get("content-type", ""))
    ok, msg, order_id = sepay_svc.apply_sepay_incoming_transfer(db, data)
    logger.info("SePay webhook processed applied=%s detail=%s order_id=%s", ok, msg, order_id)
    if ok and msg == "ok" and order_id:
        background_tasks.add_task(send_deposit_confirmed_email_task, order_id)
    return JSONResponse({"success": True}, status_code=201)


@router.post("/webhook")
async def sepay_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Đăng ký SePay: POST .../api/v1/sepay/webhook"""
    return await _handle_sepay_webhook_post(request, background_tasks, db)


async def sepay_webhook_public_path(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """POST .../api/sepay-webhook — main.py add_api_route (Nginx gửi /api/* thẳng vào FastAPI)."""
    return await _handle_sepay_webhook_post(request, background_tasks, db)
