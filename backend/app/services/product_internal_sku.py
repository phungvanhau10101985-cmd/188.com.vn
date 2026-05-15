"""SKU hiển thị web: đúng 1 chữ Latin in hoa + 4 chữ số (vd K0842).

Khi sinh hoặc chấp nhận mã, tránh trùng:
- `products.code` (SP đã đăng),
- nháp import (`product_import_drafts.product_data`),
- pool file SKU đã xuất (TTL `INTERNAL_SKU_EXPORT_RESERVE_DAYS`),
- các ô trên Google Sheet SKU (khi bật đồng bộ — đọc có cache ngắn),
và không trùng trong một lô import (`batch_reserved`).
"""
from __future__ import annotations

import copy
import json
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Set

from sqlalchemy.orm import Session

from app.models.internal_sku_export import InternalSkuExport
from app.models.product import Product
from app.models.product_import_draft import ProductImportDraft

INTERNAL_SKU_RE = re.compile(r"^[A-Z][0-9]{4}$")
_LETTERS = string.ascii_uppercase
INTERNAL_SKU_SPACE_TOTAL = len(_LETTERS) * 10_000
# Không phát hành / không tự sinh mã dạng A0000…Z0000 (dễ nhầm, trùng cảm giác “mã rỗng”).
_INTERNAL_SKU_DISALLOWED_ZERO_SUFFIX = {f"{ch}0000" for ch in _LETTERS}
INTERNAL_SKU_ASSIGNABLE_TOTAL = INTERNAL_SKU_SPACE_TOTAL - len(_INTERNAL_SKU_DISALLOWED_ZERO_SUFFIX)
_MAX_RANDOM_TRIES = 50_000
# Phiên đặt chỗ (reserve) sau khi tải file SKU trống: không trùng lần xuất kế trong khoảng thời gian này;
# sau thời điểm này bản ghi export cũ được xử lý như không còn và có thể xuất/trùng tương tác import như không dùng file.
INTERNAL_SKU_EXPORT_RESERVE_DAYS = 7


def _internal_sku_export_cutoff_utc() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=INTERNAL_SKU_EXPORT_RESERVE_DAYS)


def _purge_internal_sku_exports_expired(db: Session) -> None:
    """Xóa bản ghi export quá hạn (không giữ TTL khi chỉ đọc GET): gọi từ lúc có ghi/export mới."""
    cutoff = _internal_sku_export_cutoff_utc()
    db.query(InternalSkuExport).filter(InternalSkuExport.exported_at < cutoff).delete(
        synchronize_session=False
    )


def _is_disallowed_internal_sku_create(code: str) -> bool:
    """True nếu mã khớp [A-Z][0-9]{4} nhưng là placeholder «…0000» (A0000–Z0000)."""
    c = (code or "").strip().upper()
    return c in _INTERNAL_SKU_DISALLOWED_ZERO_SUFFIX


def internal_sku_is_valid_format(code: Optional[str]) -> bool:
    """Đúng 1 chữ Latin hoa + 4 chữ số và không phải dạng *0000 (vd A0001 hợp lệ, A0000 không)."""
    c = (code or "").strip().upper()
    return bool(INTERNAL_SKU_RE.fullmatch(c)) and not _is_disallowed_internal_sku_create(c)


def internal_sku_exists_on_other_product(
    db: Session,
    code: Optional[str],
    *,
    exclude_product_id: Optional[int] = None,
) -> bool:
    """True nếu products.code đã có SP khác dùng mã này."""
    c = (code or "").strip().upper()
    if not c:
        return False
    return _internal_sku_taken_by_other_product(db, c, exclude_product_id)


def _code_reserved_by_export(db: Session, code: str) -> bool:
    c = (code or "").strip().upper()
    if not c:
        return False
    cutoff = _internal_sku_export_cutoff_utc()
    return (
        db.query(InternalSkuExport.id)
        .filter(InternalSkuExport.code == c, InternalSkuExport.exported_at >= cutoff)
        .first()
        is not None
    )


