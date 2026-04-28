#!/usr/bin/env python3
"""
Upload toàn bộ ảnh (và cố ý chỉ các đuôi ảnh) trong frontend/public lên Bunny Storage.
Đường dẫn trên Bunny trùng với đường dẫn URL (vd: images/info/foo.png).

Chạy từ thư mục backend:
  python scripts/upload_frontend_public_to_bunny.py
  python scripts/upload_frontend_public_to_bunny.py --dry-run

Cần trong .env: BUNNY_STORAGE_ZONE_NAME, BUNNY_STORAGE_ACCESS_KEY, NEXT_PUBLIC_CDN_URL hoặc BUNNY_CDN_PUBLIC_BASE.

Thư mục mặc định: <repo>/frontend/public — ghi đè: --public-dir path
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent


def load_env():
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        load_dotenv(REPO_ROOT / ".env")
    except ImportError:
        pass


IMG_EXT = frozenset(
    ".png .jpg .jpeg .webp .gif .svg .avif .bmp .ico .jfif".split()
)


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--public-dir",
        default=str(REPO_ROOT / "frontend" / "public"),
        help="Thư mục Next public/",
    )
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    load_env()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    from app.core.config import settings

    zone = settings.BUNNY_STORAGE_ZONE_NAME
    key = settings.BUNNY_STORAGE_ACCESS_KEY
    cdn = settings.BUNNY_CDN_PUBLIC_BASE

    if not args.dry_run and (not zone or not key):
        print("Thiếu BUNNY_STORAGE_ZONE_NAME và/hoặc BUNNY_STORAGE_ACCESS_KEY trong .env")
        sys.exit(2)

    public_dir = Path(args.public_dir).resolve()
    if not public_dir.is_dir():
        print(f"Không thấy thư mục: {public_dir}")
        sys.exit(1)

    prefix = settings.BUNNY_WEB_PUBLIC_PREFIX
    # Mặc định không prefix — object path = relative từ public/ (vd: images/info/a.png)

    from app.services.bunny_storage import upload_file_to_zone

    count = 0
    skipped = []
    for f in sorted(public_dir.rglob("*")):
        if not f.is_file():
            continue
        if f.suffix.lower() not in IMG_EXT:
            continue
        rel = f.relative_to(public_dir).as_posix()
        remote = f"{prefix}/{rel}" if prefix else rel
        if args.dry_run:
            print(f"dry-run  PUT …/{remote}")
            count += 1
            continue
        try:
            data = f.read_bytes()
            upload_file_to_zone(zone_name=zone, access_key=key, remote_path=remote, data=data)
            url = (cdn + "/" + remote) if cdn else remote
            print(f"ok  {remote}  →  {url}")
            count += 1
        except Exception as e:
            skipped.append((rel, str(e)))

    print(f"[xong] {count} file" + (f", lỗi {len(skipped)}" if skipped else ""))
    for rel, err in skipped[:15]:
        print(f"  Lỗi {rel}: {err[:200]}")


if __name__ == "__main__":
    main()
