"""Upload file backup VPS lên Google Drive (service account + folder được share)."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

DRIVE_SCOPES = ("https://www.googleapis.com/auth/drive.file",)
ARCHIVE_NAME_RE = re.compile(r"^backup-188-\d{8}-\d{6}\.tar\.gz$")


def _default_vision_service_account_path() -> Path:
    return Path(__file__).resolve().parents[2] / "runtime" / "image_localization" / "gcp-vision-service-account.json"


def _credentials_path() -> str:
    raw = (getattr(settings, "VPS_BACKUP_DRIVE_CREDENTIALS_PATH", None) or "").strip()
    if raw:
        return raw
    sheets_path = (getattr(settings, "GOOGLE_SHEETS_SKU_CREDENTIALS_PATH", None) or "").strip()
    if sheets_path:
        return sheets_path
    vision_default = _default_vision_service_account_path()
    if vision_default.is_file():
        return str(vision_default)
    p2 = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if p2:
        return p2
    return (getattr(settings, "IMAGE_LOCALIZATION_GCP_KEY_FILE", None) or "").strip()


def is_drive_upload_enabled() -> bool:
    return bool(getattr(settings, "VPS_BACKUP_DRIVE_ENABLED", False))


def is_drive_upload_configured() -> bool:
    if not is_drive_upload_enabled():
        return False
    folder_id = (getattr(settings, "VPS_BACKUP_DRIVE_FOLDER_ID", None) or "").strip()
    if not folder_id:
        return False
    path = _credentials_path()
    return bool(path and os.path.isfile(path))


def drive_settings_payload() -> dict:
    enabled = is_drive_upload_enabled()
    folder_id = (getattr(settings, "VPS_BACKUP_DRIVE_FOLDER_ID", None) or "").strip()
    keep = int(getattr(settings, "VPS_BACKUP_DRIVE_KEEP_COUNT", 5) or 5)
    creds_ok = bool(_credentials_path() and os.path.isfile(_credentials_path()))
    return {
        "drive_upload_enabled": enabled,
        "drive_upload_configured": enabled and bool(folder_id) and creds_ok,
        "drive_folder_id": folder_id or None,
        "drive_keep_count": max(1, keep),
        "drive_credentials_configured": creds_ok,
    }


def _google_ssl_verify() -> bool:
    raw = (os.getenv("GOOGLE_SHEETS_SSL_VERIFY") or "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _get_drive_service():
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
            "Thiếu file JSON service account (VPS_BACKUP_DRIVE_CREDENTIALS_PATH hoặc GOOGLE_SHEETS_SKU_CREDENTIALS_PATH)."
        )

    ssl_verify = _google_ssl_verify()
    creds = service_account.Credentials.from_service_account_file(path, scopes=DRIVE_SCOPES)
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

    authed_http = AuthorizedHttp(creds, http=httplib2.Http(timeout=300))
    if ssl_verify:
        authed_http.http.disable_ssl_certificate_validation = False
    else:
        authed_http.http.disable_ssl_certificate_validation = True

    creds.refresh(GoogleAuthRequest(session=session))
    return build("drive", "v3", http=authed_http, cache_discovery=False)


def _list_backup_files_in_folder(service, folder_id: str) -> List[Dict[str, Any]]:
    query = (
        f"'{folder_id}' in parents and trashed=false "
        "and name contains 'backup-188-' and mimeType='application/gzip'"
    )
    files: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    while True:
        resp = (
            service.files()
            .list(
                q=query,
                spaces="drive",
                fields="nextPageToken, files(id,name,createdTime,size)",
                orderBy="createdTime desc",
                pageSize=100,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        for item in resp.get("files") or []:
            name = str(item.get("name") or "")
            if ARCHIVE_NAME_RE.match(name):
                files.append(item)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    files.sort(key=lambda x: str(x.get("createdTime") or ""), reverse=True)
    return files


def _format_drive_upload_error(exc: Exception) -> str:
    raw = str(exc)
    if "accessNotConfigured" in raw or "has not been used in project" in raw:
        m = re.search(r"project[= ](\d+)", raw)
        pid = m.group(1) if m else "?"
        return (
            "Chưa bật Google Drive API trên Google Cloud (project "
            f"{pid}). Vào console.cloud.google.com → APIs & Services → "
            "Library → tìm “Google Drive API” → Enable, đợi 1–2 phút rồi backup lại. "
            "Folder Drive phải share quyền Editor cho email service account trong file JSON."
        )
    if "404" in raw and ("not found" in raw.lower() or "Not Found" in raw):
        return (
            "Không tìm thấy folder Drive — kiểm tra VPS_BACKUP_DRIVE_FOLDER_ID "
            "và share folder cho service account (Editor)."
        )
    if "403" in raw and "insufficient" in raw.lower():
        return (
            "Service account không có quyền ghi folder Drive — share folder Editor "
            "cho email trong file JSON service account."
        )
    return raw[:2000]


def _prune_old_drive_backups(service, folder_id: str, keep_count: int) -> int:
    keep = max(1, int(keep_count or 1))
    files = _list_backup_files_in_folder(service, folder_id)
    deleted = 0
    for item in files[keep:]:
        fid = item.get("id")
        if not fid:
            continue
        try:
            service.files().delete(fileId=fid, supportsAllDrives=True).execute()
            deleted += 1
            logger.info("VPS backup Drive: deleted old file %s", item.get("name"))
        except Exception:
            logger.exception("VPS backup Drive: failed to delete %s", item.get("name"))
    return deleted


def upload_backup_archive(archive_path: Path) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Upload .tar.gz lên Google Drive folder đã cấu hình.
    Returns: (status, web_link, error_message)
    status: success | failed | skipped
    """
    if not is_drive_upload_enabled():
        return "skipped", None, None

    folder_id = (getattr(settings, "VPS_BACKUP_DRIVE_FOLDER_ID", None) or "").strip()
    if not folder_id:
        return "failed", None, "Thiếu VPS_BACKUP_DRIVE_FOLDER_ID trong .env"

    path = archive_path.resolve()
    if not path.is_file():
        return "failed", None, f"Không tìm thấy file backup: {path}"

    if not ARCHIVE_NAME_RE.match(path.name):
        return "failed", None, f"Tên file không hợp lệ: {path.name}"

    try:
        from googleapiclient.http import MediaFileUpload

        service = _get_drive_service()
        file_metadata = {"name": path.name, "parents": [folder_id]}
        media = MediaFileUpload(str(path), mimetype="application/gzip", resumable=True)
        created = (
            service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink, webContentLink",
                supportsAllDrives=True,
            )
            .execute()
        )
        web_link = created.get("webViewLink") or created.get("webContentLink")
        keep_count = int(getattr(settings, "VPS_BACKUP_DRIVE_KEEP_COUNT", 5) or 5)
        _prune_old_drive_backups(service, folder_id, keep_count)
        logger.info("VPS backup Drive upload OK: %s → %s", path.name, web_link)
        return "success", str(web_link) if web_link else None, None
    except Exception as exc:
        logger.exception("VPS backup Drive upload failed for %s", path)
        return "failed", None, _format_drive_upload_error(exc)
