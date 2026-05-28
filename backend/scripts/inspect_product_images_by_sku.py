"""
In URL ảnh của 1 sản phẩm theo SKU (cột code) — kiểm tra DB trực tiếp.

  cd /var/www/188.com.vn/backend
  source .venv/bin/activate
  python scripts/inspect_product_images_by_sku.py O1862
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.services.alicdn_urls import (  # noqa: E402
    normalize_product_image_url,
    url_needs_image_normalization,
)

_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)


def _find_product(db, sku: str) -> Product | None:
    s = (sku or "").strip().upper()
    if not s:
        return None
    p = db.query(Product).filter(Product.code.ilike(s)).first()
    if p:
        return p
    p = db.query(Product).filter(Product.product_id.ilike(f"%{s}%")).first()
    if p:
        return p
    p = db.query(Product).filter(Product.product_id.ilike(f"%a188{s}%")).first()
    return p


def _collect_urls(field: str, value: Any, out: List[Tuple[str, str]]) -> None:
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("http"):
            out.append((field, s))
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            _collect_urls(f"{field}[{i}]", item, out)
    elif isinstance(value, dict):
        for k, item in value.items():
            _collect_urls(f"{field}.{k}" if field else str(k), item, out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Kiểm tra URL ảnh SP theo SKU")
    parser.add_argument("sku", help="SKU nội bộ, vd O1862")
    args = parser.parse_args()

    print("DATABASE:", str(engine.url).replace(str(engine.url.password or ""), "***"))

    db = SessionLocal()
    p = _find_product(db, args.sku)
    if not p:
        print(f"Không tìm thấy sản phẩm với SKU/code «{args.sku}».")
        db.close()
        return 1

    print(f"\nproduct_id: {p.product_id}")
    print(f"code (SKU): {p.code}")
    print(f"name: {(p.name or '')[:120]}")

    pairs: List[Tuple[str, str]] = []
    payload = {
        "main_image": p.main_image,
        "images": p.images,
        "gallery": p.gallery,
        "colors": p.colors,
        "product_info": p.product_info,
        "description": p.description,
    }
    for field, value in payload.items():
        if value is not None:
            _collect_urls(field, value, pairs)

    bad = 0
    print(f"\nTổng URL ảnh tìm thấy: {len(pairs)}")
    print("-" * 80)
    for field, url in pairs:
        needs = url_needs_image_normalization(url)
        flag = "OK" if not needs else "BAD"
        if needs:
            bad += 1
        print(f"[{flag}] {field}")
        print(f"  DB:   {url[:240]}")
        if needs:
            print(f"  FIX:  {normalize_product_image_url(url)[:240]}")
        if ".jpg_" in url and needs:
            print("  ^ có hậu tố sau .jpg đầu tiên — cần migrate")
        if ".webp.jpg" in url.lower():
            print("  ^ .webp.jpg — cần bỏ .jpg thừa")

    print("-" * 80)
    print(f"URL cần sửa: {bad} / {len(pairs)}")
    if bad == 0:
        print("✅ DB của SP này đã chuẩn. Nếu web vẫn thấy _800x800q90 → frontend resize, không phải DB.")

    db.close()
    engine.dispose()
    return 0 if bad == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
