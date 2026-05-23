"""Tải scripts/tra-cuu.js (gitignore) — chạy dl_tra_cuu_js.py nếu chưa có."""
from __future__ import annotations

from pathlib import Path

_TRA_CUU = Path(__file__).resolve().parent / "tra-cuu.js"


def load_tra_cuu_js() -> str:
    if not _TRA_CUU.is_file():
        raise FileNotFoundError(
            "Thiếu scripts/tra-cuu.js (không commit). Chạy: python backend/scripts/dl_tra_cuu_js.py"
        )
    return _TRA_CUU.read_text(encoding="utf-8")
