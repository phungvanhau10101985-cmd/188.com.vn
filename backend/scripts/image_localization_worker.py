"""Process PM2 riêng: chạy job bản địa hóa ảnh.

Không import main.py — không mở uvicorn. API chỉ ghi job queued vào DB.
Chạy từ thư mục backend:

    python scripts/image_localization_worker.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Đặt trước khi import settings. .env của API để resume=false để uvicorn không nhận job.
os.environ["IMAGE_LOCALIZATION_JOB_RESUME_ON_STARTUP"] = "true"
os.environ["IMAGE_LOCALIZATION_EMBEDDED_IN_API"] = "false"

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from app.services.counterfeit_gemini_batch import start_counterfeit_batch_poller
from app.services.gemini_http import install_gemini_key_header_transport
from app.services.image_localization_job_runtime import run_image_localization_worker_forever


def main() -> None:
    install_gemini_key_header_transport()
    start_counterfeit_batch_poller()
    run_image_localization_worker_forever()


if __name__ == "__main__":
    main()
