"""Chuẩn hóa và sửa lỗi gõ nhầm email phổ biến (import khách hàng cũ)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from email_validator import EmailNotValidError, validate_email

# Sai TLD / domain hay gặp khi khách gõ tay
_TLD_FIXES = (
    (re.compile(r"\.con$", re.I), ".com"),
    (re.compile(r"\.cmo$", re.I), ".com"),
    (re.compile(r"\.comn$", re.I), ".com"),
    (re.compile(r"\.comm$", re.I), ".com"),
    (re.compile(r"\.coom$", re.I), ".com"),
    (re.compile(r"\.conm$", re.I), ".com"),
    (re.compile(r"\.vnn$", re.I), ".vn"),
    (re.compile(r"\.v$", re.I), ".vn"),
)

_DOMAIN_TYPOS = {
    "gmial.com": "gmail.com",
    "gmai.com": "gmail.com",
    "gamil.com": "gmail.com",
    "gnail.com": "gmail.com",
    "gmaill.com": "gmail.com",
    "gmail.con": "gmail.com",
    "gmail.cmo": "gmail.com",
    "gmail.co": "gmail.com",
    "yahooo.com": "yahoo.com",
    "yaho.com": "yahoo.com",
    "yahho.com": "yahoo.com",
    "yahoo.con": "yahoo.com",
    "hotmial.com": "hotmail.com",
    "hotmal.com": "hotmail.com",
    "hotmail.con": "hotmail.com",
    "outlok.com": "outlook.com",
    "outlook.con": "outlook.com",
    "iclould.com": "icloud.com",
    "icloud.con": "icloud.com",
}


@dataclass
class EmailNormalizeResult:
    email: Optional[str]
    original: str
    corrected: bool
    fixes: List[str]
    invalid_reason: Optional[str] = None


def _basic_cleanup(raw: str) -> str:
    text = (raw or "").strip().lower()
    if not text or text in ("nan", "none", "null", "-"):
        return ""
    if text.endswith(".0"):
        text = text[:-2]
    text = text.replace(" ", "").replace("\u00a0", "")
    text = text.replace(";", "@") if "@" not in text and ";" in text else text
    text = re.sub(r"\.{2,}", ".", text)
    text = text.strip(".")
    return text


def _try_validate(text: str) -> Optional[str]:
    if not text or "@" not in text:
        return None
    try:
        return validate_email(text, check_deliverability=False).normalized
    except EmailNotValidError:
        return None


def _apply_domain_fixes(text: str) -> Tuple[str, List[str]]:
    fixes: List[str] = []
    candidate = text
    if "@" not in candidate:
        return candidate, fixes

    local, domain = candidate.rsplit("@", 1)
    domain = domain.strip(".")

    for pattern, repl in _TLD_FIXES:
        new_domain = pattern.sub(repl, domain)
        if new_domain != domain:
            fixes.append(f"TLD: {domain} → {new_domain}")
            domain = new_domain

    mapped = _DOMAIN_TYPOS.get(domain)
    if mapped and mapped != domain:
        fixes.append(f"domain: {domain} → {mapped}")
        domain = mapped

    return f"{local}@{domain}", fixes


def normalize_email_with_fix(raw: str) -> EmailNormalizeResult:
    """Thử validate; luôn sửa lỗi domain/TLD phổ biến trước khi chấp nhận."""
    original = (raw or "").strip()
    text = _basic_cleanup(original)
    if not text:
        return EmailNormalizeResult(
            email=None,
            original=original,
            corrected=False,
            fixes=[],
            invalid_reason="Trống",
        )

    all_fixes: List[str] = []
    candidate, domain_fixes = _apply_domain_fixes(text)
    if domain_fixes:
        all_fixes.extend(domain_fixes)

    valid = _try_validate(candidate)
    if valid:
        return EmailNormalizeResult(
            email=valid,
            original=original,
            corrected=candidate != text or bool(all_fixes),
            fixes=all_fixes,
        )

    # Thử sửa .con/.cmo… trên cả chuỗi (trường hợp domain lạ)
    for pattern, repl in _TLD_FIXES:
        new_candidate = pattern.sub(repl, candidate)
        if new_candidate != candidate:
            all_fixes.append(f"sửa đuôi: {candidate} → {new_candidate}")
            candidate = new_candidate
            valid = _try_validate(candidate)
            if valid:
                return EmailNormalizeResult(
                    email=valid,
                    original=original,
                    corrected=True,
                    fixes=all_fixes,
                )

    return EmailNormalizeResult(
        email=None,
        original=original,
        corrected=False,
        fixes=all_fixes,
        invalid_reason="Không đúng định dạng email",
    )


def normalize_email(raw: str) -> Optional[str]:
    """API tương thích cũ — trả email đã chuẩn hoá hoặc None."""
    return normalize_email_with_fix(raw).email
