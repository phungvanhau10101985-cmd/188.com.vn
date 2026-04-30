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

# Thông điệp `error` (EN) để đối chiếu log SePay / chế độ xác minh — HTTP 200 tránh retry vô hạn khi sai nghiệp vụ.
_SEPAY_WEBHOOK_ERROR_EN: dict[str, str] = {
    "missing_amount": "Transfer amount missing",
    "invalid_amount": "Invalid transfer amount",
    "missing_id": "Transaction id missing",
    "account_mismatch": "Bank account does not match configured SePay account",
    "no_order_code_in_content": "Payment code not found in transfer content",
    "order_not_found": "Pending payment not found",
    "order_not_waiting_deposit": "Order is not awaiting deposit",
    "no_deposit_required": "Order does not require deposit",
    "content_mismatch": "Transfer content does not match expected order reference",
    "amount_mismatch": "Transfer amount does not match required deposit",
}


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

    if ok:
        # duplicate / ignored_out / ok — SePay chờ success true (+ 200/201 tuỳ auth)
        if msg == "ok" and order_id:
            background_tasks.add_task(send_deposit_confirmed_email_task, order_id)
        return JSONResponse({"success": True}, status_code=201)

    err_en = _SEPAY_WEBHOOK_ERROR_EN.get(msg, msg.replace("_", " "))
    body = {"success": False, "error": err_en, "code": msg}
    # HTTP 200: kết nối OK, không kích retry mạng; SePay không ghi nhận là giao dịch đã khớp đơn.
    return JSONResponse(body, status_code=200)


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
