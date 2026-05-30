#!/usr/bin/env python3
"""
Hủy cứng job bản địa hóa ảnh trên VPS (khi UI/API hủy ngay không được).

Usage (từ backend/, sau source .venv/bin/activate):
  python scripts/cancel_image_localization_job.py
  python scripts/cancel_image_localization_job.py 7cc916e4e5b241519ed681b3a46a8f23
  python scripts/cancel_image_localization_job.py --all-active
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.crud import image_localization_job as job_crud
from app.models.product import Product
from app.models.image_localization_job import ImageLocalizationJob


def _pkill_imgloc(job_id: str) -> None:
    short = (job_id or "").strip()[:8]
    if not short:
        return
    subprocess.run(
        ["pkill", "-f", f"imgloc-{short}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def cancel_one(db, job_id: str, *, delete_row: bool = False) -> None:
    jid = (job_id or "").strip()
    if not jid:
        return
    row = job_crud.get_job(db, jid)
    if not row:
        print(f"  ❌ Không thấy job trong DB: {jid}")
        return

    print(f"  Trước: status={row.status!r} cancel_requested={row.cancel_requested} current={row.current_product_id!r}")

    ids = list(row.queue_product_ids or [])
    if row.current_product_id:
        ids.append(row.current_product_id)
    ids = list(dict.fromkeys(str(x).strip() for x in ids if str(x).strip()))

    if ids:
        n = (
            db.query(Product)
            .filter(
                Product.product_id.in_(ids),
                Product.image_localization_status == "processing",
            )
            .update(
                {Product.image_localization_status: "pending", Product.image_localization_error: None},
                synchronize_session=False,
            )
        )
        print(f"  Reset {n} SP processing → pending")
    else:
        n = 0

    now = datetime.now(timezone.utc)
    job_crud.patch_job(
        db,
        jid,
        {
            "status": "cancelled",
            "phase": "cancelled",
            "cancel_requested": True,
            "current_product_id": None,
            "message": "Hủy cứng bằng scripts/cancel_image_localization_job.py",
            "finished_at": now,
        },
    )
    db.commit()
    _pkill_imgloc(jid)

    if delete_row:
        row2 = job_crud.get_job(db, jid)
        if row2:
            db.delete(row2)
            db.commit()
        print(f"  ✅ Đã xóa dòng job khỏi DB: {jid}")
    else:
        row2 = job_crud.get_job(db, jid)
        print(f"  Sau: status={row2.status if row2 else None!r} — chạy: pm2 restart 188-api")


def cancel_all_active(db) -> None:
    rows = (
        db.query(ImageLocalizationJob)
        .filter(ImageLocalizationJob.status.in_(("queued", "running")))
        .all()
    )
    if not rows:
        print("Không có job queued/running trong DB.")
        return
    for row in rows:
        print(f"\n==> {row.job_id}")
        cancel_one(db, row.job_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Hủy cứng job bản địa hóa ảnh")
    parser.add_argument("job_id", nargs="?", help="job_id (UUID). Bỏ trống = job running mới nhất")
    parser.add_argument("--all-active", action="store_true", help="Hủy mọi job queued/running")
    parser.add_argument("--delete", action="store_true", help="Xóa luôn dòng job sau khi cancelled")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.all_active:
            cancel_all_active(db)
            return

        jid = (args.job_id or "").strip()
        if not jid:
            row = (
                db.query(ImageLocalizationJob)
                .filter(ImageLocalizationJob.status.in_(("queued", "running")))
                .order_by(ImageLocalizationJob.updated_at.desc())
                .first()
            )
            if not row:
                print("Không có job queued/running — không làm gì.")
                return
            jid = row.job_id
            print(f"Dùng job mới nhất: {jid}")

        print(f"\n==> Hủy job {jid}")
        cancel_one(db, jid, delete_row=args.delete)
    finally:
        db.close()

    print("\n⚠️  Bắt buộc: pm2 restart 188-api  (dừng thread/process worker cũ)")
    print("    Sau đó F5 trang admin → Xóa card job nếu còn hiện.")


if __name__ == "__main__":
    main()
