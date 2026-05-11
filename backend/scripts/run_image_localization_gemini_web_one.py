#!/usr/bin/env python3
"""
Chạy bản địa hóa ảnh cho MỘT product_id — luôn dùng Gemini trên trình duyệt (Playwright + cookie/profile).

Chạy từ thư mục backend (cần DATABASE_URL, Bunny, cookie/profile như backend chạy thật):

  cd backend
  python scripts/run_image_localization_gemini_web_one.py A1048492644305a188M3366

Tùy chọn:
  --no-force   chỉ các SP đang pending/failed/null (như UI không tick «chạy lại»).
  --dry-run    xử lý ảnh nhưng không ghi các URL mới vào product (Ảnh Bunny vẫn có thể được tạo).

Yêu cầu Gemini Web:
  - Cookie đã POST qua admin API hoặc file IMAGE_LOCALIZATION_GEMINI_COOKIE_FILE
  - Hoặc Chrome profile PersistentContext (IMAGE_LOCALIZATION_CHROME_PROFILE_PATH / runtime/chrome-profile).
  - Mặc định backend IMAGE_LOCALIZATION_PLAYWRIGHT_HEADLESS=true (không cửa sổ). Muốn xem trình duyệt: đặt false trong .env.

Khi có IMAGE_LOCALIZATION_AI_IMAGE_EXPLICIT_ONLY=true trong .env:
  hoặc bật product_info.image_localization.allow_ai_models trên SP, hoặc script đã ép allow_ai_image_models=True.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        load_dotenv(ROOT.parent / ".env")
    except ImportError:
        pass


def main() -> int:
    load_env()

    parser = argparse.ArgumentParser(description="Bản địa hóa ảnh 1 SP — Gemini Web (Playwright).")
    parser.add_argument("product_id", help="Ví dụ: A1048492644305a188M3366")
    parser.add_argument("--language", default="vi", help="Mặc định vi")
    parser.add_argument("--no-force", action="store_true", help="Không ép chạy lại ảnh đã xử lý")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run")
    args = parser.parse_args()

    from app.db.session import SessionLocal
    from app.models.product import Product
    from app.services.image_localization_service import ProductImageLocalizationService

    db = SessionLocal()
    try:
        pid = (args.product_id or "").strip()
        prod = db.query(Product).filter(Product.product_id == pid).first()
        if prod is None:
            print(json.dumps({"ok": False, "error": f"Không có sản phẩm product_id={pid}"}, ensure_ascii=False))
            return 1

        svc = ProductImageLocalizationService(
            language=args.language,
            force=not args.no_force,
            dry_run=bool(args.dry_run),
            gemini_mode="web",
            allow_ai_image_models=True,
        )
        try:
            out = svc.process_product(db, prod, should_cancel=None)
        finally:
            svc.close()

        print(json.dumps({"ok": True, "product_id": pid, "result": out}, ensure_ascii=False, indent=2))
        return 0 if out.get("status") != "failed" else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
