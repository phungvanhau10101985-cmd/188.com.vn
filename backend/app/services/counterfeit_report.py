"""Danh sách sản phẩm nghi hàng giả: mail admin và file export đủ cột catalog."""
from __future__ import annotations

import html
import logging
import threading
from io import BytesIO
from typing import Any, Dict, List

from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Query, Session

from app.core.config import settings
from app.models.product import Product
from app.services.consult_image_text import (
    COUNTERFEIT_IMAGE_KEY,
    counterfeit_hit_labels,
    image_counterfeit_risk,
)

logger = logging.getLogger(__name__)


def counterfeit_products_query(db: Session, q: str = "") -> Query:
    risk = Product.consult_image_text[COUNTERFEIT_IMAGE_KEY]["risk"]
    expr = risk.astext == "true" if hasattr(risk, "astext") else cast(risk, String) == "true"
    query = db.query(Product).filter(expr)
    text = (q or "").strip()
    if text:
        like = f"%{text}%"
        query = query.filter(
            or_(
                Product.name.ilike(like),
                Product.product_id.ilike(like),
                Product.code.ilike(like),
            )
        )
    return query.order_by(Product.id.desc())


def counterfeit_image_rows(stored: Any) -> List[Dict[str, Any]]:
    if not image_counterfeit_risk(stored):
        return []
    flag = stored.get(COUNTERFEIT_IMAGE_KEY) or {}
    rows: List[Dict[str, Any]] = []
    for url, hits in (flag.get("by_url") or {}).items():
        if not isinstance(url, str) or not url.strip() or not isinstance(hits, list):
            continue
        names = [str(hit).strip() for hit in hits if str(hit).strip()]
        if names:
            rows.append({"url": url.strip(), "hits": names})
    return rows


def counterfeit_list_item(product: Product) -> Dict[str, Any]:
    stored = getattr(product, "consult_image_text", None)
    return {
        "id": product.id,
        "product_id": product.product_id,
        "code": product.code or "",
        "name": product.name or "",
        "price": product.price or 0,
        "is_active": bool(product.is_active),
        "slug": product.slug or "",
        "main_image": product.main_image or "",
        "hits": counterfeit_hit_labels(stored),
        "images": counterfeit_image_rows(stored),
    }


def _recipient_emails() -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    extra = getattr(settings, "VPS_BACKUP_NOTIFY_EMAILS", None) or []
    for raw in extra:
        email = str(raw).strip().lower()
        if email and "@" in email and email not in seen:
            seen.add(email)
            out.append(email)
    try:
        from app.services.auth_failure_alert import _get_admin_recipient_emails

        for addr in _get_admin_recipient_emails():
            email = (addr or "").strip().lower()
            if email and "@" in email and email not in seen:
                seen.add(email)
                out.append(email)
    except Exception as exc:
        logger.warning("counterfeit report: không đọc email admin (%s)", exc)
    return out


def _report_url() -> str:
    base = (
        getattr(settings, "FRONTEND_BASE_URL", None)
        or getattr(settings, "WEBSITE_URL", None)
        or "https://188.com.vn"
    ).strip().rstrip("/")
    return f"{base}/admin/products/hang-gia"


def schedule_counterfeit_payload(payload: Dict[str, Any]) -> None:
    """Gửi sau khi đã lưu DB. Không chặn job bản địa hóa."""
    threading.Thread(target=_send_counterfeit_email, args=(payload,), daemon=True).start()


def _send_counterfeit_email(payload: Dict[str, Any]) -> None:
    recipients = _recipient_emails()
    if not recipients:
        logger.warning("counterfeit report skip: không có email admin")
        return
    if not settings.is_smtp_configured():
        logger.warning("counterfeit report skip: SMTP chưa cấu hình")
        return
    from app.services.email_service import send_email

    product_id = payload.get("product_id") or ""
    name = payload.get("name") or ""
    hits = payload.get("hits") or []
    images = payload.get("images") or []
    link = _report_url()
    hit_line = ", ".join(hits) or "—"
    image_lines = []
    for row in images:
        image_lines.append(f"- {row.get('url')}: {', '.join(row.get('hits') or [])}")
    image_block = "\n".join(image_lines) or "—"
    subject = f"[188.com.vn] Nghi hàng giả: {product_id}"
    text_body = (
        f"Sản phẩm có dấu hiệu hàng giả khi kiểm tra ảnh.\n\n"
        f"Mã: {product_id}\n"
        f"SKU: {payload.get('code') or '—'}\n"
        f"Tên: {name}\n"
        f"Dấu hiệu: {hit_line}\n\n"
        f"Ảnh:\n{image_block}\n\n"
        f"Sản phẩm không đưa vào nguồn cấp dữ liệu.\n"
        f"Báo cáo: {link}\n"
    )
    image_html = "".join(
        f"<li>{html.escape(str(row.get('url') or ''))}: {html.escape(', '.join(row.get('hits') or []))}</li>"
        for row in images
    ) or "<li>—</li>"
    html_body = (
        f"<p>Sản phẩm có dấu hiệu hàng giả khi kiểm tra ảnh.</p>"
        f"<p><b>Mã:</b> {html.escape(product_id)}<br>"
        f"<b>Tên:</b> {html.escape(name)}<br>"
        f"<b>Dấu hiệu:</b> {html.escape(hit_line)}</p>"
        f"<ul>{image_html}</ul>"
        f"<p>Sản phẩm không đưa vào nguồn cấp dữ liệu.</p>"
        f'<p><a href="{html.escape(link)}">Mở báo cáo hàng giả</a></p>'
    )
    for addr in recipients:
        try:
            send_email(addr, subject, text_body, html_body)
        except Exception:
            logger.warning("counterfeit report: gửi mail lỗi %s", addr, exc_info=True)


def build_counterfeit_export_xlsx(products: List[Product]) -> bytes:
    """Cùng cột export catalog, thêm dấu hiệu và ảnh nghi."""
    import pandas as pd

    from app.crud.product import product_to_excel_row
    from app.services.excel_importer import PRODUCT_EXCEL_EXPORT_COLUMNS

    hit_col = "Dấu hiệu hàng giả"
    image_col = "Ảnh nghi hàng giả"
    rows = []
    for product in products:
        row = product_to_excel_row(product) or {"id": getattr(product, "product_id", "") or ""}
        stored = getattr(product, "consult_image_text", None)
        row[hit_col] = ", ".join(counterfeit_hit_labels(stored))
        row[image_col] = " | ".join(
            f"{item['url']} ({', '.join(item['hits'])})" for item in counterfeit_image_rows(stored)
        )
        rows.append(row)
    columns = list(PRODUCT_EXCEL_EXPORT_COLUMNS) + [hit_col, image_col]
    frame = pd.DataFrame(rows, columns=columns)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Hang gia", index=False)
    return buf.getvalue()