def _internal_sku_taken_by_other_product(db: Session, code: str, exclude_product_id: Optional[int]) -> bool:
    """Sản phẩm khác đã dùng mã này (không tính bản ghi đang cập nhật)."""
    c = (code or "").strip().upper()
    q = db.query(Product.id).filter(Product.code == c)
    if exclude_product_id is not None:
        q = q.filter(Product.id != exclude_product_id)
    return q.first() is not None


def _customer_sheet_internal_skus_cached() -> Set[str]:
    """Mã [A-Z][0-9]{4} đang có trên Google Sheet SKU (cache ~60s trong lớp sheet)."""
    try:
        from app.services.google_sheets_sku_sync import fetch_internal_sku_keys_from_sheet_cached

        return fetch_internal_sku_keys_from_sheet_cached()
    except Exception:
        return set()


def _extract_internal_skus_from_product_data(pd: Any) -> Set[str]:
    """Đọc mã nội bộ từ JSON nháp: `code` và product_info.product_info.sku."""
    out: Set[str] = set()
    if pd is None:
        return out
    if isinstance(pd, str):
        s = pd.strip()
        if not s:
            return out
        try:
            pd = json.loads(s)
        except json.JSONDecodeError:
            return out
    if not isinstance(pd, dict):
        return out
    raw_top = pd.get("code")
    if raw_top is not None:
        c = str(raw_top).strip().upper()
        if internal_sku_is_valid_format(c):
            out.add(c)
    pi = pd.get("product_info")
    if isinstance(pi, str):
        try:
            pi = json.loads(pi)
        except json.JSONDecodeError:
            pi = None
    if isinstance(pi, dict):
        inner = pi.get("product_info")
        if isinstance(inner, dict):
            sku = inner.get("sku")
            if sku is not None:
                c = str(sku).strip().upper()
                if internal_sku_is_valid_format(c):
                    out.add(c)
    return out


def internal_sku_codes_in_import_drafts(db: Session, exclude_draft_id: Optional[int] = None) -> Set[str]:
    """Tất cả mã SKU nội bộ đang ghi trong nháp import (trừ một draft khi đang gán lại cho chính nháp đó)."""
    q = db.query(ProductImportDraft.product_data).filter(ProductImportDraft.product_data.isnot(None))
    if exclude_draft_id is not None:
        q = q.filter(ProductImportDraft.id != exclude_draft_id)
    acc: Set[str] = set()
    for (blob,) in q.all():
        acc.update(_extract_internal_skus_from_product_data(blob))
    return acc


def internal_sku_conflicts_global_inventory(
    db: Session,
    code: Optional[str],
    *,
    exclude_product_id: Optional[int] = None,
    exclude_draft_id: Optional[int] = None,
) -> bool:
    """
    True nếu mã đúng định dạng và đã có trên SP khác, trong nháp import khác,
    hoặc trên sheet SKU khách (ô khớp [A-Z][0-9]{4}).
    """
    if not internal_sku_is_valid_format(code):
        return False
    c = str(code).strip().upper()
    if _internal_sku_taken_by_other_product(db, c, exclude_product_id):
        return True
    if c in internal_sku_codes_in_import_drafts(db, exclude_draft_id):
        return True
    if c in _customer_sheet_internal_skus_cached():
        return True
    return False


def _blocked_for_auto_assign_internal_sku(
    db: Session,
    code: str,
    exclude_product_id: Optional[int],
    *,
    exclude_draft_id: Optional[int] = None,
    draft_codes: Optional[Set[str]] = None,
    sheet_codes: Optional[Set[str]] = None,
) -> bool:
    """Sinh tự động / xuất file: tránh export TTL, SP, nháp và sheet."""
    c = (code or "").strip().upper()
    if _code_reserved_by_export(db, c):
        return True
    if _internal_sku_taken_by_other_product(db, c, exclude_product_id):
        return True
    dc = draft_codes if draft_codes is not None else internal_sku_codes_in_import_drafts(db, exclude_draft_id)
    if c in dc:
        return True
    sc = sheet_codes if sheet_codes is not None else _customer_sheet_internal_skus_cached()
    return c in sc


