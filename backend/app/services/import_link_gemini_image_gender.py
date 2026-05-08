"""
Gemini (vision): suy giới tính (Nam/Nữ) từ ảnh đại diện listing khi text không có —
phục vụ import link (DeepSeek taxonomy có nhánh Nam/Nữ).

Model: settings.GEMINI_MODEL (mặc định gemini-2.5-flash).
"""
from __future__ import annotations

import base64
import json
import logging
import re
from typing import Optional, Tuple

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_MAX_IMAGE_BYTES = 4_500_000
_FETCH_TIMEOUT = 25
_API_TIMEOUT = 55


def _extract_json_object(content: str) -> Optional[dict]:
    t = (content or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```\w*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    try:
        data = json.loads(t)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", t)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def _fetch_image_inline(image_url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Trả (mime_type, base64_str, error)."""
    u = (image_url or "").strip()
    if not u:
        return None, None, "URL ảnh trống."
    try:
        r = requests.get(
            u,
            timeout=_FETCH_TIMEOUT,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; 188-import-taxonomy/1.0)",
                "Accept": "image/*,*/*;q=0.8",
            },
            stream=True,
        )
        r.raise_for_status()
        ct = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        buf = bytearray()
        for chunk in r.iter_content(chunk_size=65536):
            if not chunk:
                continue
            buf.extend(chunk)
            if len(buf) > _MAX_IMAGE_BYTES:
                return None, None, "Ảnh quá lớn sau khi tải."
        raw = bytes(buf)
        if not raw:
            return None, None, "Không đọc được dữ liệu ảnh."
        if ct not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            ct = "image/jpeg"
        b64 = base64.standard_b64encode(raw).decode("ascii")
        return ct, b64, None
    except requests.RequestException as exc:
        logger.warning("Gemini gender: tải ảnh lỗi: %s", exc)
        return None, None, f"Tải ảnh thất bại: {exc}"


def infer_gender_from_product_image_gemini(
    image_url: str,
    product_title: str = "",
) -> Tuple[Optional[str], Optional[str]]:
    """
    Trả ('female'|'male', None) nếu kết luận được; (None, error_detail) nếu không.

    Không trả unknown là giới — unknown/coerced và lỗi API đều là failure để caller ghi lỗi SP.
    """
    if not settings.IMPORT_LINK_GEMINI_IMAGE_GENDER_ENABLED:
        return None, "IMPORT_LINK_GEMINI_IMAGE_GENDER_ENABLED=tắt."

    api_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if not api_key or len(api_key) < 10:
        return None, "Thiếu GEMINI_API_KEY."

    model = (getattr(settings, "GEMINI_MODEL", "") or "gemini-2.5-flash").strip()

    mime, b64, err = _fetch_image_inline(image_url)
    if err or not mime or not b64:
        return None, err or "Không chuyển ảnh sang inline."

    title_line = (product_title or "").strip()[:500]
    prompt = (
        "Ảnh là ảnh đại diện (listing) sản phẩm TMĐT (giày dép, túi, quần áo…).\n"
        "Nhiệm vụ: Dựa **chủ yếu** vào ảnh (silhouette, kiểu mẫu, đối tượng đeo/mặc nếu có), "
        "kết luận sản phẩm **được nhắm tới Nam hay Nữ** cho danh mục thương mại.\n"
        "Không dùng markdown.\n"
        "Đầu ra **duy nhất** một JSON:\n"
        '{"gender_target":"male"} hoặc {"gender_target":"female"} '
        'hoặc {"gender_target":"unknown"} chỉ khi **không thể** kết luận từ ảnh.\n'
        f"Tên listing (tham khảo, không override ảnh rõ ràng): {title_line or '(không có)'}"
    )

    url = f"{GEMINI_BASE_URL}/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime, "data": b64}},
                ],
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 128,
            "temperature": 0.15,
        },
    }

    try:
        resp = requests.post(url, json=payload, timeout=_API_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            block = data.get("promptFeedback") or data.get("error") or {}
            return None, f"Gemini không trả candidates: {str(block)[:400]}"

        parts = (candidates[0].get("content") or {}).get("parts") or []
        text_out = ""
        for p in parts:
            if isinstance(p, dict) and p.get("text"):
                text_out += str(p["text"])
        text_out = text_out.strip()
        parsed = _extract_json_object(text_out)
        if not parsed:
            return None, "Gemini không trả JSON giới tính hợp lệ."

        raw_g = str(parsed.get("gender_target") or parsed.get("gender") or "").strip().lower()
        if raw_g in ("female", "f", "nu", "nữ", "women", "woman"):
            return "female", None
        if raw_g in ("male", "m", "nam", "men", "man"):
            return "male", None

        return None, f"Gemini không xác định được giới (gender_target={raw_g!r})."
    except requests.RequestException as exc:
        logger.warning("Gemini gender vision HTTP error: %s", exc)
        return None, f"Lỗi gọi Gemini: {exc}"
    except Exception as exc:
        logger.warning("Gemini gender vision error: %s", exc)
        return None, f"Lỗi xử lý Gemini: {exc}"
