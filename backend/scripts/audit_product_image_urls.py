"""
Kiểm tra URL ảnh chưa chuẩn trong DB (đọc trực tiếp từng cột).

  cd /var/www/188.com.vn/backend
  source .venv/bin/activate
  python scripts/audit_product_image_urls.py
  python scripts/audit_product_image_urls.py --limit 20
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from typing import Any, Dict, List

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


def _walk(field: str, value: Any, pid: str, hits: List[Dict[str, str]], counter: Counter) -> None:
    if isinstance(value, str):
        s = value.strip()
        if not s.startswith("http"):
            return
        if url_needs_image_normalization(s):
            counter[field] += 1
            if len(hits) < 30:
                hits.append(
                    {
                        "product_id": pid,
                        "field": field,
                        "before": s[:240],
                        "after": normalize_product_image_url(s)[:240],
                    }
                )
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            _walk(f"{field}[{i}]", item, pid, hits, counter)
    elif isinstance(value, dict):
        for k, item in value.items():
            _walk(f"{field}.{k}" if field else str(k), item, pid, hits, counter)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit URL ảnh sản phẩm trong DB")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số SP quét")
    args = parser.parse_args()

    print("DATABASE:", str(engine.url).replace(str(engine.url.password or ""), "***"))
    db = SessionLocal()
    hits: List[Dict[str, str]] = []
    counter: Counter = Counter()
    scanned = 0
    bad_products = 0

    q = db.query(Product).order_by(Product.id.asc())
    if args.limit:
        q = q.limit(args.limit)

    for p in q.yield_per(200):
        scanned += 1
        before_len = len(hits)
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
                _walk(field, value, p.product_id, hits, counter)
        if len(hits) > before_len:
            bad_products += 1

    db.close()
    engine.dispose()

    print(f"\nScanned products: {scanned}")
    print(f"Products with bad URLs: {bad_products}")
    print(f"Total bad URLs: {sum(counter.values())}")
    print("\nBy column:")
    for field, count in counter.most_common():
        print(f"  {field}: {count}")

    print("\nSamples:")
    for row in hits[:15]:
        print(json.dumps(row, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