def internal_sku_codes_in_use(db: Session) -> Set[str]:
    """Mã định dạng nội bộ đang gán cho ít nhất một sản phẩm."""
    out: Set[str] = set()
    for (raw,) in db.query(Product.code).filter(Product.code.isnot(None)).all():
        if not raw:
            continue
        u = str(raw).strip().upper()
        if INTERNAL_SKU_RE.fullmatch(u):
            out.add(u)
    return out


def internal_sku_codes_exported(db: Session) -> Set[str]:
    """Mã đang trong thời hạn đặt chỗ (reserve) sau lần xuất file gần nhất (INTERNAL_SKU_EXPORT_RESERVE_DAYS)."""
    cutoff = _internal_sku_export_cutoff_utc()
    return {
        str(r[0]).strip().upper()
        for r in db.query(InternalSkuExport.code)
        .filter(InternalSkuExport.exported_at >= cutoff)
        .all()
        if r[0]
    }


def count_available_internal_skus_for_export(db: Session) -> dict:
    """
    Thống kê dải A0001–Z9999 (không tính X0000): còn bao nhiêu mã có thể xuất (chưa SP, không đang trong reserve export trong INTERNAL_SKU_EXPORT_RESERVE_DAYS).
    """
    _purge_internal_sku_exports_expired(db)
    db.commit()
    used = internal_sku_codes_in_use(db)
    exported = internal_sku_codes_exported(db)
    drafts = internal_sku_codes_in_import_drafts(db)
    sheet = _customer_sheet_internal_skus_cached()
    blocked = used | exported | drafts | sheet
    zero_suffix_in_blocked = sum(1 for ch in _LETTERS if f"{ch}0000" in blocked)
    avail = INTERNAL_SKU_ASSIGNABLE_TOTAL - len(blocked) + zero_suffix_in_blocked
    return {
        "total_space": INTERNAL_SKU_ASSIGNABLE_TOTAL,
        "available": max(0, avail),
        "used_on_products": len(used),
        "exported_reserved": len(exported),
        "blocked_distinct": len(blocked),
    }


def allocate_unused_internal_skus_for_export(db: Session, count: int) -> list[str]:
    """
    Lấy `count` mã đầu tiên trong dải A0001…Z9999 (bỏ qua X0000) không có trong products.code
    và chưa trong pool export đang hiệu lực (`INTERNAL_SKU_EXPORT_RESERVE_DAYS`); ghi vào internal_sku_exports và commit.
    """
    if count < 1:
        raise ValueError("Số lượng phải >= 1")
    if count > 10_000:
        raise ValueError("Mỗi lần export tối đa 10.000 mã")

    _purge_internal_sku_exports_expired(db)
    db.flush()
    draft_codes = internal_sku_codes_in_import_drafts(db)
    sheet_codes = _customer_sheet_internal_skus_cached()
    blocked = internal_sku_codes_in_use(db) | internal_sku_codes_exported(db) | draft_codes | sheet_codes
    chosen: list[str] = []
    for letter in _LETTERS:
        for n in range(10000):
            sku = f"{letter}{n:04d}"
            if _is_disallowed_internal_sku_create(sku):
                continue
            if sku in blocked:
                continue
            chosen.append(sku)
            blocked.add(sku)
            if len(chosen) >= count:
                break
        if len(chosen) >= count:
            break

    if len(chosen) < count:
        raise RuntimeError(
            f"Không đủ mã SKU trống: cần {count}, chỉ còn tối đa {len(chosen)} "
            "(A0001–Z9999, không *0000; trừ mã đã gán SP, nháp import, pool export TTL và ô SKU trên Google Sheet)."
        )

    from sqlalchemy.exc import IntegrityError

    for c in chosen:
        db.add(InternalSkuExport(code=c))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise RuntimeError(
            "Ghi mã export bị trùng (có thể do thao tác song song). Thử lại với số lượng nhỏ hơn."
        ) from None
    return chosen


