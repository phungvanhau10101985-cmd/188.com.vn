"""
Dịch tên biến thể màu (JSON [{"name","img"}]) sang tiếng Việt qua DeepSeek khi có DEEPSEEK_API_KEY.

Bật dịch khi một trong các điều kiện:
  • Nguồn **Hibox** (`variants.source` / `import_source="hibox"`) — bắt buộc mọi luồng lấy SP qua hibox.mn;
  • EXCEL_VARIANT_COLORS_DEEPSEEK_TRANSLATE (import Excel);
  • IMPORT_LINK_DEEPSEEK_TAXONOMY_ENABLED (import link Vipomall/1688 khác).

Mặc định dịch khi tên có CJK/Kirin/Cyrillic; thêm nhãn Latin (vd. Black Suede, 15 Black Suede (91536)).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

# Trung / Nhật / Hàn + Kirin (tiếng Mông Cổ / một số ngôn ngữ trên Hibox)
_CJK_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")
_CYR_RE = re.compile(r"[\u0400-\u04FF]")

_CHUNK = 40
_TIMEOUT = 90

_VI_LATIN_RE = re.compile(
    r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđĐ]",
)
# Tránh dịch nhầm size thuần (S/M/L, 170 / L, …)
_SIZE_LIKE_RE = re.compile(
    r"^(xxl|xxxl|xxxxl|xs|xl|[sm])\s*$|^\d{2,3}\s*[-–/]\s*[a-z0-9]+\s*$",
    re.IGNORECASE,
)
# Nhãn màu/chất liệu tiếng Anh trên Hibox/1688 (vd. Black Suede, Champagne Gold).
_EN_FASHION_COLOR_RE = re.compile(
    r"(?i)\b(black|white|red|blue|green|gold|silver|champagne|beige|navy|pink|"
    r"grey|gray|brown|suede|leather|ivory|cream|rose|nude|khaki|burgundy|wine|"
    r"purple|orange|yellow|tan|camel|apricot|mint|olive)\b",
)


_HIBOX_SOURCES = frozenset({"hibox"})


def _product_import_source(product_data: Optional[Dict[str, Any]]) -> str:
    if not isinstance(product_data, dict):
        return ""
    pi = product_data.get("product_info")
    if isinstance(pi, dict):
        var = pi.get("variants")
        if isinstance(var, dict):
            src = str(var.get("source") or "").strip().lower()
            if src:
                return src
    return str(product_data.get("origin") or "").strip().lower()


def variant_color_translate_enabled(
    *,
    import_source: Optional[str] = None,
    product_data: Optional[Dict[str, Any]] = None,
) -> bool:
    """Có gọi API dịch tên màu hay không."""
    if not (settings.DEEPSEEK_API_KEY or "").strip():
        return False
    src = (import_source or _product_import_source(product_data) or "").strip().lower()
    if src in _HIBOX_SOURCES:
        return True
    if getattr(settings, "EXCEL_VARIANT_COLORS_DEEPSEEK_TRANSLATE", False):
        return True
    if getattr(settings, "IMPORT_LINK_DEEPSEEK_TAXONOMY_ENABLED", False):
        return True
    return False


def variant_color_deepseek_translate_effective() -> bool:
    """Alias tương thích Excel importer (không truyền product_data)."""
    return variant_color_translate_enabled()


def _looks_like_unlocalized_latin_label(s: str) -> bool:
    """Tên NCC kiểu Black / Navy / 15 Black Suede (91536) — Latin, chưa có dấu tiếng Việt."""
    t = (s or "").strip()
    if len(t) < 2 or len(t) > 120:
        return False
    if _CJK_RE.search(t) or _CYR_RE.search(t):
        return False
    if _VI_LATIN_RE.search(t):
        return False
    if _SIZE_LIKE_RE.match(t.strip()):
        return False
    if not re.search(r"[A-Za-z]", t):
        return False
    # Cho phép SKU trong ngoặc, %, dấu phẩy (banner/ghép size+màu trên Hibox).
    if not re.match(r"^[A-Za-z0-9\s\-–/\.(),\[\]%+]+$", t):
        return False
    return True


def _needs_translate(name: str) -> bool:
    s = (name or "").strip()
    if not s:
        return False
    if getattr(settings, "EXCEL_VARIANT_COLORS_DEEPSEEK_FORCE_ALL", False):
        return True
    if _CJK_RE.search(s) or _CYR_RE.search(s):
        return True
    if _looks_like_unlocalized_latin_label(s):
        return True
    if _EN_FASHION_COLOR_RE.search(s) and re.search(r"[A-Za-z]", s) and not _VI_LATIN_RE.search(s):
        return True
    return False


def _translate_unique_names(unique: List[str]) -> Dict[str, str]:
    if not unique or not (settings.DEEPSEEK_API_KEY or "").strip():
        return {}
    mapping: Dict[str, str] = {}
    for i in range(0, len(unique), _CHUNK):
        chunk = unique[i : i + _CHUNK]
        mapping.update(_deepseek_translate_names_batch(chunk))
    return mapping


def _rebuild_flat_color_column(colors: List[Any]) -> Optional[str]:
    parts: List[str] = []
    seen_l: set[str] = set()
    for item in colors:
        lab = ""
        if isinstance(item, dict):
            lab = str(item.get("name") or item.get("label") or "").strip()
        elif item is not None:
            lab = str(item).strip()
        if not lab:
            continue
        k = lab.lower()
        if k in seen_l:
            continue
        seen_l.add(k)
        parts.append(lab)
    return ", ".join(parts) if parts else None


def collect_variant_color_label_strings(product_data: Dict[str, Any]) -> List[str]:
    """Thu nhãn màu từ colors / pairs / swatches (giữ thứ tự, bỏ trùng không phân biệt hoa thường)."""
    out: List[str] = []
    seen_l: set[str] = set()

    def _push(raw: Any) -> None:
        n = str(raw or "").strip()
        if not n:
            return
        k = n.lower()
        if k in seen_l:
            return
        seen_l.add(k)
        out.append(n)

    for item in product_data.get("colors") or []:
        if isinstance(item, dict):
            _push(item.get("name") or item.get("label"))
        else:
            _push(item)
    pi = product_data.get("product_info")
    variants = pi.get("variants") if isinstance(pi, dict) else None
    if isinstance(variants, dict):
        for po in variants.get("pairs") or []:
            if isinstance(po, dict):
                _push(po.get("color"))
        for sw in variants.get("color_swatches") or []:
            if isinstance(sw, dict):
                _push(sw.get("label"))
    flat = str(product_data.get("color") or "").strip()
    if flat and "," in flat:
        for part in flat.split(","):
            _push(part.strip())
    elif flat:
        _push(flat)
    return out


def list_untranslated_variant_color_labels(product_data: Dict[str, Any]) -> List[str]:
    return [lab for lab in collect_variant_color_label_strings(product_data) if _needs_translate(lab)]


def apply_variant_color_translation_to_product_data(
    product_data: Dict[str, Any],
    *,
    import_source: Optional[str] = None,
) -> int:
    """
    Dịch mọi nhãn màu trong product_data (colors, pairs, swatches) và đồng bộ cột `color` + variants.colors.
    Trả số nhãn đã ghi đè. Dùng sau scrape Hibox (import_source='hibox') và trước taxonomy.
    """
    if not product_data:
        return 0
    if not variant_color_translate_enabled(import_source=import_source, product_data=product_data):
        return 0

    unique: List[str] = []
    seen: set[str] = set()

    def _push(raw: Any) -> None:
        n = str(raw or "").strip()
        if not n or not _needs_translate(n) or n in seen:
            return
        seen.add(n)
        unique.append(n)

    for item in product_data.get("colors") or []:
        if isinstance(item, dict):
            _push(item.get("name") or item.get("label"))
        else:
            _push(item)

    pi = product_data.get("product_info")
    variants = pi.get("variants") if isinstance(pi, dict) else None
    if isinstance(variants, dict):
        for po in variants.get("pairs") or []:
            if isinstance(po, dict):
                _push(po.get("color"))
        for sw in variants.get("color_swatches") or []:
            if isinstance(sw, dict):
                _push(sw.get("label"))

    mapping = _translate_unique_names(unique)
    if not mapping:
        return 0

    n_applied = 0
    for item in product_data.get("colors") or []:
        if not isinstance(item, dict):
            continue
        n = str(item.get("name") or item.get("label") or "").strip()
        if n in mapping:
            vn = mapping[n]
            item["name"] = vn
            item.pop("label", None)
            n_applied += 1

    if isinstance(pi, dict) and isinstance(variants, dict):
        for po in variants.get("pairs") or []:
            if not isinstance(po, dict):
                continue
            cr = str(po.get("color") or "").strip()
            if cr in mapping:
                po["color"] = mapping[cr]
                n_applied += 1
        for sw in variants.get("color_swatches") or []:
            if not isinstance(sw, dict):
                continue
            lab = str(sw.get("label") or "").strip()
            if lab in mapping:
                sw["label"] = mapping[lab]
                n_applied += 1
        flat = _rebuild_flat_color_column(product_data.get("colors") or [])
        if flat:
            variants["colors"] = flat
            cj = flat.strip()
            if len(cj) > 500:
                cj = cj[:500].strip()
            product_data["color"] = cj

    logger.info(
        "DeepSeek Variant (product_data): đã dịch %s nhãn màu (từ %s chuỗi duy nhất)",
        n_applied,
        len(unique),
    )
    return n_applied


def apply_hibox_variant_color_translation(product_data: Dict[str, Any]) -> List[str]:
    """
    Bắt buộc cho mọi luồng scrape Hibox (hibox.mn / mirror taobao1688.kz).
    Trả cảnh báo nếu thiếu API key hoặc còn nhãn chưa Việt hóa.
    """
    warnings: List[str] = []
    if not (settings.DEEPSEEK_API_KEY or "").strip():
        warnings.append(
            "Hibox: thiếu DEEPSEEK_API_KEY — không dịch được phiên bản màu sang tiếng Việt."
        )
        return warnings
    try:
        n = apply_variant_color_translation_to_product_data(product_data, import_source="hibox")
        if n == 0:
            pending = list_untranslated_variant_color_labels(product_data)
            if pending:
                warnings.append(
                    "Hibox: DeepSeek không dịch được nhãn màu (kiểm tra API/log). "
                    f"Ví dụ còn: {pending[0][:80]}"
                )
    except Exception as exc:
        logger.warning("Hibox variant color translate: %s", exc)
        warnings.append(f"Hibox: lỗi dịch màu — {type(exc).__name__}: {exc}")
    return warnings


def _collect_unique_names(products: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for p in products:
        colors = p.get("colors") or []
        if not isinstance(colors, list):
            continue
        for item in colors:
            if not isinstance(item, dict):
                continue
            n = str(item.get("name", "")).strip()
            if not n or not _needs_translate(n):
                continue
            if n not in seen:
                seen.add(n)
                out.append(n)
    return out


def _parse_model_json_array(raw: str) -> List[str]:
    t = (raw or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```\w*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\[[\s\S]*\]", t)
        if not m:
            raise ValueError("Không tìm được mảng JSON trong phản hồi DeepSeek")
        data = json.loads(m.group(0))
    if not isinstance(data, list):
        raise ValueError("DeepSeek không trả về mảng")
    return [str(x).strip() if x is not None else "" for x in data]


def _deepseek_translate_names_batch(names: List[str]) -> Dict[str, str]:
    key = (settings.DEEPSEEK_API_KEY or "").strip()
    if not key or not names:
        return {}
    url = (settings.DEEPSEEK_API_URL or "").strip() or "https://api.deepseek.com/v1/chat/completions"
    model = (settings.DEEPSEEK_MODEL or "").strip() or "deepseek-chat"

    payload_in = json.dumps(names, ensure_ascii=False)
    system = (
        "Bạn dịch tên biến thể màu/kiểu (thương mại điện tử) sang tiếng Việt ngắn gọn, "
        "giữ thứ tự mảng. Nếu có số size hoặc mã SKU trong ngoặc (vd. «15 Black Suede (91536)»), "
        "giữ nguyên số và mã, chỉ dịch phần tên màu/chất liệu. "
        "Chỉ trả về JSON mảng chuỗi cùng độ dài với đầu vào, không markdown, không giải thích."
    )
    user = (
        f"Đầu vào (JSON array, {len(names)} phần tử): {payload_in}\n\n"
        f"Trả về đúng một JSON array có {len(names)} chuỗi tiếng Việt tương ứng."
    )

    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("DeepSeek variant translate: lỗi mạng: %s", exc)
        return {}

    if not resp.ok:
        logger.warning("DeepSeek variant translate: HTTP %s %s", resp.status_code, resp.text[:500])
        return {}

    try:
        body = resp.json()
        content = (body.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    except (json.JSONDecodeError, TypeError, IndexError) as exc:
        logger.warning("DeepSeek variant translate: parse JSON phản hồi lỗi: %s", exc)
        return {}

    try:
        translated = _parse_model_json_array(content)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("DeepSeek variant translate: không đọc được mảng từ model: %s | %s", exc, content[:400])
        return {}

    if len(translated) != len(names):
        logger.warning(
            "DeepSeek variant translate: độ dài lệch (%s vs %s), bỏ qua lô",
            len(translated),
            len(names),
        )
        return {}

    return {src: dst for src, dst in zip(names, translated) if dst}


def apply_deepseek_translations_to_variant_colors(products: List[Dict[str, Any]]) -> None:
    """
    In-place: thay `name` trong mỗi phần tử `colors` khi có bản dịch.
    """
    if not products:
        return
    if not variant_color_translate_enabled():
        return
    if not (settings.DEEPSEEK_API_KEY or "").strip():
        logger.info("Dịch Variant: thiếu DEEPSEEK_API_KEY — bỏ qua")
        return

    unique = _collect_unique_names(products)
    mapping = _translate_unique_names(unique)
    if not mapping:
        return

    n_applied = 0
    for p in products:
        colors = p.get("colors") or []
        if not isinstance(colors, list):
            continue
        for item in colors:
            if not isinstance(item, dict):
                continue
            n = str(item.get("name", "")).strip()
            if n in mapping:
                vn = mapping[n]
                item["name"] = vn
                item.pop("label", None)
                n_applied += 1

    logger.info("DeepSeek Variant: đã dịch %s nhãn màu (từ %s chuỗi duy nhất)", n_applied, len(unique))


def apply_deepseek_translations_to_color_entries(entries: List[Dict[str, Any]]) -> None:
    """Dịch `name` trong list dict màu (vd. Hibox `colors_out`); không dùng trường `label` trùng lặp."""
    if not entries:
        return
    if not variant_color_translate_enabled():
        return
    if not (settings.DEEPSEEK_API_KEY or "").strip():
        return
    unique: List[str] = []
    seen: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            continue
        n = str(item.get("name", "")).strip()
        if not n or not _needs_translate(n):
            continue
        if n not in seen:
            seen.add(n)
            unique.append(n)
    mapping = _translate_unique_names(unique)
    if not mapping:
        return
    n_applied = 0
    for item in entries:
        if not isinstance(item, dict):
            continue
        n = str(item.get("name", "")).strip()
        if n in mapping:
            vn = mapping[n]
            item["name"] = vn
            item.pop("label", None)
            n_applied += 1
    logger.info("DeepSeek Variant (color entries): đã dịch %s mục", n_applied)
