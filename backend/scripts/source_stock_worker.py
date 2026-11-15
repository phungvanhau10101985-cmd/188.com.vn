"""Process PM2 riêng: kiểm tra tồn kho nguồn bằng Playwright.

Không import main.py — không mở uvicorn, không resume job ảnh, không warm storefront.
Chạy từ thư mục backend:

    python scripts/source_stock_worker.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.source_stock_checker import run_source_stock_worker_forever


def main() -> None:
    run_source_stock_worker_forever()


if __name__ == "__main__":
    main()