def _random_sku() -> str:
    for _ in range(256):
        sku = secrets.choice(_LETTERS) + f"{secrets.randbelow(10000):04d}"
        if not _is_disallowed_internal_sku_create(sku):
            return sku
    return secrets.choice(_LETTERS) + f"{secrets.randbelow(9999) + 1:04d}"


def allocate_first_unused_exported_internal_sku(
    db: Session,
    *,
    exclude_product_id: Optional[int] = None,
    exclude_draft_id: Optional[int] = None,
    batch_reserved: Optional[Set[str]] = None,
) -> str:
    """
    Luồng import link 1688 / Hibox: purge export quá hạn trong cùng session (flush) rồi lấy mã trong
    `internal_sku_exports` còn hiệu lực và chưa gán SP / chưa chiếm trong nháp / sheet SKU.
    """
    _purge_internal_sku_exports_expired(db)
    db.flush()

    reserved = batch_reserved if batch_reserved is not None else set()
    draft_blocked = internal_sku_codes_in_import_drafts(db, exclude_draft_id)
    sheet_blocked = _customer_sheet_internal_skus_cached()
    cutoff = _internal_sku_export_cutoff_utc()
    ordered = (
        db.query(InternalSkuExport.code)
        .filter(InternalSkuExport.exported_at >= cutoff)
        .order_by(InternalSkuExport.id.asc())
        .all()
    )
    for (code,) in ordered:
        c = str(code).strip().upper()
        if not INTERNAL_SKU_RE.fullmatch(c):
            continue
        if _is_disallowed_internal_sku_create(c):
            continue
        if c in reserved:
            continue
        if _internal_sku_taken_by_other_product(db, c, exclude_product_id):
            continue
        if c in draft_blocked or c in sheet_blocked:
            continue
        reserved.add(c)
        return c
    raise RuntimeError(
        "Không còn mã SKU trong danh sách đã xuất mà chưa gán sản phẩm. "
        "Hãy tải thêm SKU trống (xuất file) trong trang Admin sản phẩm."
    )


def ensure_import_link_internal_product_code(
    db: Session,
    proposed: Optional[str],
    *,
    exclude_product_id: Optional[int] = None,
    exclude_draft_id: Optional[int] = None,
    batch_reserved: Optional[Set[str]] = None,
) -> str:
    """
    SKU cho nháp / đăng từ import link (1688, Hibox, Excel batch link):

    - Nếu admin nhập ô «Mã sp» đúng [A-Z][0-9]{4} (trừ mã kết thúc «0000» — coi như placeholder, hệ thống bỏ qua và cấp mã khác)
      và không trùng SP khác / nháp khác / ô sheet SKU: chấp nhận nếu có trong pool
      `internal_sku_exports` còn hiệu lực (INTERNAL_SKU_EXPORT_RESERVE_DAYS), hoặc sau khi TTL hết
      thì có thể dùng mã trống bất kỳ trong dải nội bộ không cần đối chiếu file xuất.
    - Ô trống: ưu tiên FIFO mã đã export còn hiệu lực và chưa gán SP; không còn thì sinh mã như luồng Excel thường.
    """
    reserved = batch_reserved if batch_reserved is not None else set()

    raw = (proposed or "").strip()
    if raw:
        cand = raw.upper()
        if INTERNAL_SKU_RE.fullmatch(cand) and not _is_disallowed_internal_sku_create(cand):
            if cand in reserved:
                raise ValueError(f"Mã {cand} đã được dùng trong cùng thao tác lô.")
            if internal_sku_conflicts_global_inventory(
                db,
                cand,
                exclude_product_id=exclude_product_id,
                exclude_draft_id=exclude_draft_id,
            ):
                raise ValueError(
                    f"Mã SKU {cand} đã được dùng trong nháp import khác, trên sheet SKU danh sách khách "
                    "hoặc gán cho sản phẩm khác. Chọn mã khác hoặc để ô Mã sp trống."
                )
            if _code_reserved_by_export(db, cand):
                reserved.add(cand)
                return cand
            reserved.add(cand)
            return cand

    try:
        return allocate_first_unused_exported_internal_sku(
            db,
            exclude_product_id=exclude_product_id,
            exclude_draft_id=exclude_draft_id,
            batch_reserved=batch_reserved,
        )
    except RuntimeError:
        return ensure_unique_internal_product_code(
            db,
            None,
            exclude_product_id=exclude_product_id,
            exclude_draft_id=exclude_draft_id,
            batch_reserved=batch_reserved,
        )


