"""SKU hiển thị web: đúng 1 chữ Latin in hoa + 4 chữ số (vd K0842).

Đảm bảo không trùng trong một lô import (`batch_reserved`) và không trùng `products.code` đã có
(trừ bản ghi `exclude_product_id` khi đang cập nhật).
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
    """True nếu mã thuộc dải nội bộ nhưng không được tạo mới (hiện tại: X0000)."""
    c = (code or "").strip().upper()
    return c in _INTERNAL_SKU_DISALLOWED_ZERO_SUFFIX


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


def _blocked_for_auto_assign_internal_sku(db: Session, code: str, exclude_product_id: Optional[int]) -> bool:
    """Sinh tự động: tránh mã đã export (dành file) và mã đã có trên SP khác."""
    c = (code or "").strip().upper()
    if _code_reserved_by_export(db, c):
        return True
    return _internal_sku_taken_by_other_product(db, c, exclude_product_id)


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
    blocked = used | exported
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
    blocked = internal_sku_codes_in_use(db) | internal_sku_codes_exported(db)
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
            f"Không đủ mã SKU trống: cần {count}, chỉ còn tối đa {len(chosen)} (A0001–Z9999, không X0000, trừ SP và đã export)."
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
    batch_reserved: Optional[Set[str]] = None,
) -> str:
    """
    Luồng import link 1688 / Hibox: purge export quá hạn trong cùng session (flush) rồi lấy mã trong
    `internal_sku_exports` còn hiệu lực và chưa gán SP.
    """
    _purge_internal_sku_exports_expired(db)
    db.flush()

    reserved = batch_reserved if batch_reserved is not None else set()
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
        if c in reserved:
            continue
        if _internal_sku_taken_by_other_product(db, c, exclude_product_id):
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
    batch_reserved: Optional[Set[str]] = None,
) -> str:
    """
    SKU cho nháp / đăng từ import link (1688, Hibox, Excel batch link):

    - Nếu admin nhập ô «Mã sp» đúng [A-Z][0-9]{4} và không trùng SP khác: chấp nhận nếu có trong pool
      `internal_sku_exports` còn hiệu lực (INTERNAL_SKU_EXPORT_RESERVE_DAYS), hoặc sau khi TTL hết
      thì có thể dùng mã trống bất kỳ trong dải nội bộ không cần đối chiếu file xuất.
    - Ô trống: ưu tiên FIFO mã đã export còn hiệu lực và chưa gán SP; không còn thì sinh mã như luồng Excel thường.
    """
    reserved = batch_reserved if batch_reserved is not None else set()

    raw = (proposed or "").strip()
    if raw:
        cand = raw.upper()
        if INTERNAL_SKU_RE.fullmatch(cand):
            if cand in reserved:
                raise ValueError(f"Mã {cand} đã được dùng trong cùng thao tác lô.")
            if _internal_sku_taken_by_other_product(db, cand, exclude_product_id):
                raise ValueError(
                    f"Mã SKU {cand} đã được gán cho sản phẩm trong hệ thống. "
                    "Chọn mã khác trong file đã xuất hoặc để ô Mã sp trống để nhận mã đã xuất tiếp theo."
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
            batch_reserved=batch_reserved,
        )
    except RuntimeError:
        return ensure_unique_internal_product_code(
            db,
            None,
            exclude_product_id=exclude_product_id,
            batch_reserved=batch_reserved,
        )


def ensure_unique_internal_product_code(
    db: Session,
    proposed: Optional[str],
    *,
    exclude_product_id: Optional[int] = None,
    batch_reserved: Optional[Set[str]] = None,
) -> str:
    """
    Trả `code` đúng `[A-Z][0-9]{4}`.

    - Nếu `proposed` đã đúng định dạng (không phân biệt hoa/thường chữ cái đầu),
      không trùng `batch_reserved` và không bị SP khác chiếm trong DB → giữ.
    - Ngược lại → sinh ngẫu nhiên; `batch_reserved` được mutate để tránh trùng trong cùng batch.
    """
    reserved = batch_reserved if batch_reserved is not None else set()

    raw = (proposed or "").strip()
    if raw:
        cand = raw.upper()
        if INTERNAL_SKU_RE.fullmatch(cand):
            # Mã nhập tay / từ Excel (kể cả mã đã xuất file trước đó) — chỉ cấm trùng SP khác.
            if cand not in reserved and not _internal_sku_taken_by_other_product(db, cand, exclude_product_id):
                reserved.add(cand)
                return cand

    for _ in range(_MAX_RANDOM_TRIES):
        sku = _random_sku()
        if sku in reserved:
            continue
        if _blocked_for_auto_assign_internal_sku(db, sku, exclude_product_id):
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
            if _blocked_for_auto_assign_internal_sku(db, sku, exclude_product_id):
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
