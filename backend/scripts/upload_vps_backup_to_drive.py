#!/usr/bin/env python3
"""CLI: upload file backup .tar.gz lên Google Drive (dùng sau bash deploy/backup-vps.sh)."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.vps_backup_drive import upload_backup_archive  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: upload_vps_backup_to_drive.py /path/to/backup-188-YYYYMMDD-HHMMSS.tar.gz", file=sys.stderr)
        return 2
    archive = Path(sys.argv[1])
    status, link, err = upload_backup_archive(archive)
    if status == "skipped":
        print("Google Drive upload skipped (VPS_BACKUP_DRIVE_ENABLED=false hoặc chưa cấu hình).")
        return 0
    if status == "success":
        print(f"OK — Google Drive: {link or '(no link)'}")
        return 0
    print(f"FAIL — {err or 'unknown error'}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
