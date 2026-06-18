#!/usr/bin/env python3
"""Kiểm tra quyền truy cập folder Google Drive cho VPS backup.

Usage:
  set VPS_BACKUP_DRIVE_FOLDER_ID=1NE152YF63m-jk_5tb3AIGnzAtPEcaYYu
  set VPS_BACKUP_DRIVE_ENABLED=true
  set GOOGLE_SHEETS_SKU_CREDENTIALS_PATH=path/to/service-account.json
  python scripts/test_vps_backup_drive_folder.py

  python scripts/test_vps_backup_drive_folder.py --folder-id 1NE152YF63m-jk_5tb3AIGnzAtPEcaYYu
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.services.vps_backup_drive import (  # noqa: E402
    _credentials_path,
    _format_drive_upload_error,
    _get_drive_service,
    _validate_folder_for_service_account_upload,
    drive_settings_payload,
    is_drive_upload_configured,
)


def _check_folder(service, folder_id: str) -> tuple[bool, str]:
    preflight = _validate_folder_for_service_account_upload(service, folder_id)
    if preflight:
        return False, preflight
    try:
        meta = (
            service.files()
            .get(
                fileId=folder_id,
                fields="id,name,mimeType,driveId,capabilities",
                supportsAllDrives=True,
            )
            .execute()
        )
    except Exception as exc:
        return False, _format_drive_upload_error(exc)

    mime = str(meta.get("mimeType") or "")
    name = str(meta.get("name") or "?")
    drive_id = meta.get("driveId") or "?"
    if mime != "application/vnd.google-apps.folder":
        return False, f"ID trỏ tới '{name}' (mime={mime}) — cần folder, không phải file."
    return True, (
        f"OK — folder '{name}' trong Shared drive ({drive_id}), service account có thể upload."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Google Drive folder cho VPS backup")
    parser.add_argument(
        "--folder-id",
        default=os.getenv("VPS_BACKUP_DRIVE_FOLDER_ID", "").strip(),
        help="Folder ID (mặc định từ VPS_BACKUP_DRIVE_FOLDER_ID)",
    )
    parser.add_argument(
        "--wrong-id",
        default="1NF152YF63m-jk_5tb3AlGnzAtPEcaYYu",
        help="ID sai từng thấy trên VPS (so sánh typo)",
    )
    args = parser.parse_args()
    folder_id = (args.folder_id or "").strip()
    wrong_id = (args.wrong_id or "").strip()

    print("==> Cấu hình Drive")
    payload = drive_settings_payload()
    for k, v in payload.items():
        print(f"    {k}: {v}")
    creds = _credentials_path()
    print(f"    credentials_path: {creds or '(trống)'}")
    print(f"    drive_service_account_email: {payload.get('drive_service_account_email') or '(không đọc được)'}")

    if folder_id and wrong_id and folder_id != wrong_id:
        print("\n==> So sánh ID folder")
        print(f"    Đúng (URL bạn gửi): {folder_id}")
        print(f"    Sai (lỗi VPS cũ):   {wrong_id}")
        print("    → Khác nhau — sửa VPS_BACKUP_DRIVE_FOLDER_ID trên VPS rồi pm2 restart 188-api.")

    if not folder_id:
        print("\nLOI: Thiếu --folder-id hoặc VPS_BACKUP_DRIVE_FOLDER_ID", file=sys.stderr)
        return 2
    if not is_drive_upload_configured() and not (creds and os.path.isfile(creds)):
        print(
            "\nLOI: Chưa cấu hình — cần VPS_BACKUP_DRIVE_ENABLED=true, folder ID, "
            "và file JSON service account (GOOGLE_SHEETS_SKU_CREDENTIALS_PATH).",
            file=sys.stderr,
        )
        return 2

    os.environ["VPS_BACKUP_DRIVE_ENABLED"] = "true"
    os.environ["VPS_BACKUP_DRIVE_FOLDER_ID"] = folder_id
    # Reload settings object fields used by _get_drive_service
    settings.VPS_BACKUP_DRIVE_ENABLED = True
    settings.VPS_BACKUP_DRIVE_FOLDER_ID = folder_id

    print(f"\n==> Kiểm tra folder {folder_id}")
    try:
        service = _get_drive_service()
    except Exception as exc:
        print(f"LOI credentials/API: {_format_drive_upload_error(exc)}", file=sys.stderr)
        return 1

    ok, msg = _check_folder(service, folder_id)
    print(f"    {msg}")
    if not ok:
        return 1

    if wrong_id and wrong_id != folder_id:
        print(f"\n==> Thử ID sai ({wrong_id}) — kỳ vọng lỗi")
        _ok_wrong, msg_wrong = _check_folder(service, wrong_id)
        print(f"    {msg_wrong}")

    print("\nOK: Folder Drive sẵn sàng cho upload backup.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
