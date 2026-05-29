"""Import danh sách khách cũ (name, gender, email, birthday, phone) từ CSV/Excel."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, List, Optional, Set

import pandas as pd

from app.services.email_normalize import normalize_email_with_fix

_NAME_COLS = frozenset({"name", "ten", "họ tên", "ho ten", "hoten", "full_name", "fullname"})
_GENDER_COLS = frozenset({"gender", "gioi tinh", "giới tính", "gioitinh", "sex"})
_EMAIL_COLS = frozenset(
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
_BIRTHDAY_COLS = frozenset({"birthday", "birth_date", "date_of_birth", "ngay sinh", "ngày sinh", "dob"})
_PHONE_COLS = frozenset({"phone", "mobile", "sdt", "sđt", "dien thoai", "điện thoại", "tel"})


@dataclass
class ParsedCustomerRow:
    row_number: int
    name: Optional[str] = None
    gender: Optional[str] = None
    email: Optional[str] = None
    email_original: Optional[str] = None
    email_corrected: bool = False
    email_fixes: List[str] = field(default_factory=list)
    birthday: Optional[date] = None
    phone: Optional[str] = None
    invalid_reason: Optional[str] = None


@dataclass
class CustomerImportParseResult:
    rows: List[ParsedCustomerRow] = field(default_factory=list)
    total_input: int = 0
    valid_count: int = 0
    corrected_count: int = 0
    invalid_count: int = 0
    duplicate_in_file: int = 0


def _norm_col(name: Any) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def _pick_column(cols: dict[str, str], aliases: frozenset[str]) -> Optional[str]:
    for key, orig in cols.items():
        if key in aliases:
            return orig
    for key, orig in cols.items():
        for alias in aliases:
            if alias in key or key in alias:
                return orig
    return None


def _cell_str(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() in ("nan", "none", "null"):
        return ""
    return text


def _parse_gender(raw: str) -> Optional[str]:
    text = (raw or "").strip()
    if not text:
        return None
    low = text.lower()
    if low in ("nam", "male", "m"):
        return "Nam"
    if low in ("nữ", "nu", "female", "f"):
        return "Nữ"
    return text[:20]


def _parse_birthday(value: Any) -> Optional[date]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _cell_str(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text.split()[0], fmt).date()
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(text, dayfirst=False, errors="coerce")
        if pd.isna(parsed):
            parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.date()
    except Exception:
        return None


def _parse_phone(value: Any) -> Optional[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        if value == int(value):
            text = str(int(value))
        else:
            text = str(value)
    else:
        text = _cell_str(value)
    if not text:
        return None
    if text.endswith(".0"):
        text = text[:-2]
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    if len(digits) == 9 and digits[0] in "35789":
        digits = "0" + digits
    elif len(digits) == 10 and digits.startswith("84"):
        digits = "0" + digits[2:]
    if len(digits) > 15:
        return digits[:15]
    return digits


def _read_dataframe(filename: str, content: bytes) -> pd.DataFrame:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(content))
    else:
        raise ValueError("Định dạng không hỗ trợ — dùng .csv, .xlsx hoặc .xls")
    df.columns = [_norm_col(c) for c in df.columns]
    return df


def parse_customer_upload(filename: str, content: bytes) -> CustomerImportParseResult:
    df = _read_dataframe(filename, content)
    if df.empty:
        raise ValueError("File không có dòng dữ liệu.")

    cols = {str(c).strip().lower(): c for c in df.columns}
    email_col = _pick_column(cols, _EMAIL_COLS)
    if email_col is None:
        raise ValueError("Không tìm thấy cột email trong file.")

    name_col = _pick_column(cols, _NAME_COLS)
    gender_col = _pick_column(cols, _GENDER_COLS)
    birthday_col = _pick_column(cols, _BIRTHDAY_COLS)
    phone_col = _pick_column(cols, _PHONE_COLS)

    result = CustomerImportParseResult(total_input=len(df))
    seen_emails: Set[str] = set()

    for idx, row in df.iterrows():
        row_num = int(idx) + 2  # header = row 1
        raw_email = _cell_str(row.get(email_col))
        email_result = normalize_email_with_fix(raw_email)

        phone = _parse_phone(row.get(phone_col)) if phone_col else None
        parsed = ParsedCustomerRow(
            row_number=row_num,
            name=_cell_str(row.get(name_col))[:255] if name_col else None,
            gender=_parse_gender(_cell_str(row.get(gender_col))) if gender_col else None,
            email_original=raw_email or None,
            email_fixes=list(email_result.fixes),
            birthday=_parse_birthday(row.get(birthday_col)) if birthday_col else None,
            phone=phone,
        )

        has_valid_phone = bool(phone and phone.startswith("0") and 10 <= len(phone) <= 11)

        if email_result.email:
            if email_result.email in seen_emails:
                parsed.invalid_reason = "Email trùng trong file"
                result.duplicate_in_file += 1
                result.invalid_count += 1
            else:
                seen_emails.add(email_result.email)
                parsed.email = email_result.email
                parsed.email_corrected = email_result.corrected
                result.valid_count += 1
                if email_result.corrected:
                    result.corrected_count += 1
        elif has_valid_phone:
            parsed.invalid_reason = None
            result.valid_count += 1
        else:
            parsed.invalid_reason = email_result.invalid_reason or "Thiếu email/SĐT hợp lệ"
            result.invalid_count += 1

        if parsed.name == "":
            parsed.name = None
        result.rows.append(parsed)

    return result
