"""Google Sheets API client dùng chung (catalog sync, Hàng Đặt Mới autofill, …).

Không còn đồng bộ danh sách SKU lên Sheet vận hành.
Xác thực: GOOGLE_SHEETS_SKU_CREDENTIALS_PATH → runtime/.../gcp-vision-service-account.json
→ GOOGLE_APPLICATION_CREDENTIALS → IMAGE_LOCALIZATION_GCP_KEY_FILE.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from app.core.config import settings

logger = logging.getLogger(__name__)

SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)


def _default_vision_service_account_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "runtime"
        / "image_localization"
        / "gcp-vision-service-account.json"
    )


def _credentials_path() -> str:
    p = (getattr(settings, "GOOGLE_SHEETS_SKU_CREDENTIALS_PATH", None) or "").strip()
    if p:
        return p
    vision_default = _default_vision_service_account_path()
    if vision_default.is_file():
        return str(vision_default)
    p2 = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if p2:
        return p2
    return (getattr(settings, "IMAGE_LOCALIZATION_GCP_KEY_FILE", None) or "").strip()


def _escape_sheet_title(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


def _column_letters_one_based(index: int) -> str:
    """Cột 1-based: 1=A, 26=Z, 27=AA."""
    if index < 1:
        return "A"
    n = index
    parts: List[str] = []
    while n > 0:
        n, r = divmod(n - 1, 26)
        parts.append(chr(65 + r))
    return "".join(reversed(parts))


def _google_sheets_ssl_verify() -> bool:
    raw = (os.getenv("GOOGLE_SHEETS_SSL_VERIFY") or "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _get_sheets_service():
    import certifi
    import httplib2
    import requests
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2 import service_account
    from google_auth_httplib2 import AuthorizedHttp
    from googleapiclient.discovery import build

    path = _credentials_path()
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(
            "Thiếu file JSON service account (GOOGLE_SHEETS_SKU_CREDENTIALS_PATH, "
            "GOOGLE_APPLICATION_CREDENTIALS hoặc IMAGE_LOCALIZATION_GCP_KEY_FILE)."
        )
    ssl_verify = _google_sheets_ssl_verify()
    if not ssl_verify:
        logger.warning(
            "GOOGLE_SHEETS_SSL_VERIFY=false — bỏ qua xác minh SSL Google API (chỉ dev/local)."
        )

    creds = service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
    session = requests.Session()
    if ssl_verify:
        session.verify = certifi.where()
    else:
        import ssl
        import urllib3
        from requests.adapters import HTTPAdapter

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        class _NoVerifyHTTPAdapter(HTTPAdapter):
            def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                pool_kwargs["ssl_context"] = ctx
                return super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)

        session.mount("https://", _NoVerifyHTTPAdapter())
        session.verify = False
    creds.refresh(GoogleAuthRequest(session=session))
    if ssl_verify:
        http = httplib2.Http(ca_certs=certifi.where(), timeout=300)
    else:
        http = httplib2.Http(disable_ssl_certificate_validation=True, timeout=300)
    authed_http = AuthorizedHttp(creds, http=http)
    return build("sheets", "v4", http=authed_http, cache_discovery=False)


def _sheet_title_for_gid(service: Any, spreadsheet_id: str, sheet_gid: int) -> str:
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in meta.get("sheets", []):
        props = sheet.get("properties") or {}
        if props.get("sheetId") == sheet_gid:
            return props.get("title") or ""
    raise ValueError(f"Không tìm thấy tab sheetId={sheet_gid} trong spreadsheet.")


def _values_batch_update(
    service: Any,
    spreadsheet_id: str,
    data_chunks: List[Dict[str, Any]],
) -> None:
    """Google values.batchUpdate: gom range; chia nhóm tránh payload / quota."""
    chunk_size = 100
    for i in range(0, len(data_chunks), chunk_size):
        part = data_chunks[i : i + chunk_size]
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "USER_ENTERED",
                "data": part,
            },
        ).execute()