def ensure_unique_internal_product_code(
    db: Session,
    proposed: Optional[str],
    *,
    exclude_product_id: Optional[int] = None,
    exclude_draft_id: Optional[int] = None,
    batch_reserved: Optional[Set[str]] = None,
) -> str:
    """
    Trả `code` đúng `[A-Z][0-9]{4}`.

    - Nếu `proposed` đã đúng định dạng và không phải mã kết thúc «0000» (A0000–Z0000 — không nhận),
      không trùng `batch_reserved` và không trùng SP / nháp / sheet → giữ.
    - Ngược lại → sinh ngẫu nhiên; `batch_reserved` được mutate để tránh trùng trong cùng batch.
    """
    reserved = batch_reserved if batch_reserved is not None else set()
    draft_codes = internal_sku_codes_in_import_drafts(db, exclude_draft_id)
    sheet_codes = _customer_sheet_internal_skus_cached()

    raw = (proposed or "").strip()
    if raw:
        cand = raw.upper()
        if INTERNAL_SKU_RE.fullmatch(cand) and not _is_disallowed_internal_sku_create(cand):
            if cand not in reserved and not internal_sku_conflicts_global_inventory(
                db,
                cand,
                exclude_product_id=exclude_product_id,
                exclude_draft_id=exclude_draft_id,
            ):
                reserved.add(cand)
                return cand

    for _ in range(_MAX_RANDOM_TRIES):
        sku = _random_sku()
        if sku in reserved:
            continue
        if _blocked_for_auto_assign_internal_sku(
            db,
            sku,
            exclude_product_id,
            exclude_draft_id=exclude_draft_id,
            draft_codes=draft_codes,
            sheet_codes=sheet_codes,
        ):
            continue
        reserved.add(sku)
        return sku

    for letter in _LETTERS:
        for n in range(10000):
            sku = f"{letter}{n:04d}"
            if _is_disallowed_internal_sku_create(sku):
                continue
            if sku in reserved:
                continue
            if _blocked_for_auto_assign_internal_sku(
                db,
                sku,
                exclude_product_id,
                exclude_draft_id=exclude_draft_id,
                draft_codes=draft_codes,
                sheet_codes=sheet_codes,
            ):
                continue
            reserved.add(sku)
            return sku

    raise RuntimeError("product_internal_sku: không còn mã trống (A-Z × 0001-9999, không X0000).")


def sync_internal_code_into_product_info(product_info: Any, code: str) -> Any:
    """
    Ghi `product_info.product_info.sku` = mã nội bộ (A1234).
    Slug link / id offer không đặt vào đây (giữ qua các cột sản phẩm khác như shop_id/link).
    """
    if not (code or "").strip():
        return product_info
    sku_clean = (code or "").strip().upper()

    root: Any = product_info
    if root is None:
        root = {}
    elif isinstance(root, str):
        s = root.strip()
        if not s:
            root = {}
        else:
            try:
                root = json.loads(s)
            except json.JSONDecodeError:
                return product_info
    if not isinstance(root, dict):
        return product_info

    out = copy.deepcopy(root)
    inner = out.get("product_info")
    inner_dict = dict(inner) if isinstance(inner, dict) else {}
    inner_dict["sku"] = sku_clean
    out["product_info"] = inner_dict
    return out
