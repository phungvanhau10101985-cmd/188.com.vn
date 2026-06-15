"""
Cookie Playwright dùng chung: lấy thông tin SP (Hibox, Vipomall, 1688), kiểm tra tồn kho nguồn.

Một file JSON trên server — mỗi scraper chỉ áp cookie khớp domain trang đang mở.
Link không cần đăng nhập vẫn scrape được; cookie giúp trang khó / đã đăng nhập.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from app.core.config import settings

logger = logging.getLogger(__name__)

_DEFAULT_COOKIE_FILENAME = "scraper-cookies.json"
_LEGACY_COOKIE_FILENAME = "1688-cookies.json"

# Origin mở trước khi add_cookies (Playwright yêu cầu khớp domain).
_HOST_SEED_URLS: Dict[str, str] = {
    "hibox.mn": "https://hibox.mn/",
    "taobao1688.kz": "https://taobao1688.kz/",
    "vipomall.vn": "https://vipomall.vn/",
    "taobao.com": "https://www.taobao.com/",
    "tmall.com": "https://www.tmall.com/",
    "1688.com": "https://www.1688.com/",
    "alibaba.com": "https://www.alibaba.com/",
    "pandamall.vn": "https://pandamall.vn/",
}


def backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_cookie_file() -> Path:
    return backend_root() / _DEFAULT_COOKIE_FILENAME


def _legacy_cookie_file() -> Path:
    return backend_root() / _LEGACY_COOKIE_FILENAME


def _cookie_json_from_settings() -> str:
    raw = (getattr(settings, "IMPORT_SCRAPER_COOKIE_JSON", "") or "").strip()
    if raw:
        return raw
    return (getattr(settings, "IMPORT_1688_COOKIE_JSON", "") or "").strip()


def _cookie_file_from_settings() -> str:
    path = (getattr(settings, "IMPORT_SCRAPER_COOKIE_FILE", "") or "").strip()
    if path:
        return path
    return (getattr(settings, "IMPORT_1688_COOKIE_FILE", "") or "").strip()


def _resolve_cookie_path(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = backend_root() / path
    return path


def normalize_playwright_cookie(item: Dict[str, Any], *, default_domain: str = "") -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    name = str(item.get("name") or "").strip()
    if not name or item.get("value") is None:
        return None
    value = str(item.get("value"))
    domain = str(item.get("domain") or default_domain or "").strip()
    if domain.startswith("http"):
        domain = urlparse(domain).hostname or domain
    if not domain:
        return None
    path = str(item.get("path") or "/").strip() or "/"
    out: Dict[str, Any] = {"name": name, "value": value, "domain": domain, "path": path}

    exp = item.get("expires")
    if exp is None and item.get("expirationDate") is not None:
        try:
            exp = int(float(item["expirationDate"]))
        except (TypeError, ValueError):
            exp = None
    if exp is None and item.get("expiry") is not None:
        try:
            exp = int(float(item["expiry"]))
        except (TypeError, ValueError):
            exp = None
    if exp is not None:
        try:
            out["expires"] = int(exp)
        except (TypeError, ValueError):
            pass

    if isinstance(item.get("httpOnly"), bool):
        out["httpOnly"] = item["httpOnly"]
    if isinstance(item.get("secure"), bool):
        out["secure"] = item["secure"]

    ss = item.get("sameSite")
    if isinstance(ss, str) and ss.strip():
        mp = {"no_restriction": "None", "strict": "Strict", "lax": "Lax", "none": "None"}
        sv = ss.strip().lower().replace("-", "_")
        if sv in mp:
            out["sameSite"] = mp[sv]
    return out


def parse_cookie_text(cookie_text: str, *, default_domain: str = ".1688.com") -> List[Dict[str, Any]]:
    text = (cookie_text or "").strip()
    if not text:
        return []
    if text.lstrip().startswith(("[", "{")):
        data = json.loads(text)
        cookies = data.get("cookies") if isinstance(data, dict) else data
        if not isinstance(cookies, list):
            raise ValueError("JSON cookie phải là list hoặc object có key cookies.")
        out: List[Dict[str, Any]] = []
        for item in cookies:
            nc = normalize_playwright_cookie(item if isinstance(item, dict) else {}, default_domain=default_domain)
            if nc:
                out.append(nc)
        return out

    out = []
    for part in text.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        if name:
            nc = normalize_playwright_cookie(
                {"name": name, "value": value.strip(), "domain": default_domain, "path": "/"},
            )
            if nc:
                out.append(nc)
    return out


def load_scraper_cookies() -> List[Dict[str, Any]]:
    raw = _cookie_json_from_settings()
    if raw:
        try:
            return parse_cookie_text(raw)
        except Exception:
            return []

    cookie_file = _cookie_file_from_settings()
    paths: List[Path] = []
    if cookie_file:
        paths.append(_resolve_cookie_path(cookie_file))
    paths.append(default_cookie_file())
    if _legacy_cookie_file().name not in {p.name for p in paths}:
        paths.append(_legacy_cookie_file())

    for path in paths:
        if path.exists():
            try:
                return parse_cookie_text(path.read_text(encoding="utf-8"))
            except Exception:
                return []
    return []


def active_cookie_file_path() -> Optional[Path]:
    cookie_file = _cookie_file_from_settings()
    if cookie_file:
        p = _resolve_cookie_path(cookie_file)
        if p.exists():
            return p
    for p in (default_cookie_file(), _legacy_cookie_file()):
        if p.exists():
            return p
    return None


def cookie_expiry_meta(cookies: List[Dict[str, Any]]) -> dict[str, Any]:
    if not cookies:
        return {
            "cookie_expiry_known_for_all": False,
            "cookies_all_expired": False,
            "cookies_expired_count": 0,
        }
    now = time.time()
    known = 0
    expired = 0
    for c in cookies:
        exp = c.get("expires")
        if exp is None:
            continue
        try:
            exp_i = int(exp)
        except (TypeError, ValueError):
            continue
        known += 1
        if exp_i < now:
            expired += 1
    all_known = known == len(cookies)
    return {
        "cookie_expiry_known_for_all": all_known,
        "cookies_all_expired": all_known and expired == len(cookies),
        "cookies_expired_count": expired,
    }


def cookie_domain_warnings(domains: List[str]) -> List[str]:
    warnings: List[str] = []
    for d in domains:
        if d == "188.com.vn" or d.endswith(".188.com.vn"):
            warnings.append(
                "Phát hiện cookie 188.com.vn — không dùng cho scrape Hibox/Vipomall. "
                "Export lại từ hibox.mn / vipomall.vn."
            )
            break
    scrape_hosts = {"hibox.mn", "vipomall.vn", "pandamall.vn", "taobao.com", "tmall.com", "1688.com", "taobao1688.kz"}
    if domains and not any(
        any(d == h or d.endswith("." + h) for h in scrape_hosts) for d in domains
    ):
        warnings.append(
            "Không thấy domain scrape (hibox.mn, vipomall.vn, pandamall.vn, taobao…). Kiểm tra lại file export."
        )
    return warnings


def delete_scraper_cookies() -> None:
    for path in (default_cookie_file(), _legacy_cookie_file()):
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
    settings.IMPORT_SCRAPER_COOKIE_FILE = ""
    settings.IMPORT_SCRAPER_COOKIE_JSON = ""
    settings.IMPORT_1688_COOKIE_FILE = ""
    settings.IMPORT_1688_COOKIE_JSON = ""


def save_scraper_cookies_from_text(cookie_text: str) -> int:
    new_cookies = parse_cookie_text(cookie_text, default_domain="")
    if not new_cookies:
        raise ValueError("Cookie trống hoặc không đọc được name=value hợp lệ (cần domain trong JSON export).")

    existing_cookies = []
    try:
        existing_cookies = load_scraper_cookies()
    except Exception:
        pass

    cookie_map = {}
    for c in existing_cookies:
        key = (c.get("domain", ""), c.get("name", ""), c.get("path", ""))
        cookie_map[key] = c

    for c in new_cookies:
        key = (c.get("domain", ""), c.get("name", ""), c.get("path", ""))
        cookie_map[key] = c

    merged_cookies = list(cookie_map.values())

    cookie_file = default_cookie_file()
    cookie_file.write_text(json.dumps(merged_cookies, ensure_ascii=False, indent=2), encoding="utf-8")

    settings.IMPORT_SCRAPER_COOKIE_FILE = cookie_file.name
    settings.IMPORT_SCRAPER_COOKIE_JSON = ""
    settings.IMPORT_1688_COOKIE_FILE = cookie_file.name
    settings.IMPORT_1688_COOKIE_JSON = ""
    return len(merged_cookies)


def upsert_scraper_cookie_env_local(values: dict[str, str]) -> None:
    path = backend_root() / ".env.local"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = existing.splitlines()
    handled: set[str] = set()
    next_lines: list[str] = []
    for line in lines:
        replaced = False
        for key, value in values.items():
            if re.match(rf"^\s*{re.escape(key)}\s*=", line):
                next_lines.append(f"{key}={value}")
                handled.add(key)
                replaced = True
                break
        if not replaced:
            next_lines.append(line)
    for key, value in values.items():
        if key not in handled:
            next_lines.append(f"{key}={value}")
    path.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")


def cookie_domains(cookies: List[Dict[str, Any]]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for c in cookies:
        dom = str(c.get("domain") or "").strip().lstrip(".").lower()
        if dom and dom not in seen:
            seen.add(dom)
            out.append(dom)
    return out[:40]


def scraper_cookie_settings_dict(message: str | None = None) -> dict[str, Any]:
    cookies = load_scraper_cookies()
    names = [str(c.get("name") or "") for c in cookies if c.get("name")]
    domains = cookie_domains(cookies)
    expiry = cookie_expiry_meta(cookies)
    warnings = cookie_domain_warnings(domains)
    saved_at: Optional[str] = None
    path = active_cookie_file_path()
    if path is not None:
        try:
            saved_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            saved_at = None
    status = "configured"
    if not cookies:
        status = "missing"
    elif expiry.get("cookies_all_expired"):
        status = "expired"
    elif warnings:
        status = "warning"
    return {
        "enabled": bool(getattr(settings, "IMPORT_1688_ENABLED", True)),
        "cookie_file": (path.name if path else None) or (_DEFAULT_COOKIE_FILENAME if cookies else None),
        "has_cookie": bool(cookies),
        "cookie_count": len(cookies),
        "cookie_names": names[:30],
        "cookie_domains": domains,
        "cookie_saved_at": saved_at,
        "cookie_status": status,
        "cookie_warnings": warnings,
        "message": message,
        "usage_note": (
            "Một bộ cookie cho Hibox, Vipomall, PandaMall, kiểm tra tồn kho và scrape 1688 (nếu bật). "
            "Dán JSON export từ Chrome (EditThisCookie / Cookie-Editor) khi đã đăng nhập "
            "hibox.mn / vipomall.vn / pandamall.vn / taobao / 1688 — không dùng cookie 188.com.vn."
        ),
        **expiry,
    }


def _seed_url_for_cookie_domain(domain: str) -> Optional[str]:
    d = domain.lstrip(".").lower()
    for host, seed in _HOST_SEED_URLS.items():
        if d == host or d.endswith("." + host):
            return seed
    if d and "." in d:
        return f"https://{d}/"
    return None


def bucket_cookies_by_seed_url(cookies: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for c in cookies:
        dom = str(c.get("domain") or "").strip()
        seed = _seed_url_for_cookie_domain(dom)
        if not seed:
            continue
        buckets.setdefault(seed, []).append(c)
    return buckets


def hosts_for_url(url: str) -> Set[str]:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return set()
    out: Set[str] = {host}
    for hint in _HOST_SEED_URLS:
        if host == hint or host.endswith("." + hint):
            out.add(hint)
    return out


def seed_playwright_context_cookies(
    ctx: Any,
    page: Any,
    *,
    prefer_hosts: Optional[Set[str]] = None,
    target_url: Optional[str] = None,
    timeout_ms: int = 120_000,
) -> int:
    """Mở origin theo domain cookie rồi add_cookies. Trả số cookie đã gắn."""
    cookies = load_scraper_cookies()
    if not cookies:
        return 0

    hosts = set(prefer_hosts or set())
    if target_url:
        hosts |= hosts_for_url(target_url)

    buckets = bucket_cookies_by_seed_url(cookies)
    if not buckets:
        return 0

    applied = 0
    for seed_url, bucket in buckets.items():
        if hosts:
            seed_host = (urlparse(seed_url).hostname or "").lower()
            if not any(seed_host == h or seed_host.endswith("." + h) for h in hosts):
                continue
        try:
            page.goto(seed_url, wait_until="domcontentloaded", timeout=timeout_ms)
            ctx.add_cookies(bucket)
            applied += len(bucket)
        except Exception as exc:
            logger.warning("import_scraper_cookies: seed %s failed: %s", seed_url, exc)
    return applied


def _pandamall_account_file() -> Path:
    return backend_root() / "pandamall-account.json"

def get_pandamall_account() -> Dict[str, str]:
    """Trả về dict {'username': '...', 'password': '...'} từ file."""
    path = _pandamall_account_file()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {
                "username": str(data.get("username") or ""),
                "password": str(data.get("password") or ""),
            }
        return {}
    except Exception as e:
        logger.warning(f"Lỗi đọc pandamall-account.json: {e}")
        return {}

def save_pandamall_account(username: str, password: str) -> None:
    """Lưu username/password vào pandamall-account.json."""
    path = _pandamall_account_file()
    existing = get_pandamall_account()
    pwd = password.strip() if password else (existing.get("password") or "")
    try:
        data = {
            "username": username.strip() if username else "",
            "password": pwd,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"Lỗi ghi pandamall-account.json: {e}")
        raise ValueError(f"Không thể lưu cấu hình: {e}")
