"""
Một hộp Gmail/ Google Mail = một chuỗi định danh (đăng nhập OTP + Google cùng user).

- lowercase + trim
- @googlemail.com -> @gmail.com
- bỏ dấu chấm trong phần local (quy ước Google)
- bỏ hậu tố +alias (phần sau +) trong local part

Các domain khác: chỉ trim + chữ thường.
"""
from typing import Optional


def identity_email(value: Optional[str]) -> str:
    e = (value or "").strip()
    if not e or "@" not in e:
        return ""
    e = e.lower()
    local, _, domain = e.partition("@")
    domain = domain.strip()
    if not local or not domain:
        return ""
    if domain in ("gmail.com", "googlemail.com"):
        if "+" in local:
            local = local.split("+", 1)[0]
        local = local.replace(".", "")
        return f"{local}@gmail.com"
    return e
