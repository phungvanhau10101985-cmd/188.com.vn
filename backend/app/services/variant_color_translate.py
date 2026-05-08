"""
Dịch tên biến thể màu (JSON [{"name","img"}]) sang tiếng Việt qua DeepSeek khi có DEEPSEEK_API_KEY và:
  • EXCEL_VARIANT_COLORS_DEEPSEEK_TRANSLATE (import Excel), hoặc
  • IMPORT_LINK_DEEPSEEK_TAXONOMY_ENABLED (import link 1688/Hibox — đồng bộ tên màu với tên SP VI).

Mặc định dịch khi tên có CJK/Kirin/Cyrillic; thêm nhãn Latin thuần (vd. Black, Red) khi chưa có dấu tiếng Việt.
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
    r"(?i)^(xxl|xxxl|xxxxl|xs|xl|[sm])\s*$|^\d{2,3}\s*[-–/]\s*[a-z0-9]+\s*$",
)


def variant_color_deepseek_translate_effective() -> bool:
    """Có gọi API dịch tên màu hay không (Excel và/hoặc import link)."""
    if not (settings.DEEPSEEK_API_KEY or "").strip():
        return False
    if getattr(settings, "EXCEL_VARIANT_COLORS_DEEPSEEK_TRANSLATE", False):
        return True
    if getattr(settings, "IMPORT_LINK_DEEPSEEK_TAXONOMY_ENABLED", False):
        return True
    return False


def _looks_like_unlocalized_latin_label(s: str) -> bool:
    """Tên NCC kiểu Black / Navy — Latin, chưa có dấu tiếng Việt."""
    t = (s or "").strip()
    if len(t) < 2 or len(t) > 56:
        return False
    if _CJK_RE.search(t) or _CYR_RE.search(t):
        return False
    if _VI_LATIN_RE.search(t):
        return False
    if _SIZE_LIKE_RE.match(t.strip()):
        return False
    if not re.search(r"[A-Za-z]", t):
        return False
    if not re.match(r"^[A-Za-z0-9\s\-–/\.]+$", t):
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
    return _looks_like_unlocalized_latin_label(s)


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
        "giữ thứ tự mảng. Chỉ trả về JSON mảng chuỗi cùng độ dài với đầu vào, không markdown, không giải thích."
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
    if not variant_color_deepseek_translate_effective():
        return
    if not (settings.DEEPSEEK_API_KEY or "").strip():
        logger.info("Dịch Variant: thiếu DEEPSEEK_API_KEY — bỏ qua")
        return

    unique = _collect_unique_names(products)
    if not unique:
        return

    mapping: Dict[str, str] = {}
    for i in range(0, len(unique), _CHUNK):
        chunk = unique[i : i + _CHUNK]
        part = _deepseek_translate_names_batch(chunk)
        mapping.update(part)

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
    if not variant_color_deepseek_translate_effective():
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
    if not unique:
        return
    mapping: Dict[str, str] = {}
    for i in range(0, len(unique), _CHUNK):
        chunk = unique[i : i + _CHUNK]
        mapping.update(_deepseek_translate_names_batch(chunk))
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
