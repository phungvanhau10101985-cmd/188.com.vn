"""
Middleware ASGI thuần — tránh lỗi h11 LocalProtocolError khi client ngắt kết nối sớm
và đọc body POST /auth/* cho cảnh báo đăng nhập (không dùng BaseHTTPMiddleware).
"""
from __future__ import annotations

import json
import logging
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.services.auth_failure_alert import is_customer_login_auth_path

logger = logging.getLogger(__name__)


def _is_client_disconnect_exc(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in ("LocalProtocolError", "ClientDisconnect", "EndOfStream"):
        return True
    msg = str(exc)
    return "Can't send data when our state is ERROR" in msg


class ClientDisconnectSafeMiddleware:
    """Bọc send — client đóng tab/proxy cắt socket thì không log ERROR h11."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            try:
                await send(message)
            except Exception as exc:
                if _is_client_disconnect_exc(exc):
                    logger.debug(
                        "client disconnect during response %s %s",
                        scope.get("method"),
                        scope.get("path"),
                    )
                    return
                raise

        await self.app(scope, receive, send_wrapper)


class AuthLoginBodyMiddleware:
    """Lưu email khách từ body POST đăng nhập vào scope (cho auth_failure_alert)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        method = (scope.get("method") or "GET").upper()
        if method != "POST" or not is_customer_login_auth_path(path, method):
            await self.app(scope, receive, send)
            return

        body = b""
        while True:
            message = await receive()
            if message["type"] != "http.request":
                if message["type"] == "http.disconnect":
                    return
                continue
            body += message.get("body", b"") or b""
            if not message.get("more_body", False):
                break

        if body:
            try:
                data = json.loads(body)
                if isinstance(data, dict):
                    raw = data.get("email")
                    if raw:
                        from app.core.email_identity import identity_email

                        v = identity_email(str(raw))
                        scope["auth_alert_email"] = v or str(raw).strip().lower()
            except Exception:
                pass

        async def receive_replay() -> Message:
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, receive_replay, send)


class LastResortJsonMiddleware:
    """Bắt exception trước khi stream response — tránh BaseHTTPMiddleware."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            if _is_client_disconnect_exc(exc):
                return
            log = logging.getLogger("last_resort_json")
            log.exception("%s %s", scope.get("method"), scope.get("path"))
            from starlette.responses import JSONResponse

            response = JSONResponse(
                status_code=500,
                content={"detail": str(exc).strip() or exc.__class__.__name__},
            )
            await response(scope, receive, send)
