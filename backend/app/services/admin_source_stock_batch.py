"""
Kiểm tra tồn kho nguồn theo từng URL (admin batch): 1688 (cookie Playwright) hoặc hibox.mn (scrape như import).
Không đọc được / lỗi → coi như hết hàng: có thể cập nhật available = 0 trên các sản khớp trong DB.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy import and_, case, exists, func, not_, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.guest_behavior import GuestProductView
from app.models.product import Product
from app.models.user import UserProductView
from app.services.import_batch_url_coercion import FETCH_TARGET_HIBOX, coerce_url_for_excel_batch_import
from app.services.import_hibox_scraper import (
    ImportHiboxError,
    extract_hibox_slug,
    hibox_canonical_scrape_url,
    normalize_product_import_url,
    scrape_hibox_for_import,
)
from app.services.import_1688_scraper import canonical_1688_offer_pc_url, extract_1688_numeric_offer_id
from app.services.source_stock_checker import _evaluate_page_stock

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _find_products_for_1688_offer(db: Session, offer_id: str) -> List[Product]:
    oid = (offer_id or "").strip()
    if not oid.isdigit():
        return []
    prefix_a = f"A{oid}a188"
    q = db.query(Product).filter(
        or_(
            Product.link_default.ilike(f"%/offer/{oid}.htm%"),
            Product.link_default.ilike(f"%/offer/{oid}.html%"),
            Product.link_default.ilike(f"%offerId={oid}%"),
            Product.link_default.ilike(f"%offer/{oid}%"),
            Product.product_id.ilike(f"{prefix_a}%"),
        )
    )
    return list(q.all())


def _find_products_for_hibox_slug(db: Session, slug: str) -> List[Product]:
    s = (slug or "").strip()
    if not s or s == "hibox_import":
        return []
    prefixed = f"hibox_{s}"
    return list(
        db.query(Product)
        .filter(
            or_(
                Product.link_default.ilike(f"%hibox.mn%/v/{s}%"),
                Product.link_default.ilike(f"%/v/{s}%"),
                Product.link_default.ilike(f"%item?id={s}%"),
                Product.product_id.ilike(f"{prefixed}%"),
                Product.product_id == prefixed,
            )
        )
        .all()
    )


def _admin_batch_scan_cooldown_cutoff_sql() -> datetime:
    """Thời điểm: trước đó được coi «quá cổ» và SP được vào lại vòng kiểm tra."""
    days = max(1, int(getattr(settings, "ADMIN_SOURCE_BATCH_SCAN_COOLDOWN_DAYS", 30)))
    return datetime.now(timezone.utc) - timedelta(days=days)


def admin_batch_scan_cooldown_days() -> int:
    return max(1, int(getattr(settings, "ADMIN_SOURCE_BATCH_SCAN_COOLDOWN_DAYS", 30)))


def admin_batch_traffic_view_window_days() -> int:
    """Cửa sổ «có người mở PDP» (guest + user đăng nhập)."""
    return max(1, int(getattr(settings, "ADMIN_SOURCE_BATCH_TRAFFIC_VIEW_WINDOW_DAYS", 30)))


def admin_batch_traffic_gap_days() -> int:
    """Đối SP traffic: chỉ được kiểm tra lại sau N ngày kể từ lần đánh batch gần nhất."""
    return max(1, int(getattr(settings, "ADMIN_SOURCE_BATCH_TRAFFIC_CHECK_GAP_DAYS", 30)))


def _traffic_view_window_since() -> datetime:
    return _utcnow() - timedelta(days=admin_batch_traffic_view_window_days())


def _traffic_recent_check_cutoff() -> datetime:
    return _utcnow() - timedelta(days=admin_batch_traffic_gap_days())


def recent_customer_view_exists(ProductModel: Any, viewed_since_utc: datetime) -> Any:
    """Đúng khi trong ``viewed_since_utc … now`` có ít nhất một dòng PDP view (guest hoặc user)."""
    uex = exists(
        select(UserProductView.id).where(
            UserProductView.product_id == ProductModel.id,
            UserProductView.viewed_at >= viewed_since_utc,
        )
    )
    gex = exists(
        select(GuestProductView.id).where(
            GuestProductView.product_id == ProductModel.id,
            GuestProductView.viewed_at >= viewed_since_utc,
        )
    )
    return or_(uex, gex)


def _batch_ttl_eligibility_expr(ProductModel: Any, *, view_window_since: datetime) -> Any:
    """
    Không PDP traffic trong cửa sổ: TTL của vòng như ADMIN_SOURCE_BATCH_SCAN_COOLDOWN_DAYS.
    Có PDP traffic: chỉ được hàng chờ khi ``admin_source_batch_scanned_at`` null hoặc cũ hơn ADMIN_SOURCE_BATCH_TRAFFIC_CHECK_GAP_DAYS days.
    """
    cold_cut = _admin_batch_scan_cooldown_cutoff_sql()
    traffic_cut = _traffic_recent_check_cutoff()
    has_traffic_views = recent_customer_view_exists(ProductModel, view_window_since)
    cold_ok = or_(ProductModel.admin_source_batch_scanned_at.is_(None), ProductModel.admin_source_batch_scanned_at <= cold_cut)
    traffic_ok = or_(ProductModel.admin_source_batch_scanned_at.is_(None), ProductModel.admin_source_batch_scanned_at <= traffic_cut)
    return or_(and_(not_(has_traffic_views), cold_ok), and_(has_traffic_views, traffic_ok))


def _ttl_ready_filters(ProductModel: Any, domain_l: str, *, active_only: bool) -> tuple[List[Any], datetime]:
    view_since = _traffic_view_window_since()
    filt: List[Any] = [
        *admin_product_source_link_base_filters(ProductModel, domain_l, active_only=active_only),
        _batch_ttl_eligibility_expr(ProductModel, view_window_since=view_since),
    ]
    return filt, view_since


def _admin_batch_queue_priority_order(ProductModel: Any, *, traffic_view_since_utc: datetime):
    rv = recent_customer_view_exists(ProductModel, traffic_view_since_utc)
    tier_traffic = case((rv, 0), else_=1).asc()
    tier_never = case((ProductModel.admin_source_batch_scanned_at.is_(None), 0), else_=1).asc()
    stamp = ProductModel.admin_source_batch_scanned_at.asc().nullsfirst()
    tie = ProductModel.id.asc()
    return (tier_traffic, tier_never, stamp, tie)


def admin_product_source_link_base_filters(
    ProductModel: Any,
    domain: str,
    *,
    active_only: bool,
) -> List[Any]:
    """Bộ lọc link/domain/active — không gồm điều kiện TTL vòng kiểm tra."""
    domain_l = (domain or "1688").strip().lower()
    filters = [
        ProductModel.link_default.isnot(None),
        func.length(func.trim(ProductModel.link_default)) > 8,
    ]
    if active_only:
        filters.append(ProductModel.is_active.is_(True))

    if domain_l == "1688":
        filters.append(
            or_(
                ProductModel.link_default.ilike("%1688.com%"),
                ProductModel.link_default.ilike("%offer.1688%"),
                ProductModel.link_default.ilike("%detail.1688%"),
            )
        )
    else:
        filters.append(
            or_(
                ProductModel.link_default.ilike("%hibox.mn%"),
                ProductModel.link_default.ilike("%taobao1688.kz%"),
                ProductModel.link_default.ilike("%1688.com%"),
                ProductModel.link_default.ilike("%offer.1688%"),
                ProductModel.link_default.ilike("%detail.1688%"),
                ProductModel.link_default.ilike("%taobao.com%"),
                ProductModel.link_default.ilike("%tmall.com%"),
            )
        )

    return filters


def admin_product_source_link_filters(
    ProductModel: Any,
    domain: str,
    *,
    active_only: bool,
) -> List[Any]:
    domain_l = (domain or "1688").strip().lower()
    return _ttl_ready_filters(ProductModel, domain_l, active_only=active_only)[0]


def admin_source_stock_queue_stats(
    db: Session,
    *,
    domain: str,
    active_only: bool,
) -> Dict[str, Any]:
    """
    Đếm sản trong phạm vi miền + link (không TTL) và TTL + traffic PDP:
    - total_in_scope, eligible_now, in_cooldown như trước
    - eligible_with_recent_customer_view / eligible_without_recent_customer_view:tácheligible theo PDP traffic trong cửa sổ
    """
    domain_l = (domain or "1688").strip().lower()
    ttl_days_cold = admin_batch_scan_cooldown_days()
    cold_cut_iso = _admin_batch_scan_cooldown_cutoff_sql().isoformat()
    filt, vu = _ttl_ready_filters(Product, domain_l, active_only=active_only)
    traffic_pv = recent_customer_view_exists(Product, vu)

    base = admin_product_source_link_base_filters(Product, domain_l, active_only=active_only)

    total_in_scope = int(db.query(func.count(Product.id)).filter(*base).scalar() or 0)
    eligible_now = int(db.query(func.count(Product.id)).filter(*filt).scalar() or 0)
    eligible_traffic = int(db.query(func.count(Product.id)).filter(*filt).filter(traffic_pv).scalar() or 0)
    eligible_plain = max(0, eligible_now - eligible_traffic)

    never_q = [*filt, Product.admin_source_batch_scanned_at.is_(None)]
    eligible_never_scanned = int(db.query(func.count(Product.id)).filter(*never_q).scalar() or 0)
    eligible_rescan_after_ttl = max(0, eligible_now - eligible_never_scanned)
    in_cooldown = max(0, total_in_scope - eligible_now)

    return {
        "ok": True,
        "domain": domain_l,
        "active_only": bool(active_only),
        "admin_batch_scan_cooldown_days": ttl_days_cold,
        "admin_batch_traffic_view_window_days": admin_batch_traffic_view_window_days(),
        "admin_batch_traffic_check_gap_days": admin_batch_traffic_gap_days(),
        "cooldown_cutoff_utc_iso": cold_cut_iso,
        "traffic_recent_check_cutoff_utc_iso": _traffic_recent_check_cutoff().isoformat(),
        "traffic_view_since_utc_iso": vu.isoformat(),
        "total_in_scope": total_in_scope,
        "eligible_now": eligible_now,
        "eligible_never_scanned": eligible_never_scanned,
        "eligible_rescan_after_ttl": eligible_rescan_after_ttl,
        "eligible_with_recent_customer_view": eligible_traffic,
        "eligible_without_recent_customer_view": eligible_plain,
        "in_cooldown": in_cooldown,
    }


def admin_collect_distinct_product_urls_from_db(
    db: Session,
    *,
    domain: str,
    limit: int,
    active_only: bool,
) -> Dict[str, Any]:
    domain_l = (domain or "1688").strip().lower()
    filt, vu = _ttl_ready_filters(Product, domain_l, active_only=active_only)
    seen: set[str] = set()
    urls_out: List[str] = []

    chunk_size = 2500
    offset = 0
    scanned_rows = 0
    scan_ceiling_rows = limit * 25 if limit < 6000 else limit * 40

    while len(urls_out) < limit and scanned_rows < scan_ceiling_rows:
        batch = (
            db.query(Product.link_default).filter(*filt).order_by(*_admin_batch_queue_priority_order(Product, traffic_view_since_utc=vu)).offset(offset).limit(chunk_size).all()
        )
        if not batch:
            break
        offset += chunk_size
        scanned_rows += len(batch)
        for (link,) in batch:
            u = str(link).strip().strip('"').strip("'")
            if len(u) < 12:
                continue
            if not u.lower().startswith("http"):
                continue
            if u in seen:
                continue
            seen.add(u)
            urls_out.append(u)
            if len(urls_out) >= limit:
                break

    return {
        "urls": urls_out,
        "count": len(urls_out),
        "domain_filter": domain_l,
        "active_only": active_only,
    }


def run_admin_source_stock_scan_next_from_db(
    db: Session,
    *,
    domain: str,
    active_only: bool = True,
    cursor_after_product_id: int = 0,
) -> Dict[str, Any]:
    """
    Chọn một SP thỏa bộ lọc miền + TTL hàng chờ (SP có PDP traffic được xử lý theo cửa sổ lượt xem và khoảng đợi riêng).
    Thứ tự ưu tiên server:
      1) SP có ít nhất một lượt xem PDP (user hoặc guest session) trong cửa sổ ``ADMIN_SOURCE_BATCH_TRAFFIC_VIEW_WINDOW_DAYS``.
      2) Chưa từng đánh batch hay mốt ``admin_source_batch_scanned_at`` cũ hơn.
      3) Tie-break ``products.id`` tăng dần.

    Biến ``cursor_after_product_id`` giữ chỉ cho tương thích API; không lái queue.
    """
    _ = cursor_after_product_id

    domain_l = (domain or "1688").strip().lower()
    filt, vu = _ttl_ready_filters(Product, domain_l, active_only=active_only)

    prod = (
        db.query(Product)
        .filter(*filt)
        .order_by(*_admin_batch_queue_priority_order(Product, traffic_view_since_utc=vu))
        .first()
    )
    if not prod:
        ttl_days = admin_batch_scan_cooldown_days()
        return {
            "ok": True,
            "done": True,
            "cursor_after_product_id": 0,
            "domain": domain_l,
            "canonical_url": "",
            "classified_out_of_stock": False,
            "raw_status": None,
            "detail": "Không còn sản trong bộ lọc hoặc tất cả đang trong thời gian chờ TTL (đánh dấu đã kiểm tra). Đặt lại đầu hàng chờ hoặc chờ qua số ngày cooldown.",
            "warnings": [],
            "matched_products": [],
            "updated_product_ids": [],
            "matched_count": 0,
            "updates_committed": False,
            "admin_batch_scan_cooldown_days": ttl_days,
        }

    seed_link_default = str(prod.link_default or "").strip().strip('"').strip("'")
    ttl_days = admin_batch_scan_cooldown_days()
    scan = dict(run_admin_source_url_scan(db, url=seed_link_default, domain=domain_l))
    marked_at: datetime | None = None
    try:
        now_stamp = _utcnow()
        row = db.query(Product).filter(Product.id == prod.id).first()
        if row is not None:
            row.admin_source_batch_scanned_at = now_stamp
            db.commit()
            marked_at = now_stamp
    except Exception as exc:
        db.rollback()
        logger.warning("admin_source_batch_scanned_at không ghi được (id=%s): %s", prod.id, exc)

    scan.update(
        {
            "done": False,
            "cursor_after_product_id": prod.id,
            "seed_product_db_id": prod.id,
            "seed_product_name": prod.name or "",
            "seed_link_default": seed_link_default,
            "admin_batch_scan_cooldown_days": ttl_days,
            "seed_admin_batch_scanned_at": marked_at.isoformat() if marked_at else None,
        }
    )
    return scan


def run_admin_source_url_scan(db: Session, *, url: str, domain: str) -> Dict[str, Any]:
    domain_lower = (domain or "").strip().lower()
    if domain_lower not in ("1688", "hibox"):
        return {
            "ok": False,
            "canonical_url": (url or "").strip(),
            "domain": domain_lower,
            "raw_status": "bad_domain",
            "classified_out_of_stock": False,
            "detail": "domain phải là «1688» hoặc «hibox».",
            "matched_products": [],
            "updated_product_ids": [],
            "matched_count": 0,
        }

    canonical_url = (url or "").strip()
    classified_oos = False
    raw_status: str | None = None
    detail: str | None = None
    warnings: List[str] = []
    matched: List[Product] = []

    if domain_lower == "1688":
        oid = extract_1688_numeric_offer_id(canonical_url)
        if not oid:
            classified_oos = True
            raw_status = "bad_url"
            detail = "Không đọc được mã offer 1688 trong URL."
            matched = []
        else:
            open_url = canonical_1688_offer_pc_url(oid) or canonical_url
            canonical_url = open_url
            matched = _find_products_for_1688_offer(db, oid)
            res = _evaluate_page_stock(open_url)
            raw_status = res.status
            detail = res.error
            classified_oos = res.status != "in_stock"
            if classified_oos and res.status not in {"out_of_stock"} and not (detail or "").strip():
                detail = "Không đọc được / không xác định được tồn → coi như hết hàng."

    else:
        # Chuẩn hoá và quy đổi sang https://hibox.mn/v/… (offer 1688 → abb-*; mirror Taobao/KZ → /v/…).
        normalized_in = normalize_product_import_url((url or "").strip())
        canonical_url = (normalized_in or (url or "").strip()).strip()

        hibox_url, coercion_err = coerce_url_for_excel_batch_import(canonical_url, FETCH_TARGET_HIBOX)
        warnings = []

        if coercion_err:
            classified_oos = True
            raw_status = "bad_url"
            detail = f"Không quy đổi được sang link Hibox hợp lệ: {coercion_err}"
            matched = []
            canonical_url = (hibox_url or canonical_url).strip()
        else:
            coerced = (hibox_url or "").strip()
            canonical_url = hibox_canonical_scrape_url(coerced) if coerced else canonical_url
            slug = extract_hibox_slug(canonical_url)
            matched = _find_products_for_hibox_slug(db, slug or "")
            try:
                _raw_row, product_data, warns = scrape_hibox_for_import(canonical_url)
                warnings = list(warns or [])
                title_like = (_raw_row or {}).get("title") if isinstance(_raw_row, dict) else None
                sku_like = (_raw_row or {}).get("sku") if isinstance(_raw_row, dict) else None
                pname = product_data.get("name") if isinstance(product_data, dict) else None
                has_signal = bool((title_like or "").strip() or (sku_like or "").strip() or (pname or "").strip())
                raw_status = "ok" if has_signal else "no_data"
                if not has_signal:
                    classified_oos = True
                    detail = (
                        "Hibox không trả đủ title/SKU sau khi scrape — coi như không lấy được (hết hoặc lỗi trang)."
                    )
                else:
                    classified_oos = False
                    if warns:
                        detail = "; ".join(warnings[:6])
            except ImportHiboxError as exc:
                classified_oos = True
                raw_status = "fetch_error"
                detail = str(exc)

    updated_ids: List[int] = []
    if classified_oos and matched:
        now = _utcnow()
        seen: set[int] = set()
        for p in matched:
            pid = int(p.id)
            if pid in seen:
                continue
            seen.add(pid)
            p.available = 0
            p.source_stock_status = "out_of_stock"
            p.source_stock_checked_at = now
            err_note = detail or ""
            if warnings:
                err_note = (err_note + " " if err_note else "") + "; ".join(warnings[:3])
            p.source_stock_error = (err_note or "").strip()[:2000] or None
            updated_ids.append(pid)
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.exception("admin source batch commit failed: %s", exc)
            raise
        try:
            for pid in updated_ids:
                logger.info(
                    "admin source batch marked OOS: product_id=%s domain=%s url=%s",
                    pid,
                    domain_lower,
                    canonical_url[:200],
                )
        except Exception:
            pass

    return {
        "ok": True,
        "canonical_url": canonical_url,
        "domain": domain_lower,
        "raw_status": raw_status,
        "classified_out_of_stock": classified_oos,
        "detail": detail,
        "warnings": warnings,
        "matched_products": [
            {
                "id": p.id,
                "name": p.name or "",
                "slug": p.slug or "",
                "product_id": p.product_id,
            }
            for p in matched
        ],
        "updated_product_ids": updated_ids,
        "matched_count": len(matched),
        "updates_committed": bool(updated_ids),
    }
