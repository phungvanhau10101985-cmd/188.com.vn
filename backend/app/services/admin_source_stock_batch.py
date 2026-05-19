"""
Kiểm tra tồn kho nguồn (admin batch): scrape **Hibox** hoặc API **CSSBuy** (quy đổi URL nguồn như nhập Excel).

Chỉ khi không đọc được PDP (thiếu tín hiệu SP / ``no_data``, lỗi fetch…) mới xếp hết và có thể
cập nhật ``available = 0``. Nếu vẫn thấy màu–size hay ma trận SKU → coi là đọc được offer,
không đánh ``out_of_stock`` chỉ vì tiêu đề trống hoặc giá tổng hợp = 0.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy import and_, case, exists, func, not_, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.guest_behavior import GuestProductView
from app.models.product import Product
from app.models.user import UserProductView
from app.services.import_batch_url_coercion import FETCH_TARGET_CSSBUY, FETCH_TARGET_HIBOX, coerce_url_for_excel_batch_import
from app.services.import_cssbuy_client import (
    ImportCssbuyError,
    cssbuy_html_disclaimer_agreement_without_add_to_cart,
    cssbuy_html_shows_add_to_cart_button,
    cssbuy_item_page_to_hibox_slug,
    fetch_cssbuy_item_json_bundle,
)
from app.services.import_hibox_scraper import (
    ImportHiboxError,
    extract_hibox_1688_offer_digits,
    extract_hibox_slug,
    hibox_canonical_scrape_url,
    hibox_scrape_signals_removed_or_not_found_offer,
    normalize_product_import_url,
    scrape_hibox_for_import,
)

logger = logging.getLogger(__name__)

# Lỗi tạm (chặn / captcha / lỗi đọc): không ghi admin_source_batch_scanned_at để SP được ưu tiên kiểm tra lại ngay.
_TRANSIENT_ADMIN_BATCH_RAW_STATUSES = frozenset({"error", "unknown", "fetch_error", "dual_fetch_error"})


def should_commit_admin_batch_ttl_after_scan(raw_status: str | None) -> bool:
    """False → không đánh dấu đã batch — giữ SP trong hàng chờ tức thì (sticky retry phía client)."""
    s = (raw_status or "").strip().lower()
    return s not in _TRANSIENT_ADMIN_BATCH_RAW_STATUSES


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _find_products_for_hibox_slug(db: Session, slug: str) -> List[Product]:
    """
    Khớp ``products`` với slug sau khi quy đổi Hibox (vd ``abb-823190872324``).

    Lưu ý: nhiều SP lưu ``link_default`` là URL 1688 ``…/offer/{id}.html`` — không chứa
    chuỗi ``/v/abb-…`` nên phải đối chiếu thêm offer id sau khi bóc từ slug.
    Khi chạy từ DB, ``anchor_product_db_id`` vẫn là khóa ghi kết quả chính xác cho
    đúng dòng được lấy từ queue.
    """
    s = (slug or "").strip()
    if not s or s == "hibox_import":
        return []
    prefixed = f"hibox_{s}"
    clauses: List[Any] = [
        Product.link_default.ilike(f"%hibox.mn%/v/{s}%"),
        Product.link_default.ilike(f"%/v/{s}%"),
        Product.link_default.ilike(f"%item?id={s}%"),
        Product.product_id.ilike(f"{prefixed}%"),
        Product.product_id == prefixed,
    ]
    oid = extract_hibox_1688_offer_digits(s)
    if oid:
        clauses.append(Product.link_default.ilike(f"%offer/{oid}%"))
        clauses.append(Product.link_default.ilike(f"%item-1688-{oid}%"))
    if s.isdigit():
        clauses.append(Product.link_default.ilike(f"%id={s}%"))

    return list(db.query(Product).filter(or_(*clauses)).all())


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
    """Bộ lọc link/active — chỉ SP có URL có thể đưa vào luồng quy đổi + scrape Hibox."""
    _ = (domain or "cssbuy").strip().lower()
    filters = [
        ProductModel.link_default.isnot(None),
        func.length(func.trim(ProductModel.link_default)) > 8,
    ]
    if active_only:
        filters.append(ProductModel.is_active.is_(True))

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
    domain_l = (domain or "cssbuy").strip().lower()
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
    domain_l = (domain or "cssbuy").strip().lower()
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


def _report_row_link_conversions(link_default: str | None) -> Dict[str, str]:
    """URL quy đổi giống nhập Excel / worker — hai cột CSSBuy & Hibox trên báo cáo."""
    raw = (link_default or "").strip()
    if not raw:
        miss = "thiếu link trong DB."
        return {
            "link_convert_cssbuy": "",
            "link_convert_cssbuy_err": miss,
            "link_convert_hibox": "",
            "link_convert_hibox_err": miss,
        }
    css_u, css_e = coerce_url_for_excel_batch_import(raw, FETCH_TARGET_CSSBUY)
    hb_u, hb_e = coerce_url_for_excel_batch_import(raw, FETCH_TARGET_HIBOX)
    return {
        "link_convert_cssbuy": (css_u or "").strip(),
        "link_convert_cssbuy_err": (css_e or "").strip(),
        "link_convert_hibox": (hb_u or "").strip(),
        "link_convert_hibox_err": (hb_e or "").strip(),
    }


def _paginate_slice(*, total: int, page: int, page_size: int) -> tuple[int, int]:
    """
    Clamp ``page`` theo tổng và trả ``(page_use, offset)`` cho OFFSET/LIMIT.

    ``page_size`` đã được clamp ở caller (1…500).
    """
    ps = max(1, int(page_size))
    t = max(0, int(total))
    if t <= 0:
        return (1, 0)
    tp = max(1, (t + ps - 1) // ps)
    p_req = max(1, int(page))
    p_use = min(p_req, tp)
    off = (p_use - 1) * ps
    return (p_use, off)


def admin_source_stock_activity_report(
    db: Session,
    *,
    domain: str,
    active_only: bool,
    window_days: int = 30,
    samples_oos_page: int = 1,
    samples_in_stock_page: int = 1,
    samples_batch_ttl_page: int = 1,
    sample_page_size: int = 200,
) -> Dict[str, Any]:
    """
    Báo cáo trong cửa sổ N ngày (rolling) trên cùng phạm vi link + is_active như hàng chờ admin.

    - ``batch_ttl_stamped_in_window``: đã có ``admin_source_batch_scanned_at`` trong cửa sổ
      (vòng batch ghi TTL — không gồm lỗi tạm không đánh dấu).
    - ``source_stock_checked_any_in_window``: đã có ``source_stock_checked_at`` trong cửa sổ
      (worker PDP, batch khi commit OOS, v.v.).
    - Phân rã ``source_stock_status`` chỉ trên các SP có ``source_stock_checked_at`` trong cửa sổ.

    - Mỗi dòng mẫu có thêm ``source_stock_check_platform`` khi PDP worker hoặc batch commit kết luận
      (cssbuy / hibox / ``cssbuy+hibox`` khi batch ghi nhận cả hai nền không đọc được).

    Mẫu trong ``samples``: sắp xếp **mới nhất trước** (``source_stock_checked_at`` hoặc ``admin_source_batch_scanned_at``
    giảm dần), phân trang độc lập mỗi nhóm qua ``samples_*_page`` và ``sample_page_size``.
    """
    domain_l = (domain or "cssbuy").strip().lower()
    wd = max(1, min(int(window_days), 366))
    since = _utcnow() - timedelta(days=wd)
    base = admin_product_source_link_base_filters(Product, domain_l, active_only=active_only)

    batch_ttl_stamped = int(
        db.query(func.count(Product.id))
        .filter(
            *base,
            Product.admin_source_batch_scanned_at.isnot(None),
            Product.admin_source_batch_scanned_at >= since,
        )
        .scalar()
        or 0
    )

    source_checked_any = int(
        db.query(func.count(Product.id))
        .filter(
            *base,
            Product.source_stock_checked_at.isnot(None),
            Product.source_stock_checked_at >= since,
        )
        .scalar()
        or 0
    )

    av_co = func.coalesce(Product.available, 0)
    checked_avail_pos = int(
        db.query(func.count(Product.id))
        .filter(
            *base,
            Product.source_stock_checked_at.isnot(None),
            Product.source_stock_checked_at >= since,
            av_co > 0,
        )
        .scalar()
        or 0
    )
    checked_avail_non_pos = int(
        db.query(func.count(Product.id))
        .filter(
            *base,
            Product.source_stock_checked_at.isnot(None),
            Product.source_stock_checked_at >= since,
            av_co <= 0,
        )
        .scalar()
        or 0
    )

    oos_signal = int(
        db.query(func.count(Product.id))
        .filter(
            *base,
            Product.source_stock_checked_at.isnot(None),
            Product.source_stock_checked_at >= since,
            Product.source_stock_status == "out_of_stock",
        )
        .scalar()
        or 0
    )

    in_stock_signal = int(
        db.query(func.count(Product.id))
        .filter(
            *base,
            Product.source_stock_checked_at.isnot(None),
            Product.source_stock_checked_at >= since,
            Product.source_stock_status == "in_stock",
        )
        .scalar()
        or 0
    )

    status_rows = (
        db.query(Product.source_stock_status, func.count(Product.id))
        .filter(
            *base,
            Product.source_stock_checked_at.isnot(None),
            Product.source_stock_checked_at >= since,
        )
        .group_by(Product.source_stock_status)
        .all()
    )
    checked_by_status: Dict[str, int] = {}
    for st, cnt in status_rows:
        k = (st or "").strip().lower() or "unknown"
        checked_by_status[k] = int(cnt or 0)

    queue = admin_source_stock_queue_stats(db, domain=domain_l, active_only=active_only)

    def iso_dt(dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None

    def row_dict(p: Product) -> Dict[str, Any]:
        return {
            "id": p.id,
            "product_id": p.product_id,
            "name": p.name,
            "slug": p.slug or "",
            "link_default": p.link_default or "",
            **_report_row_link_conversions(p.link_default),
            "source_stock_status": p.source_stock_status,
            "source_stock_checked_at": iso_dt(p.source_stock_checked_at),
            "admin_source_batch_scanned_at": iso_dt(p.admin_source_batch_scanned_at),
            "source_stock_check_platform": (p.source_stock_check_platform or "").strip() or None,
            "available": int(p.available or 0),
        }

    page_size_clamped = max(1, min(int(sample_page_size), 500))

    pg_oos_p, pg_off_oos = _paginate_slice(
        total=oos_signal, page=samples_oos_page, page_size=page_size_clamped
    )
    pg_ins_p, pg_off_ins = _paginate_slice(
        total=in_stock_signal, page=samples_in_stock_page, page_size=page_size_clamped
    )
    pg_bt_p, pg_off_bt = _paginate_slice(
        total=batch_ttl_stamped, page=samples_batch_ttl_page, page_size=page_size_clamped
    )

    samples: Dict[str, List[Dict[str, Any]]] = {"oos": [], "in_stock": [], "batch_ttl_recent": []}

    def tp_for(total_n: int, ps: int) -> int:
        return max(1, (total_n + ps - 1) // ps) if total_n > 0 else 1

    oos_rows = (
        db.query(Product)
        .filter(
            *base,
            Product.source_stock_checked_at.isnot(None),
            Product.source_stock_checked_at >= since,
            Product.source_stock_status == "out_of_stock",
        )
        .order_by(Product.source_stock_checked_at.desc(), Product.id.desc())
        .offset(pg_off_oos)
        .limit(page_size_clamped)
        .all()
    )
    samples["oos"] = [row_dict(p) for p in oos_rows]

    ins_rows = (
        db.query(Product)
        .filter(
            *base,
            Product.source_stock_checked_at.isnot(None),
            Product.source_stock_checked_at >= since,
            Product.source_stock_status == "in_stock",
        )
        .order_by(Product.source_stock_checked_at.desc(), Product.id.desc())
        .offset(pg_off_ins)
        .limit(page_size_clamped)
        .all()
    )
    samples["in_stock"] = [row_dict(p) for p in ins_rows]

    batch_rows = (
        db.query(Product)
        .filter(
            *base,
            Product.admin_source_batch_scanned_at.isnot(None),
            Product.admin_source_batch_scanned_at >= since,
        )
        .order_by(Product.admin_source_batch_scanned_at.desc(), Product.id.desc())
        .offset(pg_off_bt)
        .limit(page_size_clamped)
        .all()
    )
    samples["batch_ttl_recent"] = [row_dict(p) for p in batch_rows]

    samples_pagination = {
        "page_size": page_size_clamped,
        "oos": {
            "page": pg_oos_p,
            "total": int(oos_signal),
            "total_pages": tp_for(oos_signal, page_size_clamped),
        },
        "in_stock": {
            "page": pg_ins_p,
            "total": int(in_stock_signal),
            "total_pages": tp_for(in_stock_signal, page_size_clamped),
        },
        "batch_ttl_recent": {
            "page": pg_bt_p,
            "total": int(batch_ttl_stamped),
            "total_pages": tp_for(batch_ttl_stamped, page_size_clamped),
        },
    }

    return {
        "ok": True,
        "domain": domain_l,
        "active_only": bool(active_only),
        "window_days": wd,
        "window_since_utc_iso": since.isoformat(),
        "samples_pagination": samples_pagination,
        "queue": queue,
        "counts": {
            "batch_ttl_stamped_in_window": batch_ttl_stamped,
            "source_stock_checked_any_in_window": source_checked_any,
            "source_stock_oos_signal_in_window": oos_signal,
            "source_stock_in_stock_signal_in_window": in_stock_signal,
            "checked_available_positive_in_window": checked_avail_pos,
            "checked_available_zero_or_negative_in_window": checked_avail_non_pos,
        },
        "checked_in_window_by_source_stock_status": checked_by_status,
        "samples": samples,
    }


def admin_collect_distinct_product_urls_from_db(
    db: Session,
    *,
    domain: str,
    limit: int,
    active_only: bool,
) -> Dict[str, Any]:
    domain_l = (domain or "cssbuy").strip().lower()
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
    sticky_seed_product_id: int = 0,
    skip_sticky_after_failure: bool = False,
    dual_alternate_fallback: bool = False,
    alternate_sequence_index: int = 0,
) -> Dict[str, Any]:
    """
    Chọn một SP thỏa bộ lọc miền + TTL hàng chờ (SP có PDP traffic được xử lý theo cửa sổ lượt xem và khoảng đợi riêng).
    Thứ tự ưu tiên server:
      1) SP có ít nhất một lượt xem PDP (user hoặc guest session) trong cửa sổ ``ADMIN_SOURCE_BATCH_TRAFFIC_VIEW_WINDOW_DAYS``.
      2) Chưa từng đánh batch hay mốt ``admin_source_batch_scanned_at`` cũ hơn.
      3) Tie-break ``products.id`` tăng dần.

    Kết quả scrape **hết nguồn**: ngoài sản khớp slug trong DB (nếu có), cờ được ghi **ảnh hưởng** lên
    đúng ``products.id`` của SP được chọn trong hàng chờ (neo), để báo cáo / «Xóa khỏi DB» đứng với một bản ghi cụ thể.

    ``sticky_seed_product_id`` (``products.id``): nếu còn thỏa bộ lọc, ưu tiên kiểm tra lại đúng SP đó (retry captcha/chặn…).
    Biến ``cursor_after_product_id`` giữ chỉ cho tương thích API; không lái queue.
    """
    _ = cursor_after_product_id

    domain_l = (domain or "cssbuy").strip().lower()
    filt, vu = _ttl_ready_filters(Product, domain_l, active_only=active_only)

    prod = None
    sid = max(0, int(sticky_seed_product_id or 0))
    if sid > 0:
        prod = db.query(Product).filter(Product.id == sid, *filt).first()

    if prod is None:
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
    scan = dict(
        run_admin_source_url_scan(
            db,
            url=seed_link_default,
            domain=domain_l,
            dual_alternate_fallback=bool(dual_alternate_fallback),
            alternate_sequence_index=int(alternate_sequence_index),
            anchor_product_db_id=int(prod.id),
        )
    )
    raw_status_l = str(scan.get("raw_status") or "").strip().lower()
    skip_after_retry = bool(skip_sticky_after_failure and sid > 0 and int(prod.id) == sid and raw_status_l in _TRANSIENT_ADMIN_BATCH_RAW_STATUSES)
    marked_at: datetime | None = None
    if should_commit_admin_batch_ttl_after_scan(scan.get("raw_status")) or skip_after_retry:
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
            "skipped_after_retry": skip_after_retry,
        }
    )
    return scan


def _alternate_primary_platform(sequence_index: int) -> str:
    return "cssbuy" if int(sequence_index) % 2 == 0 else "hibox"


def _other_source_platform(platform: str) -> str:
    pl = (platform or "").strip().lower()
    return "cssbuy" if pl == "hibox" else "hibox"


def _json_list_nonempty_for_catalog(raw_json: Any) -> bool:
    """Mảng JSON từ scraper: tên màu, size, hoặc cặp color×size."""
    if raw_json is None:
        return False
    try:
        data = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(data, list) or len(data) == 0:
        return False
    for x in data[:200]:
        if x is None:
            continue
        if isinstance(x, str) and x.strip():
            return True
        if isinstance(x, dict) and (
            str(x.get("color") or "").strip() or str(x.get("size") or "").strip()
        ):
            return True
    return False


def _hibox_row_shows_color_size_catalog(raw_row: Dict[str, Any], product_data: Dict[str, Any]) -> bool:
    """
    PDP vẫn có thông tin SKU (màu/size/variant) → coi là đọc được offer, không gán hết
    chỉ vì thiếu tiêu đề/SKU dạng chữ.
    """
    if str(raw_row.get("h1") or "").strip():
        return True
    if _json_list_nonempty_for_catalog(raw_row.get("variant_color_size_json")):
        return True
    if _json_list_nonempty_for_catalog(raw_row.get("colors_json")):
        return True
    if _json_list_nonempty_for_catalog(raw_row.get("sizes_json")):
        return True
    try:
        if int(raw_row.get("color_variant_image_count") or 0) > 0:
            return True
    except (TypeError, ValueError):
        pass

    sizes = product_data.get("sizes")
    if isinstance(sizes, list) and any(str(s).strip() for s in sizes if s is not None):
        return True

    colors = product_data.get("colors")
    if isinstance(colors, list):
        for c in colors[:120]:
            if isinstance(c, dict) and str(c.get("name") or "").strip():
                return True
            if not isinstance(c, dict) and str(c).strip():
                return True

    pi = product_data.get("product_info")
    variants_blob = pi.get("variants") if isinstance(pi, dict) else None
    if isinstance(variants_blob, dict):
        pairs = variants_blob.get("pairs")
        if isinstance(pairs, list):
            for it in pairs[:160]:
                if isinstance(it, dict) and (
                    str(it.get("color") or "").strip() or str(it.get("size") or "").strip()
                ):
                    return True

    return False


def _cssbuy_row_shows_variant_matrix(row0: Dict[str, Any]) -> bool:
    """
    Trong payload /web/item thường có skumap / danh sách thuộc tính — nếu còn matrix SKU,
    không coi là hết chỉ vì giá summary = 0.
    """

    def walk(o: Any, depth: int, seen: List[int]) -> bool:
        if depth > 12 or seen[0] > 380:
            return False
        seen[0] += 1
        if isinstance(o, dict):
            for k, v in o.items():
                kl = str(k).lower()
                kln = kl.replace("_", "").replace("-", "")
                is_sku_blob = ("skumap" in kln) or ("sku" in kln and ("prop" in kln or "spec" in kln))
                if is_sku_blob and v:
                    if isinstance(v, dict) and len(v) >= 2:
                        return True
                    if isinstance(v, list) and len(v) >= 2:
                        return True
                if walk(v, depth + 1, seen):
                    return True
        elif isinstance(o, list):
            if (
                len(o) >= 3
                and o
                and all(isinstance(x, dict) for x in o[: min(8, len(o))])
            ):
                hit = 0
                keys_union: set[str] = set()
                for x in o[:20]:
                    if not isinstance(x, dict):
                        continue
                    keys_union.update(str(k).lower() for k in x.keys())
                    if any(str(x.get(nk) or "").strip() for nk in ("name", "value", "text", "propertyname", "prop")):
                        hit += 1
                dense = {"pid", "vid", "value", "prop", "properties"}.intersection(keys_union)
                if hit >= 3 or ("pid" in keys_union and len(o) >= 3) or dense:
                    return True
            for x in o[:48]:
                if walk(x, depth + 1, seen):
                    return True
        return False

    return walk(row0, 0, [0])


def _attempt_has_usable_catalog_read(scan: Dict[str, Any]) -> bool:
    if scan.get("classified_out_of_stock") is True:
        return True
    rs = (scan.get("raw_status") or "").strip().lower()
    return rs == "ok"


def _gather_platform_scan_attempt(db: Session, *, seed_url: str, platform: str) -> Dict[str, Any]:
    plat = (platform or "").strip().lower()
    if plat not in ("hibox", "cssbuy"):
        plat = "cssbuy"

    classified_oos = False
    raw_status: str | None = None
    detail: str | None = None
    warnings: List[str] = []
    matched: List[Product] = []

    normalized_in = normalize_product_import_url((seed_url or "").strip())
    canonical_url = (normalized_in or (seed_url or "").strip()).strip()

    if plat == "hibox":
        hibox_url, coercion_err = coerce_url_for_excel_batch_import(canonical_url, FETCH_TARGET_HIBOX)
        warnings = []

        if coercion_err:
            classified_oos = False
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
                rr = dict(_raw_row) if isinstance(_raw_row, dict) else {}
                pd = dict(product_data) if isinstance(product_data, dict) else {}
                if hibox_scrape_signals_removed_or_not_found_offer(rr):
                    raw_status = "no_data"
                    classified_oos = True
                    detail = (
                        "Hibox: trang báo không tìm thấy/đã xóa offer (Taobao…) — coi như không còn hàng nguồn."
                    )
                else:
                    title_like = rr.get("title")
                    sku_like = rr.get("sku")
                    pname = pd.get("name")
                    basics = bool((title_like or "").strip() or (sku_like or "").strip() or (pname or "").strip())
                    has_signal = basics or _hibox_row_shows_color_size_catalog(rr, pd)
                    cart_ok = rr.get("hibox_dom_cart_cta")
                    if cart_ok is False:
                        raw_status = "no_data"
                        classified_oos = True
                        detail = (
                            "Hibox: PDP không có nút «САГСЛАХ» (thêm giỏ — khoanh đỏ) — coi hết hàng nguồn."
                        )
                    elif has_signal:
                        raw_status = "ok"
                        classified_oos = False
                        if warnings:
                            detail = "; ".join(warnings[:6])
                    else:
                        raw_status = "no_data"
                        classified_oos = True
                        detail = (
                            "Hibox không trả đủ dữ liệu đọc SP (thiếu tiêu đề/SKU và không thấy màu–size hay variant có nội dung) — có thể hết hoặc lỗi trang."
                        )
            except ImportHiboxError as exc:
                classified_oos = False
                raw_status = "fetch_error"
                detail = str(exc)
            except Exception as exc:
                logger.exception("admin source batch hibox scrape failed url=%s", canonical_url[:200])
                classified_oos = False
                raw_status = "fetch_error"
                detail = (
                    ((str(exc) or "unexpected_error")[:920] + " — chưa kiểm tra được, không đổi tồn.")[:1000]
                )
    else:
        cssbuy_page, coercion_err = coerce_url_for_excel_batch_import(canonical_url, FETCH_TARGET_CSSBUY)
        warnings = []

        if coercion_err:
            classified_oos = False
            raw_status = "bad_url"
            detail = f"Không quy đổi được sang URL CSSBuy hợp lệ: {coercion_err}"
            matched = []
            canonical_url = (cssbuy_page or canonical_url).strip()
        else:
            canonical_url = (cssbuy_page or "").strip() or canonical_url
            slug = cssbuy_item_page_to_hibox_slug(canonical_url)
            matched = _find_products_for_hibox_slug(db, slug or "")
            try:
                payload, css_page_html = fetch_cssbuy_item_json_bundle(canonical_url)
                code = payload.get("code")
                if code != 0:
                    classified_oos = True
                    raw_status = "no_data"
                    detail = (
                        "CSSBuy /web/item code≠0 hoặc từ chối — coi không còn offer/hết dữ liệu item: "
                        + str(payload.get("message") or payload.get("msg") or f"code={code}")[:820]
                    )[:1000]
                else:
                    rows = payload.get("data")
                    row0 = rows[0] if isinstance(rows, list) and rows else None
                    if not isinstance(row0, dict):
                        classified_oos = True
                        raw_status = "no_data"
                        detail = (
                            "CSSBuy trả payload không có data hàng đầu hợp lệ như PDP không load — coi không còn offer."
                        )
                    else:
                        try:
                            price = float(row0.get("price") or 0)
                        except (TypeError, ValueError):
                            price = 0.0
                        title = (row0.get("title") or row0.get("title_cn") or "").strip()
                        variant_matrix = _cssbuy_row_shows_variant_matrix(row0)
                        has_signal = bool(title) and (price > 0 or variant_matrix)
                        css_html = (css_page_html or "").strip()
                        disclaimer_no_cart = cssbuy_html_disclaimer_agreement_without_add_to_cart(css_html)
                        show_cart = cssbuy_html_shows_add_to_cart_button(css_html)
                        if disclaimer_no_cart:
                            classified_oos = True
                            raw_status = "no_data"
                            detail = (
                                "CSSBuy: có checkbox disclaimer («I have read… terms of service…») nhưng không thấy "
                                "«Add To Cart» — PDP hết hàng / không còn bán được."
                            )
                        elif has_signal and not show_cart:
                            classified_oos = True
                            raw_status = "no_data"
                            detail = (
                                "CSSBuy: API có dữ liệu nhưng PDP không có nút «Add To Cart» "
                                "(khoanh đỏ kiểm tra còn bán)."
                            )
                        elif not has_signal:
                            raw_status = "no_data"
                            classified_oos = True
                            detail = (
                                "CSSBuy: thiếu tiêu đề hoặc không có (giá > 0 / ma trận SKU thuộc tính) — không khẳng định được offer còn."
                            )
                        else:
                            raw_status = "ok"
                            classified_oos = False
                            detail = None
            except ImportCssbuyError as exc:
                classified_oos = True
                raw_status = "no_data"
                detail = f"CSSBuy không lấy được item (dead/skeleton không tải): {exc}"[:1000]
            except Exception as exc:
                logger.exception("admin source batch cssbuy failed url=%s", canonical_url[:200])
                classified_oos = False
                raw_status = "fetch_error"
                detail = (
                    ((str(exc) or "unexpected_error")[:920] + " — chưa kiểm tra được, không đổi tồn.")[:1000]
                )

    return {
        "canonical_url": canonical_url,
        "domain": plat,
        "raw_status": raw_status,
        "classified_out_of_stock": classified_oos,
        "detail": detail,
        "warnings": warnings,
        "matched_orm": matched,
    }


def _finalize_scan_commit_and_serialise(
    db: Session,
    *,
    computed: Dict[str, Any],
    extras: Dict[str, Any] | None = None,
    anchor_product_db_id: int | None = None,
) -> Dict[str, Any]:
    canonical_url = str(computed.get("canonical_url") or "").strip()
    domain_used = str(computed.get("domain") or "").strip().lower()
    raw_status = computed.get("raw_status")
    detail = computed.get("detail")
    warnings = list(computed.get("warnings") or [])
    classified_oos = bool(computed.get("classified_out_of_stock"))
    matched: List[Product] = list(computed.get("matched_orm") or [])

    anch = max(0, int(anchor_product_db_id or 0))
    anchor_added = False
    if anch > 0:
        ids_present = {int(p.id) for p in matched}
        if anch not in ids_present:
            anchor_row = db.query(Product).filter(Product.id == anch).first()
            if anchor_row is not None:
                matched = [anchor_row] + matched
                anchor_added = True

    updated_ids: List[int] = []
    scan_status = "out_of_stock" if classified_oos else ("in_stock" if str(raw_status or "").strip().lower() == "ok" else "error")
    plat = domain_used.strip()[:80] if domain_used.strip() else None
    if matched:
        now = _utcnow()
        seen: set[int] = set()
        for p in matched:
            pid = int(p.id)
            if pid in seen:
                continue
            seen.add(pid)
            previous_status = (p.source_stock_status or "").strip().lower()
            if classified_oos:
                p.available = 0
            elif scan_status == "in_stock" and int(p.available or 0) <= 0 and previous_status == "out_of_stock":
                p.available = 500
            p.source_stock_status = scan_status
            p.source_stock_checked_at = now
            p.source_stock_check_platform = plat
            err_note = (detail or "") if isinstance(detail, str) else ""
            if warnings:
                err_note = (err_note + " " if err_note else "") + "; ".join(warnings[:3])
            p.source_stock_error = ((err_note or "").strip()[:2000] or None) if scan_status != "in_stock" else None
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
                    "admin source batch stamped source stock: product_id=%s status=%s domain=%s url=%s",
                    pid,
                    scan_status,
                    domain_used,
                    canonical_url[:200],
                )
        except Exception:
            pass

    out: Dict[str, Any] = {
        "ok": True,
        "canonical_url": canonical_url,
        "domain": domain_used,
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
    if extras:
        out.update(extras)
    if anchor_added:
        out["anchor_included_db_id"] = anch
        if classified_oos:
            out["oos_commit_included_anchor_db_id"] = anch
    return out


def run_admin_source_url_scan(
    db: Session,
    *,
    url: str,
    domain: str,
    dual_alternate_fallback: bool = False,
    alternate_sequence_index: int = 0,
    anchor_product_db_id: int = 0,
) -> Dict[str, Any]:
    domain_lower = (domain or "").strip().lower()
    if domain_lower == "1688":
        return {
            "ok": False,
            "canonical_url": (url or "").strip(),
            "domain": domain_lower,
            "raw_status": "bad_domain",
            "classified_out_of_stock": False,
            "detail": "Đã ngừng kiểm tra trực tiếp 1688 — dùng domain=hibox hoặc cssbuy.",
            "matched_products": [],
            "updated_product_ids": [],
            "matched_count": 0,
        }

    if not dual_alternate_fallback:
        if domain_lower in ("", "cssbuy"):
            domain_lower = "cssbuy"
        elif domain_lower == "hibox":
            pass
        else:
            return {
                "ok": False,
                "canonical_url": (url or "").strip(),
                "domain": domain_lower,
                "raw_status": "bad_domain",
                "classified_out_of_stock": False,
                "detail": "domain phải là «hibox» hoặc «cssbuy».",
                "matched_products": [],
                "updated_product_ids": [],
                "matched_count": 0,
            }
        gathered = _gather_platform_scan_attempt(db, seed_url=url, platform=domain_lower)
        return _finalize_scan_commit_and_serialise(
            db,
            computed=gathered,
            extras=None,
            anchor_product_db_id=anchor_product_db_id or None,
        )

    primary = _alternate_primary_platform(alternate_sequence_index)
    secondary = _other_source_platform(primary)
    first = _gather_platform_scan_attempt(db, seed_url=url, platform=primary)

    extras_common: Dict[str, Any] = {
        "alternate_sequence_index": int(alternate_sequence_index),
        "alternate_primary_domain": primary,
    }

    if _attempt_has_usable_catalog_read(first):
        return _finalize_scan_commit_and_serialise(
            db,
            computed=first,
            extras=dict(extras_common),
            anchor_product_db_id=anchor_product_db_id or None,
        )

    second = _gather_platform_scan_attempt(db, seed_url=url, platform=secondary)
    if _attempt_has_usable_catalog_read(second):
        merged_extras = dict(extras_common)
        merged_extras.update(
            {
                "alternate_fallback_used": True,
                "alternate_failed_domain": primary,
            }
        )
        return _finalize_scan_commit_and_serialise(
            db,
            computed=second,
            extras=merged_extras,
            anchor_product_db_id=anchor_product_db_id or None,
        )

    from app.services.vipomall_source_stock import vipomall_gather_admin_batch_scan

    fb_pid = None
    anch = max(0, int(anchor_product_db_id or 0))
    if anch > 0:
        anchor_row = db.query(Product).filter(Product.id == anch).first()
        if anchor_row is not None:
            fb_pid = anchor_row.product_id
    third = vipomall_gather_admin_batch_scan(db, seed_url=url, fallback_product_id=fb_pid)
    if _attempt_has_usable_catalog_read(third):
        merged_extras = dict(extras_common)
        merged_extras.update(
            {
                "vipomall_fallback_used": True,
                "alternate_fallback_used": True,
                "alternate_failed_domain": primary,
                "cssbuy_and_hibox_inconclusive": True,
            }
        )
        return _finalize_scan_commit_and_serialise(
            db,
            computed=third,
            extras=merged_extras,
            anchor_product_db_id=anchor_product_db_id or None,
        )

    det_a_raw = first.get("detail")
    det_b_raw = second.get("detail")
    det_a = (det_a_raw if isinstance(det_a_raw, str) else "") or ""
    det_b = (det_b_raw if isinstance(det_b_raw, str) else "") or ""
    det_a = det_a.strip()
    det_b = det_b.strip()
    rs_a = str(first.get("raw_status") or "—").strip()
    rs_b = str(second.get("raw_status") or "—").strip()
    if not det_a:
        det_a = "(không có chi tiết)"
    if not det_b:
        det_b = "(không có chi tiết)"
    canon = (str(second.get("canonical_url") or first.get("canonical_url") or "") or "").strip()
    det_c_raw = third.get("detail")
    det_c = (det_c_raw if isinstance(det_c_raw, str) else "") or ""
    det_c = det_c.strip() or "(không có chi tiết)"
    rs_c = str(third.get("raw_status") or "—").strip()
    mega_detail = (
        "CSSBuy, Hibox và Vipomall (1688) đều không đưa ra kết luận in_stock/out_of_stock rõ — "
        "đã ghi trạng thái lỗi kiểm tra; nên xử lý chặn/captcha hoặc thiếu offerId 1688.\n\n"
        f"[{primary.upper()}] raw_status={rs_a}\n{det_a}\n\n"
        f"[{secondary.upper()}] raw_status={rs_b}\n{det_b}\n\n"
        f"[VIPOMALL] raw_status={rs_c}\n{det_c}"
    )
    attempts = [
        {"domain": primary, "raw_status": first.get("raw_status"), "detail": first.get("detail")},
        {"domain": secondary, "raw_status": second.get("raw_status"), "detail": second.get("detail")},
        {"domain": "vipomall", "raw_status": third.get("raw_status"), "detail": third.get("detail")},
    ]
    merged_warns = list(
        (first.get("warnings") or [])
        + (second.get("warnings") or [])
        + (third.get("warnings") or [])
    )[:40]
    return _finalize_scan_commit_and_serialise(
        db,
        computed={
            "canonical_url": canon,
            "domain": f"{primary}+{secondary}",
            "raw_status": "dual_fetch_error",
            "classified_out_of_stock": False,
            "detail": mega_detail,
            "warnings": merged_warns,
            "matched_orm": [],
        },
        extras={
            "dual_platform_both_failed": True,
            "dual_attempts": attempts,
            "alternate_sequence_index": int(alternate_sequence_index),
            "alternate_primary_domain": primary,
        },
        anchor_product_db_id=anchor_product_db_id or None,
    )

def admin_clear_false_source_oos_flag(db: Session, *, db_id: int) -> Dict[str, Any]:
    """
    Gỡ cờ sai: đặt lại ``source_stock_status`` (không còn out_of_stock), xóa mốc ``source_stock_checked_at``,
    phục hồi tồn mặc định nghiệp vụ khi đang là 0.
    """
    pk = max(1, int(db_id))
    row = db.query(Product).filter(Product.id == pk).first()
    if not row:
        return {"ok": False, "detail": "product_not_found", "product_db_id": pk}
    try:
        row.source_stock_status = "unknown"
        row.source_stock_error = None
        row.source_stock_checked_at = None
        row.source_stock_next_check_at = None
        row.source_stock_check_platform = None
        if int(row.available or 0) <= 0:
            row.available = 500
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("clear_false_oos_flag failed id=%s: %s", pk, exc)
        return {"ok": False, "detail": "database_error", "product_db_id": pk}

    refreshed = db.query(Product).filter(Product.id == pk).first()

    checked_iso = None
    if refreshed and refreshed.source_stock_checked_at:
        checked_iso = refreshed.source_stock_checked_at.isoformat()

    return {
        "ok": True,
        "product_db_id": pk,
        "source_stock_status": refreshed.source_stock_status if refreshed else "unknown",
        "available": int(refreshed.available or 0) if refreshed else 0,
        "source_stock_checked_at": checked_iso,
    }


def admin_reset_source_stock_pdp_cycle(
    db: Session,
    *,
    domain: str,
    active_only: bool,
) -> Dict[str, Any]:
    """
    Xóa kết quả/lịch kiểm tra nguồn PDP (``source_stock_*``) trên các sản trong cùng phạm vi link như queue-stats;
    bỏ qua các dòng đang ``queued`` hoặc ``checking``;
    đồng thời xóa deque hàng chờ in-memory của **process backend đang nhận request** (không phải máy chủ khác).

    Không đụng ``available`` và không reset TTL batch admin (``admin_source_batch_scanned_at``).
    """
    from app.services import source_stock_checker as source_stock_checker_mod

    mem = source_stock_checker_mod.clear_source_stock_in_memory_queue()

    domain_l = (domain or "cssbuy").strip().lower()
    base_filters = admin_product_source_link_base_filters(Product, domain_l, active_only=active_only)

    stmt = (
        update(Product)
        .where(and_(*base_filters))
        .where(or_(Product.source_stock_status.is_(None), ~Product.source_stock_status.in_(["queued", "checking"])))
        .values(
            source_stock_next_check_at=None,
            source_stock_checked_at=None,
            source_stock_status="unknown",
            source_stock_error=None,
            source_stock_check_platform=None,
        )
    )
    res = db.execute(stmt)
    db.commit()

    rc = getattr(res, "rowcount", None)
    updated = int(rc) if isinstance(rc, int) and rc >= 0 else 0

    return {
        "ok": True,
        "domain": domain_l,
        "active_only": bool(active_only),
        "products_updated": updated,
        "memory_queue_cleared": int(mem.get("cleared_count", 0) or 0),
        "detail": (
            "Đã reset source_stock («unknown», xóa mốc) cho SP trong phạm vi; "
            "bỏ qua queued/checking. Queue RAM chỉ của process nhận request được xóa."
        ),
    }


def admin_force_worker_source_stock_recheck(db: Session, *, db_id: int) -> Dict[str, Any]:
    """
    Ép PDP worker (queue in-process): ``enqueue_source_stock_check(..., force=True)``.
    """
    # Local import để tránh khởi tạo nặng nếu module không đụng vào báo cáo.
    from app.services.source_stock_checker import enqueue_source_stock_check

    pk = max(1, int(db_id))
    row = db.query(Product).filter(Product.id == pk).first()
    if not row:
        return {"ok": False, "detail": "product_not_found", "product_db_id": pk}

    ok_enqueue = enqueue_source_stock_check(pk, reason="admin_report_recheck", force=True)

    db.expire_all()
    row2 = db.query(Product).filter(Product.id == pk).first()
    if not row2:
        return {"ok": False, "detail": "product_not_found", "product_db_id": pk}

    st_l = (row2.source_stock_status or "").strip().lower()
    if ok_enqueue:
        skip_reason = None
    elif st_l in {"queued", "checking"}:
        skip_reason = "already_pending"
    else:
        skip_reason = "not_eligible_or_failed"

    next_iso = row2.source_stock_next_check_at.isoformat() if row2.source_stock_next_check_at else None

    return {
        "ok": True,
        "product_db_id": pk,
        "enqueued_now": bool(ok_enqueue),
        "skip_reason": skip_reason,
        "source_stock_status": row2.source_stock_status,
        "source_stock_next_check_at": next_iso,
    }
