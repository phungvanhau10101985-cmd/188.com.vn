#!/usr/bin/env python3
"""
Tạo banner AI CMSN / sale / kho còn thiếu. Mỗi lần mặc định 1 ảnh Gemini.

Usage (từ backend/, PYTHONPATH=.):
  .venv/bin/python scripts/ensure_daily_banners.py
  .venv/bin/python scripts/ensure_daily_banners.py --max-create 8 --no-notify
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.services.marketing_banner import ensure_daily_banners


def main() -> int:
    parser = argparse.ArgumentParser(description="Tạo banner marketing còn thiếu")
    parser.add_argument(
        "--max-create",
        type=int,
        default=1,
        help="Số ảnh Gemini tối đa trong lần chạy này (mặc định 1)",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Không gửi email preview tới admin",
    )
    args = parser.parse_args()
    db = SessionLocal()
    try:
        result = ensure_daily_banners(
            db,
            max_create=max(0, int(args.max_create)),
            notify_admin=not args.no_notify,
        )
        print(json.dumps(result, ensure_ascii=False))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
