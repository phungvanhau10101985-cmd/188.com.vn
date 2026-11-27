"""Chữ OCR trên ảnh gốc — chỉ để NanoAI tư vấn, không ghi vào trường web.

Lọc cơ học trước khi lưu. Không tóm tắt bằng AI. Dịch từng dòng; lỗi dịch thì giữ chữ gốc.
Khóa `_counterfeit` cùng cột do batch Gemini 3.8 Flash ghi. Không gửi NanoAI.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

CONSULT_IMAGE_TEXT_KEY = "consult_image_text"
IMAGE_CONSULT_CONTEXT_FIELD = "image_consult_context"
COUNTERFEIT_IMAGE_KEY = "_counterfeit"
_MAX_COUNTERFEIT_HITS = 12
_MAX_CONTEXT_LINES = 40
_MAX_LINE_CHARS = 200
_HTML_TAG_RE = re.compile(r"<[^>]*>")

# Cụm người bán / kênh liên hệ / slogan. Không gồm chữ đơn 荐|退|价|换.
_SELLER_PHRASES = (
    "实力工厂",
    "一件代发",
    "立即购买",
    "批发价格",
    "批发价",
    "wechat",
    "weixin",
    "buy now",
    "微信",
    "工厂",
    "车间",
    "品控",
    "厂家",
    "团队",
    "验货",
    "货源",
    "热卖",
    "爆款",
    "点击",
    "包邮",
    "价格",
)

_SELLER_RE = re.compile(
    "|".join(re.escape(p) for p in sorted(_SELLER_PHRASES, key=len, reverse=True)),
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://\S+|www\.\S+|\b[\w.-]+\.(?:com|cn|net|org)\b", re.IGNORECASE)
_PHONE_RE = re.compile(
    r"(?:\+?86[-\s]?)?1[3-9]\d{9}|(?:电话|手机|热线|tel|phone)\s*[:：]?\s*\+?\d[\d\s-]{6,}\d",
    re.IGNORECASE,
)
_WECHAT_ID_RE = re.compile(
    r"(?:微信|wechat|weixin|v信|vx)\s*[:：]?\s*[A-Za-z0-9_-]{3,}",
    re.IGNORECASE,
)
_QQ_RE = re.compile(r"qq\s*[:：]?\s*\d{5,}", re.IGNORECASE)
_PRICE_RE = re.compile(
    r"(?:批发价|批发价格|价格|价目|券后价|券后)\s*[:：]?\s*\d+(?:[.,]\d+)?\s*(?:元|¥|￥)?"
    r"|\d+(?:[.,]\d+)?\s*(?:元|¥|￥)"
    r"|[¥￥]\s*\d+(?:[.,]\d+)?"
)
_SIZE_RE = re.compile(
    r"^(?:"
    r"\d{1,4}(?:[.,]\d+)?(?:cm|mm|kg|g|w|v|kw|ml|l|mah)?"
    r"|(?:xxxs|xxs|xs|s|m|l|xl|xxl|xxxl|xxxxl)"
    r")$",
    re.IGNORECASE,
)
_EDGE_PUNCT_RE = re.compile(r"^[\s,，。；;、|｜:：\-—~～/／]+|[\s,，。；;、|｜:：\-—~～/／]+$")


def ocr_items_to_lines(ocr_results: Optional[Iterable[Any]]) -> List[str]:
    lines: List[str] = []
    for item in ocr_results or []:
        if isinstance(item, dict):
            text = str(item.get("text") or "")
        elif isinstance(item, (list, tuple)) and item:
            text = str(item[0] or "")
        else:
            continue
        text = _normalize_space(text)
        if text:
            lines.append(text)
    return lines


def filter_ocr_line(text: str) -> Optional[str]:
    """Giữ phần mô tả sản phẩm. None khi dòng không còn gì đáng lưu."""
    raw = _normalize_space(text)
    if not raw:
        return None
    cleaned = _URL_RE.sub(" ", raw)
    cleaned = _PHONE_RE.sub(" ", cleaned)
    cleaned = _WECHAT_ID_RE.sub(" ", cleaned)
    cleaned = _QQ_RE.sub(" ", cleaned)
    cleaned = _PRICE_RE.sub(" ", cleaned)
    cleaned = _SELLER_RE.sub(" ", cleaned)
    cleaned = _normalize_space(cleaned)
    cleaned = _EDGE_PUNCT_RE.sub("", cleaned).strip()
    if not cleaned:
        return None
    compact = re.sub(r"\s+", "", cleaned)
    if _is_short_noise(compact):
        return None
    return cleaned


def filter_ocr_lines(lines: Iterable[str]) -> List[str]:
    kept: List[str] = []
    seen = set()
    for line in lines:
        item = filter_ocr_line(line)
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        kept.append(item)
    return kept


def translate_consult_lines(
    lines: List[str],
    *,
    translate_batch: Optional[Callable[[List[str]], List[str]]] = None,
) -> List[Dict[str, str]]:
    """Một dòng một bản dịch. Lệch số dòng hoặc lỗi API thì vi = src."""
    if not lines:
        return []
    vi_lines: Optional[List[str]] = None
    fn = translate_batch or _deepseek_translate_batch
    try:
        got = fn(lines)
        if isinstance(got, list) and len(got) == len(lines):
            vi_lines = [str(x or "").strip() for x in got]
    except Exception:
        logger.warning("consult image text translate failed", exc_info=True)
        vi_lines = None
    if vi_lines is None:
        vi_lines = list(lines)
    out: List[Dict[str, str]] = []
    for src, vi in zip(lines, vi_lines):
        out.append({"src": src, "vi": vi or src})
    return out


def merge_consult_image_text(
    existing: Any,
    updates: Dict[str, List[Dict[str, str]]],
) -> Optional[Dict[str, Any]]:
    """Chỉ thay URL có trong updates. Danh sách rỗng thì xóa khóa URL đó. Giữ cờ hàng giả."""
    base: Dict[str, Any] = {}
    if isinstance(existing, dict):
        flag = existing.get(COUNTERFEIT_IMAGE_KEY)
        if isinstance(flag, dict) and (flag.get("checked") or (isinstance(flag.get("by_url"), dict) and flag.get("by_url"))):
            base[COUNTERFEIT_IMAGE_KEY] = flag
        for url, rows in existing.items():
            if url == COUNTERFEIT_IMAGE_KEY:
                continue
            if isinstance(url, str) and url.strip() and isinstance(rows, list) and rows:
                base[url] = rows
    for url, rows in updates.items():
        key = str(url or "").strip()
        if not key or key == COUNTERFEIT_IMAGE_KEY:
            continue
        if rows:
            base[key] = rows
        else:
            base.pop(key, None)
    return base or None


def set_gemini_counterfeit(stored: Any, brands: Iterable[str], image_url: str = "") -> Optional[Dict[str, Any]]:
    """Ghi hoặc xóa cờ hàng giả theo tên logo Gemini đọc được."""
    base: Dict[str, Any] = dict(stored) if isinstance(stored, dict) else {}
    base.pop(COUNTERFEIT_IMAGE_KEY, None)
    found: List[str] = []
    seen: set[str] = set()
    for raw in brands:
        token = str(raw or "").strip()
        key = token.casefold()
        if not token or key in seen:
            continue
        seen.add(key)
        found.append(token)
        if len(found) >= _MAX_COUNTERFEIT_HITS:
            break
    url = (image_url or "").strip() or "gemini"
    base[COUNTERFEIT_IMAGE_KEY] = {
        "risk": bool(found),
        "by_url": {url: found} if found else {},
        "source": "gemini-3.8-flash",
        "checked": True,
    }
    return base or None


def counterfeit_was_checked(stored: Any) -> bool:
    """Gemini đã trả kết quả cho sản phẩm này, kể cả khi không thấy logo."""
    if not isinstance(stored, dict):
        return False
    flag = stored.get(COUNTERFEIT_IMAGE_KEY)
    return isinstance(flag, dict) and bool(flag.get("checked"))


def image_counterfeit_risk(stored: Any) -> bool:
    if not isinstance(stored, dict):
        return False
    flag = stored.get(COUNTERFEIT_IMAGE_KEY)
    return isinstance(flag, dict) and bool(flag.get("risk")) and bool(flag.get("by_url"))


def storefront_may_show_product(stored: Any) -> bool:
    """Web vẫn hiện sản phẩm đã đăng. Chỉ ẩn khi đã thấy logo hàng giả."""
    return not image_counterfeit_risk(stored)


def _counterfeit_checked_and_risk():
    from sqlalchemy import String, cast

    from app.models.product import Product

    flag = Product.consult_image_text[COUNTERFEIT_IMAGE_KEY]
    checked = flag["checked"]
    risk = flag["risk"]
    if hasattr(checked, "astext"):
        checked_ok = checked.astext.in_(("true", "True"))
        risk_text = risk.astext
    else:
        checked_ok = cast(checked, String).in_(("true", "True"))
        risk_text = cast(risk, String)
    return checked_ok, risk_text


def storefront_counterfeit_cleared_clause():
    from sqlalchemy import func

    _checked_ok, risk_text = _counterfeit_checked_and_risk()
    risk_on = func.coalesce(risk_text, "false").in_(("true", "True"))
    return ~risk_on


_DISTRIBUTION_LOCALIZED = ("localized", "skipped")


def distribution_ready(stored: Any, localization_status: Any) -> bool:
    """Nguồn cấp và web nền tảng khác chỉ nhận hàng đã kiểm sạch và đã bản địa hóa."""
    status = str(localization_status or "").strip().lower()
    return (
        counterfeit_was_checked(stored)
        and not image_counterfeit_risk(stored)
        and status in _DISTRIBUTION_LOCALIZED
    )


def distribution_ready_clause():
    from sqlalchemy import and_, func

    from app.models.product import Product

    checked_ok, risk_text = _counterfeit_checked_and_risk()
    risk_on = func.coalesce(risk_text, "false").in_(("true", "True"))
    localized = func.lower(func.coalesce(Product.image_localization_status, "")).in_(_DISTRIBUTION_LOCALIZED)
    return and_(checked_ok, ~risk_on, localized)


def counterfeit_hit_labels(stored: Any) -> List[str]:
    if not image_counterfeit_risk(stored):
        return []
    flag = stored.get(COUNTERFEIT_IMAGE_KEY) or {}
    found: List[str] = []
    seen: set[str] = set()
    for hits in (flag.get("by_url") or {}).values():
        if not isinstance(hits, list):
            continue
        for hit in hits:
            token = str(hit or "").strip()
            key = token.casefold()
            if not token or key in seen:
                continue
            seen.add(key)
            found.append(token)
    return found


def counterfeit_hit_fingerprint(stored: Any) -> Tuple[str, ...]:
    return tuple(sorted(label.casefold() for label in counterfeit_hit_labels(stored)))


def consult_updates_from_results(results: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
    """URL có consult_ocr_texts (kể cả list rỗng) mới được cập nhật. None = không đụng."""
    updates: Dict[str, List[Dict[str, str]]] = {}
    for url, res in results.items():
        raw = getattr(res, "consult_ocr_texts", None)
        if raw is None:
            continue
        kept = filter_ocr_lines(raw if isinstance(raw, list) else [])
        updates[str(url)] = translate_consult_lines(kept)
    return updates


def build_image_consult_context(stored: Any) -> Optional[Dict[str, Any]]:
    """Shape NanoAI `image_consult_context`. None khi không còn dòng — không gửi `{lines: []}`.

    Không ghi vào product_info. Tối đa 40 dòng, mỗi dòng 200 ký tự, không HTML.
    """
    if not isinstance(stored, dict) or not stored:
        return None
    images: List[Dict[str, Any]] = []
    flat: List[Dict[str, str]] = []
    seen = set()
    for url, rows in stored.items():
        if len(flat) >= _MAX_CONTEXT_LINES:
            break
        if url == COUNTERFEIT_IMAGE_KEY:
            continue
        if not isinstance(url, str) or not url.strip() or not isinstance(rows, list):
            continue
        image_lines: List[Dict[str, str]] = []
        for row in rows:
            if len(flat) >= _MAX_CONTEXT_LINES:
                break
            line = _context_line(row)
            if line is None:
                continue
            key = line["src"].casefold()
            if key in seen:
                continue
            seen.add(key)
            image_lines.append(line)
            flat.append(line)
        if image_lines:
            images.append({"url": url.strip(), "lines": image_lines})
    if not flat:
        return None
    payload: Dict[str, Any] = {"language": "vi", "lines": flat}
    if images:
        payload["images"] = images
    return payload


def _context_line(row: Any) -> Optional[Dict[str, str]]:
    if not isinstance(row, dict):
        return None
    src = filter_ocr_line(_plain_text(str(row.get("src") or "")))
    if not src:
        return None
    src = src[:_MAX_LINE_CHARS]
    vi = _plain_text(str(row.get("vi") or ""))[:_MAX_LINE_CHARS]
    return {"src": src, "vi": vi}


def _plain_text(text: str) -> str:
    return _normalize_space(_HTML_TAG_RE.sub("", text or ""))


def _normalize_space(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"\s+", " ", t).strip()


def _is_short_noise(compact: str) -> bool:
    n = len(compact)
    if n == 0:
        return True
    if n > 2:
        return False
    if _SIZE_RE.fullmatch(compact):
        return False
    # Hai chữ Hán thường là từ (纯棉), không phải mảnh OCR một ký tự.
    if n == 2 and all("\u4e00" <= ch <= "\u9fff" for ch in compact):
        return False
    return True


def _deepseek_translate_batch(lines: List[str]) -> List[str]:
    from app.core.config import settings
    from app.services.deepseek_http import deepseek_chat_completions, deepseek_message_text

    numbered = "\n".join(f"{i}. {line}" for i, line in enumerate(lines, start=1))
    prompt = (
        "Dịch từng dòng sau sang tiếng Việt cho tư vấn bán hàng.\n"
        f"Trả về đúng {len(lines)} dòng, cùng thứ tự, mỗi dòng một bản dịch.\n"
        "Giữ nguyên số và đơn vị. Không gộp dòng, không tóm tắt, không giải thích.\n"
        f"{numbered}"
    )
    model = (getattr(settings, "DEEPSEEK_MODEL", None) or "deepseek-v4-flash").strip() or "deepseek-v4-flash"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": max(200, 80 * len(lines)),
        "thinking": {"type": "disabled"},
    }
    response = deepseek_chat_completions(payload, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(f"DeepSeek HTTP {response.status_code}")
    return _parse_translated_lines(deepseek_message_text(response), len(lines))


def _parse_translated_lines(raw: str, n: int) -> List[str]:
    rows = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
    cleaned = [re.sub(r"^\d+[\.\)、]\s*", "", ln).strip() for ln in rows]
    cleaned = [ln for ln in cleaned if ln]
    if len(cleaned) != n:
        raise RuntimeError(f"DeepSeek trả {len(cleaned)} dòng, cần {n}")
    return cleaned
