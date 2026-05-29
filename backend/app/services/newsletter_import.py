"""Parse danh sách email từ file / text cho import admin."""

from __future__ import annotations

import io
import re
from typing import Iterable, List, Set

import pandas as pd

from app.services.email_normalize import normalize_email, normalize_email_with_fix

_EMAIL_COL_NAMES = frozenset(
    {
        "email",
        "e-mail",
        "e_mail",
        "mail",
        "email_address",
        "dia_chi_email",
        "địa chỉ email",
    }
)


def normalize_email_with_correction(raw: str):
    """Trả kết quả chuẩn hoá kèm thông tin sửa lỗi (dùng cho import)."""
    return normalize_email_with_fix(raw)


def extract_emails_from_text(text: str) -> List[str]:
    """Mỗi dòng hoặc phân tách bằng dấu phẩy/chấm phẩy."""
    out: List[str] = []
    seen: Set[str] = set()
    for line in (text or "").replace(";", "\n").replace(",", "\n").splitlines():
        chunk = line.strip()
        if not chunk:
            continue
        for token in re.split(r"\s+", chunk):
            email = normalize_email(token)
            if email and email not in seen:
                seen.add(email)
                out.append(email)
    return out


def _pick_email_column(df: pd.DataFrame) -> str | None:
    cols = {str(c).strip().lower(): c for c in df.columns}
    for key in _EMAIL_COL_NAMES:
        if key in cols:
            return cols[key]
    if len(df.columns) == 1:
        return df.columns[0]
    for c in df.columns:
        if "mail" in str(c).lower():
            return c
    return df.columns[0] if len(df.columns) else None


def extract_emails_from_upload(filename: str, content: bytes) -> List[str]:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(content))
    elif name.endswith(".txt"):
        return extract_emails_from_text(content.decode("utf-8", errors="ignore"))
    else:
        raise ValueError("Định dạng không hỗ trợ — dùng .csv, .xlsx, .xls hoặc .txt")

    df.columns = [str(c).strip().lower() for c in df.columns]
    col = _pick_email_column(df)
    if col is None:
        raise ValueError("Không tìm thấy cột email trong file")

    out: List[str] = []
    seen: Set[str] = set()
    for value in df[col].tolist():
        email = normalize_email(str(value) if value is not None else "")
        if email and email not in seen:
            seen.add(email)
            out.append(email)
    return out


def dedupe_preserve_order(emails: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for e in emails:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out
