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

from sqlalchemy import text

from app.db.session import SessionLocal
from app.crud import image_localization_job as job_crud
from app.models.product import Product
from app.models.image_localization_job import ImageLocalizationJob


def _pkill_workers() -> None:
    for pattern in (
        "imgloc-",
        "_multiprocess_job_entry",
        "image_localization_job",
        "image_localization_service",
    ):
        subprocess.run(
            ["pkill", "-9", "-f", pattern],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


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


def _force_cancel_sql(db, job_id: str) -> bool:
    """UPDATE trực tiếp — không bị worker ghi đè khi API đã stop."""
    now = datetime.now(timezone.utc)
    res = db.execute(
        text(
            """
            UPDATE image_localization_jobs
            SET status = 'cancelled',
                phase = 'cancelled',
                cancel_requested = TRUE,
                current_product_id = NULL,
                message = 'Hủy cứng (scripts/cancel_image_localization_job.py)',
                finished_at = :finished_at,
                updated_at = :finished_at
            WHERE job_id = :job_id
            """
        ),
        {"job_id": job_id, "finished_at": now},
    )
    db.commit()
    return (res.rowcount or 0) > 0


def _reset_all_processing(db) -> int:
    return (
        db.query(Product)
        .filter(Product.image_localization_status == "processing")
        .update(
            {Product.image_localization_status: "pending", Product.image_localization_error: None},
            synchronize_session=False,
        )
    )


def cancel_one(db, job_id: str, *, delete_row: bool = False, reset_all_processing: bool = False) -> None:
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

    if reset_all_processing:
        all_n = _reset_all_processing(db)
        db.commit()
        print(f"  Reset toàn bộ SP processing → pending: {all_n}")

    if delete_row:
        db.delete(row)
        db.commit()
        _pkill_imgloc(jid)
        print(f"  ✅ Đã xóa dòng job khỏi DB: {jid}")
        return

    if not _force_cancel_sql(db, jid):
        print(f"  ❌ UPDATE SQL không đổi dòng nào: {jid}")
        return

    _pkill_imgloc(jid)
    row2 = job_crud.get_job(db, jid)
    print(f"  Sau SQL: status={row2.status if row2 else None!r}")
    print(f"  ✅ Xong — chạy: pm2 start 188-api")


def cancel_all_active(db, *, delete_row: bool = False, reset_all_processing: bool = False) -> None:
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
        cancel_one(db, row.job_id, delete_row=delete_row, reset_all_processing=False)
    if reset_all_processing:
        all_n = _reset_all_processing(db)
        db.commit()
        print(f"Reset toàn bộ SP processing → pending: {all_n}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hủy cứng job bản địa hóa ảnh")
    parser.add_argument("job_id", nargs="?", help="job_id (UUID). Bỏ trống = job running mới nhất")
    parser.add_argument("--all-active", action="store_true", help="Hủy mọi job queued/running")
    parser.add_argument("--delete", action="store_true", help="Xóa luôn dòng job khỏi DB")
    parser.add_argument(
        "--nuke",
        action="store_true",
        help="Dọn triệt để: --delete + reset mọi SP processing + pkill worker",
    )
    args = parser.parse_args()

    delete_row = args.delete or args.nuke
    reset_all = args.nuke

    if args.nuke:
        _pkill_workers()

    db = SessionLocal()
    try:
        jid = (args.job_id or "").strip()
        if not jid and not args.all_active:
            row = (
                db.query(ImageLocalizationJob)
                .filter(ImageLocalizationJob.status.in_(("queued", "running")))
                .order_by(ImageLocalizationJob.updated_at.desc())
                .first()
            )
            if row:
                jid = row.job_id
                print(f"Dùng job mới nhất: {jid}")

        if args.all_active:
            cancel_all_active(db, delete_row=delete_row, reset_all_processing=reset_all)
        elif jid:
            print(f"\n==> {'Nuke' if args.nuke else 'Hủy'} job {jid}")
            cancel_one(db, jid, delete_row=delete_row, reset_all_processing=reset_all)
        elif args.nuke and reset_all:
            all_n = _reset_all_processing(db)
            db.commit()
            print(f"Không còn job active — reset toàn bộ SP processing → pending: {all_n}")
        else:
            print("Không có job queued/running — không làm gì.")
    finally:
        db.close()

    print("\n⚠️  Bắt buộc: pm2 start 188-api  (chỉ start sau khi DB đã cancelled)")
    print("    Sau đó F5 trang admin → Xóa card job nếu còn hiện.")


if __name__ == "__main__":
    main()
