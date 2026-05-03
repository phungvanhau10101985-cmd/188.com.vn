#!/usr/bin/env python3
"""
Đồng bộ bảng loyalty_tiers (trang /admin/loyalty) qua file JSON.

Dữ liệu không nằm trong frontend — API đọc/ghi PostgreSQL. Luồng:
  1) Export trên máy đang có đúng dữ liệu (DATABASE_URL trong backend/.env).
  2) Copy file JSON lên VPS.
  3) Import trên VPS (backend/.env trỏ DB production).

Ví dụ:
  cd backend
  python scripts/sync_loyalty_tiers_json.py export loyalty_tiers.json

  python scripts/sync_loyalty_tiers_json.py import loyalty_tiers.json
  python scripts/sync_loyalty_tiers_json.py import loyalty_tiers.json --dry-run

Import khớp theo trường name (unique): có thì UPDATE, không có thì INSERT.
Không xóa hạng thiếu trong file — tránh mất dữ liệu production nhầm.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal
from typing import Any, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import SessionLocal  # noqa: E402
from app.models.loyalty import LoyaltyTier  # noqa: E402


def _tier_to_dict(row: LoyaltyTier) -> dict[str, Any]:
    return {
        "name": row.name,
        "min_spend": str(row.min_spend),
        "discount_percent": float(row.discount_percent),
        "description": row.description or "",
    }


def cmd_export(path: str | None) -> None:
    db = SessionLocal()
    try:
        rows = db.query(LoyaltyTier).order_by(LoyaltyTier.min_spend.asc()).all()
        data = [_tier_to_dict(r) for r in rows]
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"Đã ghi {len(data)} hạng → {path}")
        else:
            print(text)
    finally:
        db.close()


def cmd_import(path: str, *, dry_run: bool) -> None:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        raise SystemExit("File JSON phải là mảng các object.")

    db = SessionLocal()
    try:
        for i, item in enumerate(raw):
            if not isinstance(item, dict):
                raise SystemExit(f"Dòng {i}: không phải object.")
            name = (item.get("name") or "").strip()
            if not name:
                raise SystemExit(f"Dòng {i}: thiếu name.")
            try:
                min_spend = Decimal(str(item.get("min_spend", "0")))
            except Exception:
                raise SystemExit(f"Dòng {i}: min_spend không hợp lệ.")
            discount = float(item.get("discount_percent", 0))
            desc = item.get("description")
            if desc is None:
                desc = ""
            desc = str(desc)

            existing = db.query(LoyaltyTier).filter(LoyaltyTier.name == name).first()
            if existing:
                if (
                    existing.min_spend == min_spend
                    and float(existing.discount_percent) == discount
                    and (existing.description or "") == desc
                ):
                    print(f"  [giữ nguyên] {name}")
                    continue
                print(f"  [UPDATE] {name}: min_spend={min_spend}, %={discount}")
                if not dry_run:
                    existing.min_spend = min_spend
                    existing.discount_percent = discount
                    existing.description = desc or None
            else:
                print(f"  [INSERT] {name}: min_spend={min_spend}, %={discount}")
                if not dry_run:
                    db.add(
                        LoyaltyTier(
                            name=name,
                            min_spend=min_spend,
                            discount_percent=discount,
                            description=desc or None,
                        )
                    )
        if dry_run:
            print("--dry-run: không ghi DB.")
        else:
            db.commit()
            print(f"Đã áp dụng {len(raw)} mục từ {path}.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Export / import loyalty_tiers JSON.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("export", help="Đọc DB hiện tại → JSON")
    pe.add_argument(
        "out",
        nargs="?",
        default=None,
        help="Đường dẫn file .json (bỏ qua = in ra stdout)",
    )

    pi = sub.add_parser("import", help="Đọc JSON → upsert vào DB hiện tại")
    pi.add_argument("path", help="File .json")
    pi.add_argument("--dry-run", action="store_true", help="Chỉ in thay đổi, không commit")

    args = p.parse_args()
    if args.cmd == "export":
        cmd_export(args.out)
    else:
        cmd_import(args.path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
