"""Chạy một lần kiểm tra nguồn PDP và in trường products trước/sau (xác nhận commit DB)."""
from __future__ import annotations

from sqlalchemy import or_

from app.db.session import SessionLocal
from app.models.product import Product
from app.services.import_source_ids import legacy_mirror_link_ilike_patterns
from app.services.source_stock_checker import (
    _link_eligible_for_source_stock_check,
    check_product_source_stock,
)


def pick_one_id() -> tuple[int, str, str] | None:
    db = SessionLocal()
    try:
        row = (
            db.query(Product.id)
            .filter(Product.is_active == True)  # noqa: E712
            .filter(Product.link_default.isnot(None))
            .filter(
                or_(
                    *[Product.link_default.ilike(p) for p in legacy_mirror_link_ilike_patterns()],
                    Product.link_default.ilike("%1688.com%"),
                    Product.link_default.ilike("%vipomall.vn%"),
                    Product.link_default.ilike("%taobao.com%"),
                    Product.link_default.ilike("%tmall.com%"),
                )
            )
            .order_by(Product.id.asc())
            .first()
        )
        if not row:
            return None
        full = db.query(Product).filter(Product.id == row.id).first()
        if not full or not _link_eligible_for_source_stock_check(full.link_default or ""):
            return None
        return int(full.id), (full.product_id or "").strip(), (full.link_default or "").strip()[:100]
    finally:
        db.close()


def snapshot(pid: int) -> dict:
    db = SessionLocal()
    try:
        p = db.query(Product).filter(Product.id == pid).first()
        if not p:
            return {}
        return {
            "id": p.id,
            "source_stock_status": p.source_stock_status,
            "source_stock_checked_at": p.source_stock_checked_at,
            "source_stock_next_check_at": p.source_stock_next_check_at,
            "source_stock_error": (p.source_stock_error or "")[:200] or None,
            "available": p.available,
        }
    finally:
        db.close()


def main() -> None:
    picked = pick_one_id()
    if not picked:
        print("NO_PRODUCT: không có SP active + link hợp lệ (1688/vipomall/taobao…).")
        raise SystemExit(1)
    pid, code, link = picked
    print("PICKED", {"db_id": pid, "product_code": code, "link_prefix": link})

    before = snapshot(pid)
    print("BEFORE_DB", before)

    print("RUNNING check_product_source_stock (CSSBuy → Vipomall — có thể ~15–90s)…")
    result = check_product_source_stock(pid)
    st = getattr(result, "status", None) if result is not None else None
    err = (getattr(result, "error", None) or "").strip()
    print(
        "RESULT",
        {"status": st, "error_prefix": (err[:180] + "…") if len(err) > 180 else err or None},
    )

    after = snapshot(pid)
    print("AFTER_DB", after)

    chk_at_changed = before.get("source_stock_checked_at") != after.get("source_stock_checked_at")
    status_ok = bool(after.get("source_stock_checked_at"))
    print("WRITE_CONFIRM", {"checked_at_changed_or_set": chk_at_changed, "has_checked_at": status_ok})


if __name__ == "__main__":
    main()
