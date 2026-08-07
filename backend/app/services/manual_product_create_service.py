"""Đăng sản phẩm thủ công / AI: DeepSeek text + Gemini ảnh + tạo Product + Ladipage 1 SP."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud import product as product_crud
from app.db.session import SessionLocal
from app.schemas.product import ProductCreate
from app.services import bunny_storage
from app.services.import_link_deepseek_taxonomy import (
    apply_deepseek_taxonomy_to_product_data,
    translate_product_listing_deepseek_only,
)
from app.services.image_localization_service import (
    _extract_first_image_bytes_from_gemini_generate_response,
    _normalize_gemini_image_size,
    _sanitize_model_id,
)
from app.services.ladipage_ai_service import _guess_mime_from_url
from app.services.ladipage_bootstrap import (
    bootstrap_single_product_ladipage,
    fill_ladipage_ai_content,
    publish_ladipage,
)
from app.services.manual_product_create_job_store import load_job, persist_job

logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

_WORKER_LOCK = threading.RLock()
_ACTIVE_THREADS: Dict[str, threading.Thread] = {}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_update(job_id: str, **kwargs: Any) -> Dict[str, Any]:
    with _WORKER_LOCK:
        state = load_job(job_id) or {"job_id": job_id}
        state.update(kwargs)
        state["updated_at"] = _utcnow_iso()
        persist_job(job_id, state)
        return state


def _job_step(job_id: str, step: str, message: str, *, progress: Optional[int] = None) -> None:
    payload: Dict[str, Any] = {
        "step": step,
        "message": message,
        "status": "running",
    }
    if progress is not None:
        payload["progress"] = max(0, min(100, int(progress)))
    _job_update(job_id, **payload)


def new_manual_product_id() -> str:
    """Prefix M — tách khỏi import 1688/Hibox (A/T/hibox)."""
    stamp = datetime.now(timezone.utc).strftime("%y%m%d%H%M%S")
    suffix = uuid.uuid4().hex[:6].upper()
    return f"M{stamp}{suffix}"


def _gender_hint(gender: str) -> Optional[str]:
    g = (gender or "").strip().lower()
    if g in ("nam", "male", "men", "man"):
        return "male"
    if g in ("nữ", "nu", "female", "women", "woman"):
        return "female"
    return None


def _parse_sizes(raw: Any, *, no_size: bool) -> List[str]:
    if no_size:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    text = str(raw or "").strip()
    if not text or text.lower() in ("không", "khong", "no", "none", "-"):
        return []
    parts = re.split(r"[,;/|]+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def _parse_color_items(raw: Any) -> List[Dict[str, str]]:
    """Chuẩn hóa colors → [{name, img}] (img có thể rỗng)."""
    out: List[Dict[str, str]] = []
    if raw is None:
        return out
    if isinstance(raw, str):
        for p in re.split(r"[,;/|]+|\n+", raw):
            name = p.strip()
            if name:
                out.append({"name": name, "img": ""})
        return out
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, str):
            name = item.strip()
            if name:
                out.append({"name": name, "img": ""})
            continue
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("label") or "").strip()
            img = str(
                item.get("img")
                or item.get("image")
                or item.get("image_url")
                or item.get("url")
                or ""
            ).strip()
            if name:
                out.append({"name": name, "img": img})
    return out


def _parse_colors(raw: Any) -> List[str]:
    """Chỉ lấy danh sách tên màu (dùng cho AI generate / brief)."""
    return [c["name"] for c in _parse_color_items(raw) if c.get("name")]


def _build_brief_blob(payload: Dict[str, Any]) -> str:
    sizes = _parse_sizes(payload.get("sizes"), no_size=bool(payload.get("no_size")))
    colors = _parse_colors(payload.get("colors"))
    gender = (payload.get("gender") or "").strip() or "không rõ"
    gender_line = f"Giới tính: {gender}"
    ghint = _gender_hint(gender)
    if ghint == "female":
        gender_line += " — dành cho nữ"
    elif ghint == "male":
        gender_line += " — dành cho nam"
    pname = (payload.get("product_name") or payload.get("name") or "").strip()
    lines = [
        f"Tên sản phẩm (admin): {pname or 'chưa đặt — AI đặt tên'}",
        gender_line,
        f"Chất liệu: {(payload.get('material') or '').strip() or 'chưa nêu'}",
        f"Phong cách / mẫu: {(payload.get('style') or '').strip() or 'chưa nêu'}",
        f"Size: {', '.join(sizes) if sizes else 'không có size'}",
        f"Màu: {', '.join(colors) if colors else 'chưa nêu'}",
        f"Giá bán (VND): {payload.get('price')}",
    ]
    notes = (payload.get("notes") or "").strip()
    if notes:
        lines.append(f"Ghi chú admin: {notes}")
    return "\n".join(lines)


def _upload_product_image_bytes(image_bytes: bytes, *, name_hint: str, product_key: str) -> str:
    zone = (settings.BUNNY_STORAGE_ZONE_NAME or "").strip()
    key = (settings.BUNNY_STORAGE_ACCESS_KEY or "").strip()
    cdn = (settings.BUNNY_CDN_PUBLIC_BASE or "").strip()
    if not zone or not key or not cdn:
        raise RuntimeError("Thiếu cấu hình Bunny CDN (zone / access key / public base).")
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", name_hint).strip("-") or "img"
    digest = hashlib.sha1(image_bytes).hexdigest()[:10]
    remote_name = f"{safe}-{int(time.time())}-{digest}.jpg"
    prefix = (settings.BUNNY_UPLOAD_PATH_PREFIX or "site").strip("/")
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    remote_path = f"{prefix}/manual-products/{product_key}/{day}/{remote_name}"
    bunny_storage.upload_file_to_zone(
        zone_name=zone,
        access_key=key,
        remote_path=remote_path,
        data=image_bytes,
        content_type="image/jpeg",
    )
    url = bunny_storage.build_public_object_url(cdn, remote_path)
    if not url:
        raise RuntimeError("Không tạo được URL public Bunny.")
    return url


def _resolve_manual_ai_image_model(choice: Optional[str]) -> Tuple[str, Optional[str], str]:
    """
    Map lựa chọn UI → (model_id, image_size|None, label).
    None size = không gửi imageConfig (Flash 2.5 mặc định ~1K).
    """
    key = (choice or "").strip().lower().replace("_", "-")
    if key in ("flash", "flash-2.5", "gemini-2.5-flash-image", "nano-banana"):
        return "gemini-2.5-flash-image", None, "Flash (~1K, rẻ)"
    if key in ("flash3", "flash-3", "flash-3.1", "gemini-3.1-flash-image", "nano-banana-2"):
        return "gemini-3.1-flash-image", "2K", "Flash 3.1 (2K)"
    # Mặc định / pro
    default = (
        getattr(settings, "IMAGE_LOCALIZATION_GEMINI_IMAGE_MODEL", "") or "gemini-3-pro-image-preview"
    ).strip() or "gemini-3-pro-image-preview"
    if key in ("", "pro", "pro-2k", "gemini-3-pro-image", "gemini-3-pro-image-preview", "nano-banana-pro"):
        size = (
            getattr(settings, "IMAGE_LOCALIZATION_GEMINI_API_DEFAULT_IMAGE_SIZE", "2K") or "2K"
        ).strip().upper() or "2K"
        if size not in ("2K", "4K"):
            size = "2K"
        return _sanitize_model_id(default, "gemini-3-pro-image-preview"), size, "Pro (2K, chất lượng cao)"
    # Cho phép truyền thẳng model id
    if "flash-image" in key and "pro" not in key:
        if "3.1" in key:
            return _sanitize_model_id(key, "gemini-3.1-flash-image"), "2K", key
        return _sanitize_model_id(key, "gemini-2.5-flash-image"), None, key
    return _sanitize_model_id(key or default, "gemini-3-pro-image-preview"), "2K", key or "pro"


def _gemini_edit_from_urls(
    image_urls: List[str],
    prompt: str,
    *,
    image_model: Optional[str] = None,
    image_size: Optional[str] = "",
    timeout_sec: Optional[int] = None,
) -> bytes:
    """Gemini image-edit với 1..N ảnh tham chiếu (inline_data)."""
    api_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if len(api_key) < 10:
        raise RuntimeError("Thiếu GEMINI_API_KEY.")
    urls = [u.strip() for u in image_urls if (u or "").strip()]
    if not urls:
        raise RuntimeError("Thiếu ảnh tham chiếu cho Gemini.")

    parts: List[Dict[str, Any]] = [{"text": prompt.strip()}]
    for u in urls[:3]:
        img_resp = requests.get(u, timeout=30)
        img_resp.raise_for_status()
        mime = _guess_mime_from_url(u, img_resp.headers.get("Content-Type"))
        b64 = base64.b64encode(img_resp.content).decode("ascii")
        parts.append({"inline_data": {"mime_type": mime, "data": b64}})

    dm = (
        (
            image_model
            or getattr(settings, "IMAGE_LOCALIZATION_GEMINI_IMAGE_MODEL", "")
            or "gemini-3-pro-image-preview"
        ).strip()
        or "gemini-3-pro-image-preview"
    )
    model = _sanitize_model_id(dm, "gemini-3-pro-image-preview")
    # image_size:
    #   None  → không gửi imageConfig (Flash 2.5)
    #   ""    → mặc định settings (2K)
    #   "2K"/"4K" → dùng giá trị đó
    if image_size is None:
        eff_size: Optional[str] = None
    else:
        raw_size = str(image_size).strip() or getattr(
            settings, "IMAGE_LOCALIZATION_GEMINI_API_DEFAULT_IMAGE_SIZE", "2K"
        )
        eff_size = _normalize_gemini_image_size(raw_size) or "2K"
        if "2.5-flash-image" in model:
            eff_size = None
    tout = (
        timeout_sec
        if timeout_sec is not None
        else max(60, int(getattr(settings, "IMAGE_LOCALIZATION_GEMINI_API_TIMEOUT_SEC", 300) or 300))
    )

    gen_cfg: Dict[str, Any] = {"responseModalities": ["TEXT", "IMAGE"]}
    if eff_size:
        gen_cfg["imageConfig"] = {"imageSize": eff_size}

    payload: Dict[str, Any] = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": gen_cfg,
    }
    url = f"{GEMINI_BASE_URL}/models/{model}:generateContent"
    verify = bool(getattr(settings, "GEMINI_SSL_VERIFY", True))
    try:
        res = requests.post(url, params={"key": api_key}, json=payload, timeout=tout, verify=verify)
    except requests.exceptions.SSLError:
        if not verify:
            raise
        logger.warning("Gemini image SSL verify failed — retry verify=False.")
        try:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
        res = requests.post(url, params={"key": api_key}, json=payload, timeout=tout, verify=False)
    if res.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {res.status_code}: {(res.text or '')[:400]}")
    body = res.json()
    fb = body.get("promptFeedback") or {}
    br = fb.get("blockReason") or fb.get("block_reason")
    if br:
        raise RuntimeError(f"Gemini từ chối prompt: {br}")
    out = _extract_first_image_bytes_from_gemini_generate_response(body)
    if not out:
        raise RuntimeError("Gemini không trả ảnh.")
    return out


def _style_label(style: str) -> str:
    s = (style or "").strip().lower()
    if "âu" in s or "eu" in s or "europe" in s:
        return "mẫu châu Âu"
    if "á" in s or "asia" in s or "asian" in s:
        return "mẫu châu Á"
    return (style or "").strip() or "phong cách hiện đại"


def _resolve_model_presence(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s in ("model", "with_model", "nguoi_mau", "có người mẫu", "co nguoi mau", "yes", "1", "true"):
        return "model"
    return "none"


def _resolve_model_gender(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s in ("nam", "male", "man", "men", "boy", "trai"):
        return "male"
    if s in ("nu", "nữ", "female", "woman", "women", "girl", "gai", "gái"):
        return "female"
    return "female"


def _resolve_model_age_group(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s in ("em_be", "baby", "infant", "toddler", "so_sinh"):
        return "baby"
    if s in ("tre_em", "child", "kid", "children"):
        return "child"
    if s in ("thieu_nien", "teen", "teenager"):
        return "teen"
    if s in ("trung_nien", "middle_aged", "senior"):
        return "middle_aged"
    return "adult"


def _resolve_model_ethnicity(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s in ("asian", "chau_a", "châu á", "chau a"):
        return "asian"
    if s in ("western", "european", "chau_au", "châu âu", "chau au", "au my", "âu mỹ"):
        return "western"
    return ""  # không yêu cầu cụ thể


_MODEL_AGE_LABELS = {
    "baby": "infant/toddler model (0–3 years old)",
    "child": "child model (4–12 years old)",
    "teen": "teenage model (13–17 years old)",
    "adult": "adult model (18–35 years old)",
    "middle_aged": "middle-aged adult model (35–55 years old)",
}

_MODEL_ETHNICITY_LABELS = {
    "asian": "Asian",
    "western": "Western/European",
}


def _indefinite_article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def _resolve_shot_style(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s in ("lifestyle", "noi_that", "indoor", "trong nhà", "trong nha"):
        return "lifestyle"
    if s in ("outdoor", "phong_canh", "scenery", "landscape", "ngoài trời", "ngoai troi"):
        return "outdoor"
    return "studio"


def _commercial_look_brief(
    *,
    model_presence: str,
    shot_style: str,
    gender_txt: str,
    model_gender: str = "female",
    model_age_group: str = "adult",
    model_ethnicity: str = "",
) -> str:
    """Mô tả phong cách chụp bán hàng chuyên nghiệp cho prompt Gemini."""
    if shot_style == "outdoor":
        scene = (
            "Outdoor commercial fashion photography: soft natural daylight, shallow depth of field, "
            "tasteful real-world background (park / street / cafe patio) that stays blurry and does not distract. "
            "Premium look suitable for Shopee/Lazada hero images."
        )
    elif shot_style == "lifestyle":
        scene = (
            "Indoor lifestyle commercial set: bright airy room, soft window light, minimal styled props, "
            "clean composition, premium catalog feel."
        )
    else:
        scene = (
            "Professional studio e-commerce packshot: seamless light-gray or soft white cyclorama, "
            "softbox key + fill, subtle floor shadow, crisp edges, high-end catalog lighting."
        )

    if model_presence == "model":
        age_desc = _MODEL_AGE_LABELS.get(model_age_group, _MODEL_AGE_LABELS["adult"])
        ethnicity_desc = _MODEL_ETHNICITY_LABELS.get(model_ethnicity, "")
        ethnicity_prefix = f"{ethnicity_desc} " if ethnicity_desc else ""
        if model_age_group in ("baby", "child"):
            sex_word = "girl" if model_gender == "female" else "boy"
            article = _indefinite_article(ethnicity_desc or age_desc)
            talent = (
                f"Include {article} {ethnicity_prefix}{age_desc} ({sex_word}) "
                "wearing/using the exact product naturally; "
                "age-appropriate, friendly expression, flattering pose that sells the outfit. "
                "No adult model in this shot."
            )
        else:
            sex_word = "female" if model_gender == "female" else "male"
            article = _indefinite_article(ethnicity_desc or sex_word)
            talent = (
                f"Include {article} {ethnicity_prefix}{sex_word} fashion model "
                f"— {age_desc} — wearing/holding the exact product; "
                "confident commercial pose, flattering angles that sell."
            )
        subject = f"{talent} Keep the product as the hero — face not overpowering the garment."
    else:
        subject = (
            "NO human model, NO mannequin, NO hands. Product-only hero composition, "
            "centered, full product visible, premium flat/ghost-mannequin or hanging presentation as fits the item."
        )

    return (
        f"{scene} {subject} "
        "Photorealistic commercial fashion photography, sharp focus on product, true colors, "
        "no watermark, no price tag, no extra logos, no invented text overlays, no low-quality phone snapshot look."
    )


_GALLERY_ANGLES = [
    "3/4 angled hero that shows depth and shape",
    "clean side / profile commercial angle",
    "alternate lifestyle or styled commercial angle that still keeps product readable",
    "slightly closer mid-shot emphasizing design details while full product remains clear",
]
_DETAIL_FOCUS = [
    "close-up of fabric/material texture with premium lighting",
    "detail of print, stitching, zipper, neckline or construction that sells quality",
    "macro of distinctive design element while remaining photorealistic",
]
_FIDELITY = (
    "CRITICAL: Keep the EXACT same product from the reference photos "
    "(silhouette, print, logo placement, proportions, fabric look). Do not redesign or invent a different item. "
)


def _normalize_color_name_list(raw: Any) -> List[str]:
    names: List[str] = []
    seen = set()
    if isinstance(raw, str):
        items = re.split(r"[,;/|]+|\n+", raw)
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    for item in items:
        if isinstance(item, dict):
            cn = str(item.get("name") or item.get("label") or "").strip()
        else:
            cn = str(item or "").strip()
        if not cn:
            continue
        key = cn.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(cn[:40])
        if len(names) >= 12:
            break
    return names


def _ref_pool_from_payload(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    pool: List[Dict[str, str]] = []
    refs = [str(u).strip() for u in (payload.get("ref_image_urls") or []) if str(u).strip()][:3]
    for i, u in enumerate(refs):
        pool.append(
            {
                "id": f"orig-{i}",
                "url": u,
                "label": f"Ảnh gốc {i + 1}",
                "kind": "ref",
            }
        )
    return pool


def _init_studio(payload: Dict[str, Any], *, product_key: str) -> Dict[str, Any]:
    g_count = max(0, min(12, int(payload.get("gallery_count") if payload.get("gallery_count") is not None else 5)))
    d_count = max(0, min(12, int(payload.get("detail_count") if payload.get("detail_count") is not None else 3)))
    return {
        "product_key": product_key,
        "plan": {
            "gallery_count": g_count,
            "detail_count": d_count,
            "model_presence": _resolve_model_presence(payload.get("model_presence")),
            "model_gender": _resolve_model_gender(payload.get("model_gender")),
            "model_age_group": _resolve_model_age_group(payload.get("model_age_group")),
            "model_ethnicity": _resolve_model_ethnicity(payload.get("model_ethnicity")),
            "shot_style": _resolve_shot_style(payload.get("shot_style")),
            "image_model": str(
                payload.get("image_model") or payload.get("ai_image_model") or "pro"
            ).strip()
            or "pro",
        },
        "ref_pool": _ref_pool_from_payload(payload),
        "phase": "color",
        "suggested_prompt": "",
        "color_names": [],
        "colors": [],
        "main_image": "",
        "images": [],
        "gallery": [],
        "current_slot": None,
        "can_publish": False,
        "next_actions": ["color"],
    }


def _studio_can_publish(studio: Dict[str, Any]) -> bool:
    if (studio.get("main_image") or "").strip():
        return True
    for row in studio.get("colors") or []:
        if isinstance(row, dict) and (row.get("img") or "").strip():
            return True
    return False


def _studio_approved_color_urls(studio: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for row in studio.get("colors") or []:
        if not isinstance(row, dict):
            continue
        u = (row.get("img") or "").strip()
        if u:
            out.append(u)
    return out


def _add_to_ref_pool(studio: Dict[str, Any], *, url: str, label: str, kind: str, pool_id: str) -> None:
    url = (url or "").strip()
    if not url:
        return
    pool = list(studio.get("ref_pool") or [])
    for item in pool:
        if isinstance(item, dict) and (item.get("url") or "").strip() == url:
            return
    pool.append({"id": pool_id, "url": url, "label": label[:80], "kind": kind})
    studio["ref_pool"] = pool


def _resolve_selected_refs(
    studio: Dict[str, Any],
    *,
    ref_urls: Optional[List[str]] = None,
    attach_url: Optional[str] = None,
) -> List[str]:
    """Ưu tiên attach + ref_urls khách chọn (tối đa 3)."""
    ordered: List[str] = []
    attach = (attach_url or "").strip()
    if attach:
        ordered.append(attach)
    for u in ref_urls or []:
        s = str(u or "").strip()
        if s and s not in ordered:
            ordered.append(s)
        if len(ordered) >= 3:
            break
    if ordered:
        return ordered[:3]
    # fallback: ảnh gốc trong pool
    for item in studio.get("ref_pool") or []:
        if not isinstance(item, dict):
            continue
        if (item.get("kind") or "") != "ref":
            continue
        u = (item.get("url") or "").strip()
        if u and u not in ordered:
            ordered.append(u)
        if len(ordered) >= 3:
            break
    return ordered[:3]


def _slot_label(slot: Dict[str, Any]) -> str:
    kind = (slot.get("kind") or "").strip()
    idx = int(slot.get("index") or 0)
    name = (slot.get("name") or "").strip()
    if kind == "color":
        return f"ảnh màu «{name or idx + 1}»"
    if kind == "main":
        return "ảnh chính"
    if kind == "gallery":
        return f"ảnh gallery {idx + 1}"
    if kind == "detail":
        return f"ảnh chi tiết {idx + 1}"
    return "ảnh"


def _build_studio_slot_prompt(
    state: Dict[str, Any],
    slot: Dict[str, Any],
) -> str:
    payload = dict(state.get("payload") or {})
    studio = dict(state.get("studio") or {})
    plan = dict(studio.get("plan") or {})
    gender_txt = (payload.get("gender") or "").strip() or "unisex"
    material_txt = (payload.get("material") or "").strip() or "chất liệu theo ảnh"
    style_txt = _style_label(str(payload.get("style") or ""))
    presence = _resolve_model_presence(plan.get("model_presence") or payload.get("model_presence"))
    scene = _resolve_shot_style(plan.get("shot_style") or payload.get("shot_style"))
    model_gender = _resolve_model_gender(plan.get("model_gender") or payload.get("model_gender"))
    model_age_group = _resolve_model_age_group(plan.get("model_age_group") or payload.get("model_age_group"))
    model_ethnicity = _resolve_model_ethnicity(
        plan.get("model_ethnicity") or payload.get("model_ethnicity")
    )
    look = _commercial_look_brief(
        model_presence=presence,
        shot_style=scene,
        gender_txt=gender_txt,
        model_gender=model_gender,
        model_age_group=model_age_group,
        model_ethnicity=model_ethnicity,
    )
    kind = (slot.get("kind") or "").strip()
    idx = int(slot.get("index") or 0)
    # Ghi chú thêm của admin — CHỈ cộng thêm vào prompt gốc, không bao giờ thay thế toàn bộ.
    # (Prompt chính do hệ thống tự dựng, ẩn với người dùng — tránh gửi nhầm placeholder/prompt hỏng lên AI.)
    notes = (slot.get("user_prompt") or "").strip()
    if "«màu chính»" in notes:
        notes = ""  # tương thích ngược: bỏ placeholder cũ nếu còn sót từ phiên bản trước

    if kind == "color":
        cname = (slot.get("name") or "").strip() or "màu chính"
        base = (
            "Create a premium e-commerce colorway photo of the SAME product, recolored to this exact colorway: "
            f"«{cname}». Keep identical shape, print layout, and construction; only change the garment color as specified. "
            f"{_FIDELITY}"
            f"Shopper: {gender_txt}. {look}"
        )
    elif kind == "main":
        base = (
            "Create a premium e-commerce HERO product photo that customers want to buy. "
            f"{_FIDELITY}"
            f"Shopper: {gender_txt}. Material feel: {material_txt}. Fashion style: {style_txt}. "
            f"{look} "
            "Square-friendly composition, product fills frame confidently, retail-ready quality."
        )
    elif kind == "gallery":
        angle = _GALLERY_ANGLES[idx % len(_GALLERY_ANGLES)]
        base = (
            "Create another premium commercial catalog photo of the SAME product. "
            f"{_FIDELITY}"
            f"Camera/composition: {angle}. "
            f"Shopper: {gender_txt}. Style: {style_txt}. Material: {material_txt}. "
            f"{look}"
        )
    else:
        focus = _DETAIL_FOCUS[idx % len(_DETAIL_FOCUS)]
        base = (
            "Create a premium PRODUCT DETAIL photo for an online fashion store. "
            f"Focus: {focus}. Same exact product as references and hero. "
            f"Material: {material_txt}. Style: {style_txt}. "
            "Sharp commercial lighting, no text, no watermark, photorealistic."
        )

    if notes:
        base = f"{base}\nMô tả/ghi chú thêm từ admin: {notes}"
    return base


def _suggested_prompt_for_phase(state: Dict[str, Any], *, kind: str, name: str = "", index: int = 0) -> str:
    slot = {"kind": kind, "name": name, "index": index, "user_prompt": ""}
    return _build_studio_slot_prompt(state, slot)


def _compute_next_actions(studio: Dict[str, Any]) -> List[str]:
    actions: List[str] = ["color"]
    if _studio_approved_color_urls(studio) or (studio.get("main_image") or "").strip():
        actions.append("main")
        actions.append("gallery")
        actions.append("detail")
    if _studio_can_publish(studio):
        actions.append("publish")
    return actions


def _refresh_studio_hints(state: Dict[str, Any], studio: Dict[str, Any]) -> None:
    phase = (studio.get("phase") or "color").strip() or "color"
    name = ""
    idx = 0
    if phase == "color":
        idx = len([c for c in (studio.get("colors") or []) if isinstance(c, dict) and c.get("img")])
    elif phase == "gallery":
        idx = len(studio.get("images") or [])
    elif phase == "detail":
        idx = len(studio.get("gallery") or [])
    studio["suggested_prompt"] = _suggested_prompt_for_phase(state, kind=phase, name=name, index=idx)
    studio["next_actions"] = _compute_next_actions(studio)
    studio["can_publish"] = _studio_can_publish(studio)


def _commit_approved_slot(studio: Dict[str, Any], slot: Dict[str, Any]) -> None:
    kind = (slot.get("kind") or "").strip()
    url = (slot.get("url") or "").strip()
    if not url:
        raise ValueError("Chưa có ảnh để duyệt.")
    if kind == "color":
        name = (slot.get("name") or "").strip() or f"Màu {int(slot.get('index') or 0) + 1}"
        colors = list(studio.get("colors") or [])
        idx = int(slot.get("index") or 0)
        # append if index beyond list (one-by-one without predeclared names)
        if idx >= len(colors):
            colors.append({"name": name, "img": url, "status": "approved"})
            idx = len(colors) - 1
        else:
            colors[idx] = {"name": name, "img": url, "status": "approved"}
        studio["colors"] = colors
        names = list(studio.get("color_names") or [])
        if name not in names:
            names.append(name)
        studio["color_names"] = names
        _add_to_ref_pool(
            studio,
            url=url,
            label=f"Màu {name}",
            kind="color",
            pool_id=f"color-{idx}",
        )
    elif kind == "main":
        studio["main_image"] = url
        _add_to_ref_pool(studio, url=url, label="Ảnh chính", kind="main", pool_id="main-0")
    elif kind == "gallery":
        images = list(studio.get("images") or [])
        images.append(url)
        studio["images"] = images
        i = len(images) - 1
        _add_to_ref_pool(
            studio, url=url, label=f"Gallery {i + 1}", kind="gallery", pool_id=f"gallery-{i}"
        )
    elif kind == "detail":
        gallery = list(studio.get("gallery") or [])
        gallery.append(url)
        studio["gallery"] = gallery
        i = len(gallery) - 1
        _add_to_ref_pool(
            studio, url=url, label=f"Chi tiết {i + 1}", kind="detail", pool_id=f"detail-{i}"
        )
    else:
        raise ValueError(f"Slot không hợp lệ: {kind}")
    studio["can_publish"] = _studio_can_publish(studio)


def job_public_view(state: Dict[str, Any]) -> Dict[str, Any]:
    """Shape trả API (kèm studio / vision)."""
    return {
        "job_id": state.get("job_id"),
        "status": state.get("status") or "unknown",
        "step": state.get("step"),
        "message": state.get("message"),
        "progress": int(state.get("progress") or 0),
        "result": state.get("result"),
        "error": state.get("error"),
        "created_at": state.get("created_at"),
        "updated_at": state.get("updated_at"),
        "vision_product_name": state.get("vision_product_name"),
        "vision_colors": state.get("vision_colors"),
        "studio": state.get("studio"),
    }


def _generate_name_and_description(brief: str, *, seed_name: str = "") -> Tuple[str, str, List[str]]:
    """DeepSeek đặt tên + mô tả marketing (giọng listing/ladipage). Không phụ thuộc flag import taxonomy."""
    from app.services.listing_year_sanitize import (
        LISTING_SANITIZE_PROMPT_VI,
        sanitize_listing_context_for_ai,
        sanitize_vi_listing_field,
    )
    from app.services.import_link_deepseek_taxonomy import (
        _TRANSLATE_ONLY_SYSTEM_VI,
        _extract_json_object,
        _scrub_cjk,
    )

    warnings: List[str] = []
    context = (
        "Đăng bán thủ công trên cửa hàng Việt Nam. "
        "Viết tên hấp dẫn, tự nhiên; mô tả theo phong cách landing/ladipage "
        "(lợi ích, chất liệu, đối tượng) nhưng plain text không HTML. "
        "Không bịa thông số ngoài ngữ cảnh brief.\n\n"
        f"{brief}"
    )
    name_src = sanitize_listing_context_for_ai((seed_name or "").strip() or "Sản phẩm thời trang")
    blob = sanitize_listing_context_for_ai(context.strip()[:9000])
    key = (settings.DEEPSEEK_API_KEY or "").strip()
    tv = ""
    mv = ""
    if key:
        if (seed_name or "").strip():
            user_prompt = (
                "NHIỆM VỤ: Giữ nguyên TÊN ĐÃ CHỐT bên dưới; chỉ viết mô tả tiếng Việt bán hàng.\n"
                "- ten_tieng_viet: copy đúng TÊN ĐÃ CHỐT (có thể tinh chỉnh nhẹ ≤5% nếu cần, không đổi loại SP).\n"
                "- mo_ta_vi: plain text tiếng Việt 350–1200 ký tự, 2–5 đoạn, \\n giữa đoạn; không HTML.\n"
                "- Giọng landing/ladipage (lợi ích, chất liệu, đối tượng), không bịa thông số ngoài brief.\n"
                f"{LISTING_SANITIZE_PROMPT_VI.strip()}\n\n"
                f"BRIEF:\n{blob}\n\n"
                f"TÊN ĐÃ CHỐT (SEO từ ảnh/admin):\n{name_src}\n\n"
                'Trả về JSON: {"ten_tieng_viet":"...","mo_ta_vi":"..."}'
            )
        else:
            user_prompt = (
                "NHIỆM VỤ: Đặt tên và viết mô tả tiếng Việt cho sản phẩm mới.\n"
                '- ten_tieng_viet: tên SP tiếng Việt tự nhiên ≤220 ký tự (không liệt kê hết size/màu ở cuối).\n'
                "- mo_ta_vi: plain text tiếng Việt 350–1200 ký tự, 2–5 đoạn, \\n giữa đoạn; không HTML.\n"
                "- Giọng bán hàng giống landing page (hero/highlights), không bịa thông số.\n"
                f"{LISTING_SANITIZE_PROMPT_VI.strip()}\n\n"
                f"BRIEF ADMIN:\n{blob}\n\n"
                'Trả về JSON: {"ten_tieng_viet":"...","mo_ta_vi":"..."}'
            )
        url = (settings.DEEPSEEK_API_URL or "").strip() or "https://api.deepseek.com/v1/chat/completions"
        model = (settings.DEEPSEEK_MODEL or "").strip() or "deepseek-v4-flash"
        try:
            from app.services.deepseek_http import deepseek_chat_completions

            resp = deepseek_chat_completions(
                {
                    "model": model,
                    "temperature": 0.35,
                    "messages": [
                        {"role": "system", "content": _TRANSLATE_ONLY_SYSTEM_VI.strip()},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 4096,
                },
                timeout=90,
                api_url=url,
                api_key=key,
            )
            if resp.ok:
                body = resp.json()
                content = (body.get("choices") or [{}])[0].get("message", {}).get("content") or ""
                parsed = _extract_json_object(content)
                tv = sanitize_vi_listing_field(_scrub_cjk(str(parsed.get("ten_tieng_viet") or "")).strip())
                mv = sanitize_vi_listing_field(_scrub_cjk(str(parsed.get("mo_ta_vi") or "")).strip())
                if len(tv) > 220:
                    tv = tv[:220].strip()
                mv = re.sub(r"[ \t]+\n", "\n", mv)
                mv = re.sub(r"\n{3,}", "\n\n", mv).strip()
                if len(mv) > 12000:
                    mv = mv[:12000].strip()
            else:
                warnings.append(f"deepseek_manual: HTTP {resp.status_code}")
        except Exception as exc:
            warnings.append(f"deepseek_manual: {exc}")
    else:
        warnings.append("deepseek_manual: thiếu DEEPSEEK_API_KEY.")

    if not tv:
        # Thử lại qua helper import (nếu flag bật)
        tv2, mv2, tw = translate_product_listing_deepseek_only(
            name_src, brief, context_text=context
        )
        warnings.extend(tw)
        tv = tv or tv2
        mv = mv or mv2

    if not tv:
        parts = []
        for line in brief.splitlines():
            if "Chất liệu:" in line or "Phong cách" in line or "Giới tính:" in line:
                parts.append(line.split(":", 1)[-1].strip())
        tv = " · ".join([p for p in parts if p])[:200] or "Sản phẩm mới"
        warnings.append("deepseek: dùng tên fallback từ brief.")
    if not mv:
        mv = brief
        warnings.append("deepseek: dùng mô tả fallback từ brief.")
    return tv, mv, warnings


def validate_job_payload(payload: Dict[str, Any]) -> None:
    mode = (payload.get("mode") or "").strip().lower()
    if mode not in ("manual", "ai"):
        raise ValueError("mode phải là «manual» hoặc «ai».")
    try:
        price = float(payload.get("price"))
    except (TypeError, ValueError):
        raise ValueError("Giá bán không hợp lệ.") from None
    if price <= 0:
        raise ValueError("Giá bán phải > 0.")
    material = (payload.get("material") or "").strip()
    if not material:
        raise ValueError("Vui lòng nhập chất liệu.")
    product_name = (payload.get("product_name") or payload.get("name") or "").strip()
    if mode == "manual":
        main = (payload.get("main_image") or "").strip()
        if not main:
            raise ValueError("Mode thủ công cần ảnh chính (main_image).")
        if not product_name:
            raise ValueError("Vui lòng nhập tên sản phẩm.")
    else:
        refs = payload.get("ref_image_urls") or []
        if not isinstance(refs, list) or not any(str(u).strip() for u in refs):
            raise ValueError("Mode AI cần ít nhất 1 ảnh gốc tham chiếu (tối đa 3).")
        if len([u for u in refs if str(u).strip()]) > 3:
            raise ValueError("Mode AI tối đa 3 ảnh gốc.")
        # Mode AI: tên có thể để trống — Gemini đọc ảnh đặt tên SEO.
        if _resolve_model_presence(payload.get("model_presence")) == "model":
            if not str(payload.get("model_gender") or "").strip():
                raise ValueError("Chọn «Có người mẫu» thì cần điền giới tính người mẫu.")
            if not str(payload.get("model_age_group") or "").strip():
                raise ValueError("Chọn «Có người mẫu» thì cần điền độ tuổi người mẫu.")
            if not str(payload.get("model_ethnicity") or "").strip():
                raise ValueError("Chọn «Có người mẫu» thì cần điền quốc tịch/gốc người mẫu.")


def _gemini_request_json(url: str, payload: Dict[str, Any], *, timeout: int = 90) -> Dict[str, Any]:
    """POST Gemini generateContent; SSL fail trên Windows → retry verify=False."""
    verify = True
    raw = (getattr(settings, "GEMINI_SSL_VERIFY", None))
    if raw is not None:
        verify = bool(raw)
    try:
        res = requests.post(url, json=payload, timeout=timeout, verify=verify)
    except requests.exceptions.SSLError:
        if not verify:
            raise
        logger.warning("Gemini SSL verify failed — retry verify=False (dev Windows thiếu CA).")
        try:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
        res = requests.post(url, json=payload, timeout=timeout, verify=False)
    if res.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {res.status_code}: {(res.text or '')[:400]}")
    return res.json()


# Vision đặt tên: resize cạnh dài ≤1024 + JPEG vừa phải → ít tile token, vẫn đủ rõ SP.
_VISION_NAME_MAX_EDGE = 1024
_VISION_NAME_JPEG_QUALITY = 82


def _resize_image_bytes_for_vision_name(raw: bytes) -> Tuple[bytes, str]:
    """
    Thu nhỏ ảnh gốc trước khi gửi Gemini vision đặt tên.
    Giảm số tile/token; không ảnh hưởng bước tạo ảnh đăng (vẫn dùng URL gốc).
    Trả (jpeg_bytes, mime).
    """
    import cv2
    import numpy as np

    arr = np.frombuffer(raw, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        # Fallback: gửi bytes gốc (mime đoán sau)
        return raw, ""
    h, w = img.shape[:2]
    long_edge = max(h, w)
    if long_edge > _VISION_NAME_MAX_EDGE:
        scale = _VISION_NAME_MAX_EDGE / float(long_edge)
        nh = max(1, int(round(h * scale)))
        nw = max(1, int(round(w * scale)))
        img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    ok, enc = cv2.imencode(
        ".jpg",
        img,
        [int(cv2.IMWRITE_JPEG_QUALITY), _VISION_NAME_JPEG_QUALITY],
    )
    if not ok:
        return raw, ""
    return enc.tobytes(), "image/jpeg"


def _extract_vision_name_json(text: str) -> Tuple[str, str, List[str]]:
    """Parse JSON tên SP + danh sách màu; nếu bị cắt MAX_TOKENS vẫn cố lấy ten_san_pham."""
    text = (text or "").strip()
    if not text:
        return "", "", []
    parsed: Dict[str, Any] = {}
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(text[start:end])
        else:
            parsed = json.loads(text)
    except Exception:
        parsed = {}
    name = str(parsed.get("ten_san_pham") or "").strip()
    if not name:
        m = re.search(r'"ten_san_pham"\s*:\s*"((?:\\.|[^"\\])*)"', text)
        if m:
            try:
                name = json.loads(f'"{m.group(1)}"')
            except Exception:
                name = m.group(1).replace('\\"', '"').strip()
    analysis = " | ".join(
        [
            x
            for x in [
                str(parsed.get("loai_san_pham") or "").strip(),
                str(parsed.get("diem_noi_bat") or "").strip(),
                str(parsed.get("mo_ta_ngan") or "").strip(),
            ]
            if x
        ]
    )
    colors_out: List[str] = []
    raw_colors = parsed.get("mau_sac") or parsed.get("colors") or []
    if isinstance(raw_colors, str):
        raw_colors = [x.strip() for x in re.split(r"[,/;|]", raw_colors) if x.strip()]
    if isinstance(raw_colors, list):
        seen = set()
        for c in raw_colors:
            cn = str(c or "").strip()
            if not cn:
                continue
            key = cn.lower()
            if key in seen:
                continue
            seen.add(key)
            colors_out.append(cn[:40])
            if len(colors_out) >= 8:
                break
    if not colors_out:
        m2 = re.search(r'"mau_sac"\s*:\s*\[([^\]]*)\]', text)
        if m2:
            for piece in re.findall(r'"((?:\\.|[^"\\])*)"', m2.group(1)):
                cn = piece.strip()
                if cn and cn.lower() not in {x.lower() for x in colors_out}:
                    colors_out.append(cn[:40])
    if len(name) > 120:
        name = name[:120].strip()
    return name, analysis, colors_out


def name_product_from_reference_images(
    image_urls: List[str],
    *,
    gender: str = "",
    material: str = "",
    style: str = "",
    colors: Optional[List[str]] = None,
    notes: str = "",
) -> Tuple[str, str, List[str], List[str]]:
    """
    Gemini vision đọc 1–3 ảnh gốc → (tên SEO, phân tích, mau_sac[], warnings).
    """
    warnings: List[str] = []
    api_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if len(api_key) < 10:
        warnings.append("vision_name: thiếu GEMINI_API_KEY.")
        return "", "", [], warnings

    urls = [str(u).strip() for u in (image_urls or []) if str(u).strip()][:3]
    if not urls:
        warnings.append("vision_name: thiếu ảnh gốc.")
        return "", "", [], warnings

    image_parts: List[Dict[str, Any]] = []
    for idx, image_url in enumerate(urls):
        try:
            img_resp = requests.get(image_url, timeout=30)
            img_resp.raise_for_status()
            jpeg_bytes, mime = _resize_image_bytes_for_vision_name(img_resp.content)
            if not mime:
                mime = _guess_mime_from_url(image_url, img_resp.headers.get("Content-Type")) or "image/jpeg"
            b64 = base64.b64encode(jpeg_bytes).decode("ascii")
            image_parts.append({"inline_data": {"mime_type": mime, "data": b64}})
        except Exception as exc:
            warnings.append(f"vision_name: tải/resize ảnh {idx + 1} lỗi: {exc}")

    if not image_parts:
        warnings.append("vision_name: không tải được ảnh nào.")
        return "", "", [], warnings

    model = (getattr(settings, "GEMINI_MODEL", "") or "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    model = model.replace("-latest", "")
    gender_txt = (gender or "").strip() or "không rõ"
    material_txt = (material or "").strip() or "theo ảnh"
    style_txt = (style or "").strip() or "thời trang"
    colors_txt = ", ".join([c for c in (colors or []) if c]) or "tự nhận từ ảnh"
    notes_txt = (notes or "").strip() or "không"
    n_img = len(image_parts)

    prompt = (
        "Bạn là chuyên gia đặt tên sản phẩm e-commerce thời trang Việt Nam (SEO + chuyển đổi).\n"
        f"NHIỆM VỤ: Nhìn {n_img} ảnh sản phẩm (1 ảnh cũng đủ), nhận diện đúng loại hàng "
        "(set bộ áo+quần / đầm / áo / giày / túi… — nhìn kỹ có quần/short riêng không), "
        "form, chất cảm, chi tiết nổi bật — rồi đặt MỘT TÊN TIẾNG VIỆT "
        "chuẩn SEO, khách dễ tìm và muốn mua.\n"
        "Đồng thời liệt kê các MÀU sản phẩm nhìn thấy trên ảnh (tiếng Việt ngắn).\n"
        "Quy tắc tên:\n"
        "- 45–90 ký tự, tự nhiên, có loại SP + đặc điểm bán (đối tượng, họa tiết, form).\n"
        "- Không mã SKU, không emoji, không dấu ngoặc thừa.\n"
        "- Không liệt kê hết size/màu ở cuối tên.\n"
        "- Có thể nêu motif/nhân vật in trên áo nếu nhìn thấy vì khách hay search.\n"
        f"Gợi ý admin — Giới tính: {gender_txt}; Chất liệu: {material_txt}; "
        f"Phong cách: {style_txt}; Màu gợi ý: {colors_txt}; Ghi chú: {notes_txt}.\n"
        "Trả ĐÚNG một JSON ngắn (không markdown, không giải thích):\n"
        '{"ten_san_pham":"...","loai_san_pham":"...","diem_noi_bat":"...","mo_ta_ngan":"...","mau_sac":["..."]}'
    )

    parts: List[Dict[str, Any]] = [{"text": prompt}]
    parts.extend(image_parts)

    url = f"{GEMINI_BASE_URL}/models/{model}:generateContent?key={api_key}"
    # maxOutputTokens cao: gemini-2.5-flash tính cả thinking vào budget → 800 dễ MAX_TOKENS cắt JSON.
    gen_cfg: Dict[str, Any] = {
        "temperature": 0.2,
        "maxOutputTokens": 4096,
        "responseMimeType": "application/json",
        "thinkingConfig": {"thinkingBudget": 0},
    }
    payload: Dict[str, Any] = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": gen_cfg,
    }

    def _call(cfg: Dict[str, Any]) -> Dict[str, Any]:
        return _gemini_request_json(
            url,
            {"contents": [{"role": "user", "parts": parts}], "generationConfig": cfg},
            timeout=90,
        )

    body: Dict[str, Any] = {}
    try:
        body = _call(gen_cfg)
    except Exception as exc:
        msg = str(exc).lower()
        # Bỏ field không hỗ trợ rồi thử lại
        cfg2 = dict(gen_cfg)
        dropped = False
        if "thinking" in msg:
            cfg2.pop("thinkingConfig", None)
            dropped = True
        if "mediaresolution" in msg.replace("_", "") or "media_resolution" in msg:
            cfg2.pop("mediaResolution", None)
            dropped = True
        if dropped or "invalid" in msg:
            try:
                cfg2.pop("thinkingConfig", None)
                body = _call(cfg2)
                warnings.append(f"vision_name: fallback config sau lỗi: {exc}")
            except Exception as exc2:
                warnings.append(f"vision_name: {exc2}")
                return "", "", [], warnings
        else:
            warnings.append(f"vision_name: {exc}")
            return "", "", [], warnings

    text = ""
    finish = ""
    try:
        cands = body.get("candidates") or []
        if cands:
            finish = str(cands[0].get("finishReason") or "")
            resp_parts = ((cands[0].get("content") or {}).get("parts") or [])
            for p in resp_parts:
                if isinstance(p, dict) and p.get("text"):
                    text += str(p["text"])
        fb = body.get("promptFeedback") or {}
        if fb.get("blockReason"):
            warnings.append(f"vision_name: prompt bị chặn ({fb.get('blockReason')}).")
    except Exception:
        text = ""
    if not text.strip():
        warnings.append(f"vision_name: Gemini không trả text (finish={finish or 'n/a'}).")
        return "", "", [], warnings
    if "MAX" in finish.upper() and "TOKEN" in finish.upper():
        warnings.append("vision_name: output bị cắt MAX_TOKENS — đang parse phần còn lại.")

    name, analysis, colors_out = _extract_vision_name_json(text)
    if not name:
        warnings.append("vision_name: thiếu ten_san_pham trong JSON.")
        return "", analysis, colors_out, warnings
    return name, analysis, colors_out, warnings


def name_product_from_reference_image(
    image_url: str,
    *,
    gender: str = "",
    material: str = "",
    style: str = "",
    colors: Optional[List[str]] = None,
    notes: str = "",
) -> Tuple[str, str, List[str], List[str]]:
    """Alias tương thích — ủy quyền sang name_product_from_reference_images."""
    return name_product_from_reference_images(
        [image_url],
        gender=gender,
        material=material,
        style=style,
        colors=colors,
        notes=notes,
    )


def _resolve_category_id_for_product_data(db: Session, product_data: Dict[str, Any]) -> Optional[int]:
    """Gán FK category_id từ bộ ba taxonomy (tên cat1/2/3)."""
    c1 = (product_data.get("category") or "").strip()
    c2 = (product_data.get("subcategory") or "").strip()
    c3 = (product_data.get("sub_subcategory") or "").strip()
    if not (c1 and c2 and c3):
        return None
    triple_idx = product_crud._build_cat3_triple_name_lookup(db)
    key = f"{c1.lower()}\x1f{c2.lower()}\x1f{c3.lower()}"
    cid = triple_idx.get(key)
    if cid:
        return cid
    cat3_idx = product_crud._build_cat3_lookup_indexes(db)
    return product_crud._resolve_category_id_from_row(product_data, cat3_idx)


def _sync_product_description_from_ladipage(db: Session, product: Any, lp: Any) -> None:
    """
    Đồng bộ cột description sản phẩm từ section ladipage (hero + highlights)
    để nội dung SP và trang landing cùng giọng.
    """
    from app.models.ladipage import LadipageSection

    sections = (
        db.query(LadipageSection)
        .filter(LadipageSection.ladipage_id == int(lp.id))
        .order_by(LadipageSection.order_index)
        .all()
    )
    parts: List[str] = []
    for section in sections:
        data = section.data or {}
        st = (section.section_type or "").strip()
        if st == "hero":
            h = (data.get("headline") or "").strip()
            sub = (data.get("subheadline") or "").strip()
            if h:
                parts.append(h)
            if sub:
                parts.append(sub)
        elif st == "highlights":
            items = data.get("items") or []
            if isinstance(items, list):
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    t = (it.get("title") or "").strip()
                    d = (it.get("desc") or "").strip()
                    if t and d:
                        parts.append(f"{t}: {d}")
                    elif t or d:
                        parts.append(t or d)
        elif st == "material":
            body = (data.get("body") or "").strip()
            if body:
                parts.append(body)
        elif st == "trust_cta":
            body = (data.get("body") or "").strip()
            if body:
                parts.append(body)
    text = "\n\n".join([p for p in parts if p]).strip()
    if len(text) < 80:
        return
    current = (getattr(product, "description", None) or "").strip()
    # Chỉ ghi đè khi mô tả còn ngắn / fallback
    if len(current) >= 350 and "Giới tính:" not in current:
        return
    product.description = text[:12000]
    db.add(product)
    db.commit()
    db.refresh(product)


def _run_ai_studio_bootstrap(job_id: str) -> None:
    """Mode AI: chỉ vision đặt tên → awaiting_input (form tạo từng mốc)."""
    state = load_job(job_id) or {}
    payload = dict(state.get("payload") or {})
    warnings: List[str] = list(state.get("warnings") or [])
    try:
        _job_update(
            job_id,
            status="generating",
            step="validate",
            message="Đang kiểm tra dữ liệu…",
            progress=5,
            error=None,
        )
        validate_job_payload(payload)
        product_key = (state.get("product_key") or "").strip() or new_manual_product_id()
        studio = _init_studio(payload, product_key=product_key)
        refs = [str(u).strip() for u in (payload.get("ref_image_urls") or []) if str(u).strip()][:3]
        gender = (payload.get("gender") or "").strip()
        material = (payload.get("material") or "").strip()
        style = (payload.get("style") or "").strip()
        admin_name = (payload.get("product_name") or payload.get("name") or "").strip()

        _job_update(
            job_id,
            status="generating",
            step="vision_name",
            message=f"Gemini đang đọc {len(refs)} ảnh gốc để đặt tên SEO…",
            progress=12,
            product_key=product_key,
            studio=studio,
        )
        vision_name, vision_analysis, vision_colors, vw = name_product_from_reference_images(
            refs,
            gender=gender,
            material=material,
            style=style,
            colors=_parse_colors(payload.get("colors")),
            notes=(payload.get("notes") or "").strip(),
        )
        warnings.extend(vw)
        if admin_name:
            name_source = "admin"
        elif vision_name:
            name_source = "gemini_vision"
            payload = {**payload, "product_name": vision_name}
        else:
            detail = "; ".join([w for w in vw if w][:3]) or "Gemini không trả tên hợp lệ."
            raise RuntimeError(
                "Chưa đặt được tên SEO từ ảnh gốc. "
                f"Chi tiết: {detail} "
                "1 ảnh là đủ; thử lại hoặc kiểm tra GEMINI_API_KEY / ảnh tải được."
            )

        studio = _init_studio(payload, product_key=product_key)
        _refresh_studio_hints({"payload": payload, "studio": studio}, studio)

        _job_update(
            job_id,
            status="awaiting_input",
            step="awaiting_input",
            message=(
                f"Đã đặt tên SEO: {(admin_name or vision_name)[:80]}. "
                "Nhập màu đầu tiên + chọn ảnh tham khảo + prompt rồi bấm Tạo."
            ),
            progress=20,
            payload=payload,
            product_key=product_key,
            studio=studio,
            vision_product_name=vision_name or admin_name or None,
            vision_analysis=vision_analysis or None,
            vision_colors=vision_colors or [],
            name_source=name_source,
            warnings=warnings,
            error=None,
        )
    except Exception as exc:
        logger.exception("manual_product AI bootstrap %s failed", job_id)
        _job_update(
            job_id,
            status="failed",
            step="error",
            message=str(exc)[:2000],
            error=str(exc)[:2000],
        )
    finally:
        with _WORKER_LOCK:
            _ACTIVE_THREADS.pop(job_id, None)


def _run_generate_studio_slot(job_id: str) -> None:
    """Tạo đúng 1 ảnh cho current_slot → awaiting_approval."""
    try:
        state = load_job(job_id) or {}
        studio = dict(state.get("studio") or {})
        slot = dict(studio.get("current_slot") or {})
        if not slot.get("kind"):
            raise RuntimeError("Không có slot ảnh để tạo.")
        product_key = (studio.get("product_key") or state.get("product_key") or "").strip()
        if not product_key:
            product_key = new_manual_product_id()
            studio["product_key"] = product_key
        plan = dict(studio.get("plan") or {})
        image_model_choice = str(plan.get("image_model") or "pro").strip() or "pro"
        model_id, model_size, model_label = _resolve_manual_ai_image_model(image_model_choice)
        kind = str(slot.get("kind") or "").strip()
        attempt = int(slot.get("attempt") or 0) + 1
        slot["attempt"] = attempt
        label = _slot_label(slot)

        _job_update(
            job_id,
            status="generating",
            step=f"ai_{kind}",
            message=f"Đang tạo {label} ({model_label}, lần {attempt})…",
            progress=30,
            studio={**studio, "current_slot": slot},
            ai_image_model=model_id,
            ai_image_model_label=model_label,
            error=None,
        )

        refs = _resolve_selected_refs(
            studio,
            ref_urls=list(slot.get("ref_urls") or []),
            attach_url=str(slot.get("attach_url") or ""),
        )
        if not refs:
            raise RuntimeError("Chọn ít nhất 1 ảnh tham khảo (hoặc gửi ảnh kèm).")
        prompt = _build_studio_slot_prompt({**state, "studio": studio}, slot)
        raw = _gemini_edit_from_urls(
            refs,
            prompt,
            image_model=model_id,
            image_size=model_size,
        )
        hint = f"{kind}-{int(slot.get('index') or 0) + 1}-a{attempt}"
        url = _upload_product_image_bytes(raw, name_hint=hint, product_key=product_key)
        slot["url"] = url
        studio["current_slot"] = slot
        studio["phase"] = kind
        studio["can_publish"] = _studio_can_publish(studio)

        _job_update(
            job_id,
            status="awaiting_approval",
            step="awaiting_approval",
            message=f"Xem {label} — OK thì Tiếp, chưa ổn thì Tạo lại (có thể sửa prompt/ref).",
            progress=45,
            studio=studio,
            product_key=product_key,
            error=None,
        )
    except Exception as exc:
        logger.exception("manual_product studio generate %s failed", job_id)
        st = load_job(job_id) or {}
        studio = dict(st.get("studio") or {})
        _job_update(
            job_id,
            status="awaiting_approval",
            step="awaiting_approval",
            message=f"Tạo ảnh lỗi: {str(exc)[:400]}. Sửa prompt/ref rồi Tạo lại.",
            error=str(exc)[:2000],
            studio=studio,
        )
    finally:
        with _WORKER_LOCK:
            _ACTIVE_THREADS.pop(job_id, None)


def _resolve_publish_media(studio: Dict[str, Any]) -> Tuple[str, List[str], List[str], List[Dict[str, Any]]]:
    colors_payload: List[Dict[str, Any]] = []
    for row in studio.get("colors") or []:
        if not isinstance(row, dict):
            continue
        name = (row.get("name") or "").strip()
        img = (row.get("img") or "").strip()
        if name and img:
            colors_payload.append({"name": name, "img": img})
    main_image = (studio.get("main_image") or "").strip()
    if not main_image and colors_payload:
        main_image = colors_payload[0]["img"]
    images = [str(u).strip() for u in (studio.get("images") or []) if str(u).strip()]
    gallery = [str(u).strip() for u in (studio.get("gallery") or []) if str(u).strip()]
    if not main_image:
        raise ValueError("Chưa có ảnh để đăng (cần ít nhất 1 ảnh màu hoặc ảnh chính).")
    if not colors_payload:
        colors_payload = [{"name": "Màu chính", "img": main_image}]
    return main_image, images, gallery, colors_payload


def _finalize_product_from_media(
    job_id: str,
    *,
    main_image: str,
    images: List[str],
    gallery: List[str],
    colors_payload: List[Dict[str, Any]],
    mode: str,
) -> None:
    """DeepSeek + taxonomy + tạo SP + Ladipage (dùng bởi manual full + AI publish)."""
    state = load_job(job_id) or {}
    payload = dict(state.get("payload") or {})
    admin_id = state.get("created_by")
    warnings: List[str] = list(state.get("warnings") or [])
    db: Optional[Session] = None
    try:
        product_key = (
            (state.get("product_key") or "").strip()
            or ((state.get("studio") or {}).get("product_key") or "").strip()
            or new_manual_product_id()
        )
        sizes = _parse_sizes(payload.get("sizes"), no_size=bool(payload.get("no_size")))
        gender = (payload.get("gender") or "").strip()
        material = (payload.get("material") or "").strip()
        style = (payload.get("style") or "").strip()
        available = int(payload.get("available") or 500)
        if available < 0:
            available = 0

        admin_name = (payload.get("product_name") or payload.get("name") or "").strip()
        vision_name = (state.get("vision_product_name") or "").strip()
        vision_analysis = (state.get("vision_analysis") or "").strip()
        vision_colors = list(state.get("vision_colors") or [])
        name_source = state.get("name_source") or ("admin" if admin_name else "gemini_vision")

        # Sync màu vào payload brief
        payload = {
            **payload,
            "colors": [{"name": c["name"], "img": c.get("img") or ""} for c in colors_payload],
        }
        brief = _build_brief_blob(payload)
        if vision_analysis:
            brief = f"{brief}\nPhân tích ảnh gốc: {vision_analysis}"
        if vision_colors:
            brief = f"{brief}\nMàu gợi ý từ ảnh: {', '.join([str(x) for x in vision_colors if x])}"
        color_names = [c["name"] for c in colors_payload]
        if color_names:
            brief = f"{brief}\nMàu đã chọn: {', '.join(color_names)}"

        locked_name = (admin_name or vision_name or "").strip()
        _job_update(
            job_id,
            status="publishing",
            step="text",
            message="DeepSeek đang viết mô tả" + (" theo tên SEO…" if locked_name else " và đặt tên…"),
            progress=80,
            error=None,
        )
        name_vi, desc_vi, tw = _generate_name_and_description(brief, seed_name=locked_name)
        warnings.extend(tw)
        if locked_name:
            name_vi = locked_name[:500]

        product_data: Dict[str, Any] = {
            "product_id": product_key,
            "name": name_vi,
            "description": desc_vi,
            "price": float(payload.get("price")),
            "sizes": sizes,
            "colors": colors_payload,
            "images": images,
            "gallery": gallery,
            "main_image": main_image,
            "material": material,
            "style": style,
            "available": available,
            "origin": "manual" if mode == "manual" else "manual_ai",
            "brand_name": (payload.get("brand_name") or "").strip() or None,
            "shop_name": (payload.get("shop_name") or "").strip() or "188.com.vn",
            "product_info": {
                "manual_create": {
                    "mode": mode,
                    "gender": gender,
                    "brief": brief,
                    "admin_product_name": admin_name,
                    "vision_product_name": vision_name or None,
                    "vision_analysis": vision_analysis or None,
                    "vision_colors": vision_colors or None,
                    "name_source": name_source,
                    "model_presence": (
                        str(payload.get("model_presence") or "").strip() or None
                    )
                    if mode == "ai"
                    else None,
                    "shot_style": (
                        str(payload.get("shot_style") or "").strip() or None
                    )
                    if mode == "ai"
                    else None,
                    "image_model": (
                        str(payload.get("image_model") or payload.get("ai_image_model") or "").strip()
                        or None
                    )
                    if mode == "ai"
                    else None,
                    "created_at": _utcnow_iso(),
                }
            },
        }
        gender_hint = _gender_hint(gender)
        if gender_hint == "male":
            product_data["chinese_name"] = f"{name_vi} 男士 男款"
        elif gender_hint == "female":
            product_data["chinese_name"] = f"{name_vi} 女士 女款"
        else:
            product_data["chinese_name"] = name_vi

        db = SessionLocal()
        _job_update(
            job_id,
            status="publishing",
            step="taxonomy",
            message="DeepSeek đang gán danh mục taxonomy…",
            progress=84,
        )
        tax_warnings = apply_deepseek_taxonomy_to_product_data(db, product_data)
        warnings.extend(tax_warnings)

        c1 = (product_data.get("category") or "").strip()
        c2 = (product_data.get("subcategory") or "").strip()
        c3 = (product_data.get("sub_subcategory") or "").strip()
        require_tax = bool(payload.get("require_taxonomy", mode == "ai"))
        if require_tax and not (c1 and c2 and c3):
            err_bits = [w for w in tax_warnings if "taxonomy" in w.lower() or "deepseek" in w.lower()]
            detail = "; ".join(err_bits[:3]) if err_bits else "DeepSeek không trả bộ ba cat1/cat2/cat3 hợp lệ."
            raise RuntimeError(
                "Không gán được danh mục taxonomy chuẩn (category / subcategory / sub_subcategory). "
                f"{detail}"
            )

        cid = _resolve_category_id_for_product_data(db, product_data)
        if cid:
            product_data["category_id"] = cid
        elif require_tax and (c1 and c2 and c3):
            warnings.append(
                f"taxonomy: đã có bộ ba «{c1} › {c2} › {c3}» nhưng không khớp category_id trong DB."
            )
            if mode == "ai":
                raise RuntimeError(
                    f"Danh mục «{c1} › {c2} › {c3}» không khớp taxonomy DB (category_id). "
                    "Kiểm tra cây danh mục / taxonomy_import."
                )

        if admin_name and not (product_data.get("name") or "").strip():
            product_data["name"] = admin_name[:500]

        _job_update(
            job_id,
            status="publishing",
            step="create_product",
            message="Đang tạo sản phẩm…",
            progress=88,
        )
        create_fields = getattr(ProductCreate, "model_fields", None) or getattr(
            ProductCreate, "__fields__", {}
        )
        create = ProductCreate(**{k: v for k, v in product_data.items() if k in create_fields})
        product = product_crud.create_product(db, create)

        _job_update(
            job_id,
            status="publishing",
            step="ladipage",
            message="Đang tạo trang SP kiểu Ladipage (hero, highlights…)…",
            progress=94,
        )
        lp = bootstrap_single_product_ladipage(
            db,
            product,
            created_by=int(admin_id) if admin_id else None,
            publish=True,
            skip_if_exists=True,
        )
        if lp is None:
            from app.services.ladipage_cleanup import find_single_product_ladipages_for_product

            existing_lps = find_single_product_ladipages_for_product(db, int(product.id))
            lp = existing_lps[0] if existing_lps else None
            if lp is not None:
                try:
                    fill_ladipage_ai_content(db, lp)
                except Exception as fill_exc:
                    warnings.append(f"ladipage_fill: {fill_exc}")
                if (lp.status or "").strip() != "published":
                    publish_ladipage(db, lp)
                db.commit()
                db.refresh(lp)

        if lp is None:
            raise RuntimeError(
                "Không tạo được Ladipage 1 SP — trang sản phẩm sẽ không có hero/highlights/FAQ."
            )

        try:
            _sync_product_description_from_ladipage(db, product, lp)
        except Exception as sync_exc:
            warnings.append(f"sync_description: {sync_exc}")

        result = {
            "product_id": product.product_id,
            "product_db_id": product.id,
            "code": product.code,
            "slug": product.slug,
            "name": product.name,
            "category": product.category,
            "subcategory": product.subcategory,
            "sub_subcategory": product.sub_subcategory,
            "category_id": product.category_id,
            "ladipage_id": lp.id if lp else None,
            "ladipage_slug": lp.slug if lp else None,
            "ladipage_status": (lp.status if lp else None),
            "mode": mode,
            "warnings": warnings,
        }
        _job_update(
            job_id,
            status="done",
            step="done",
            message="Đăng sản phẩm thành công.",
            progress=100,
            result=result,
            error=None,
            warnings=warnings,
        )
    except Exception as exc:
        logger.exception("manual_product finalize %s failed", job_id)
        _job_update(
            job_id,
            status="failed",
            step="error",
            message=str(exc)[:2000],
            error=str(exc)[:2000],
            progress=int((load_job(job_id) or {}).get("progress") or 0),
        )
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        raise
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def _run_publish_studio_job(job_id: str) -> None:
    try:
        state = load_job(job_id) or {}
        if (state.get("status") or "") == "done":
            return
        studio = dict(state.get("studio") or {})
        main_image, images, gallery, colors_payload = _resolve_publish_media(studio)
        _finalize_product_from_media(
            job_id,
            main_image=main_image,
            images=images,
            gallery=gallery,
            colors_payload=colors_payload,
            mode="ai",
        )
    except Exception as exc:
        # _finalize already marks failed; ensure message if resolve failed early
        st = load_job(job_id) or {}
        if (st.get("status") or "") != "failed":
            _job_update(
                job_id,
                status="failed",
                step="error",
                message=str(exc)[:2000],
                error=str(exc)[:2000],
            )
        logger.exception("manual_product publish %s failed", job_id)
    finally:
        with _WORKER_LOCK:
            _ACTIVE_THREADS.pop(job_id, None)


def run_manual_product_job(job_id: str) -> None:
    """Worker entry: manual = full pipeline; AI = bootstrap studio (vision → awaiting_colors)."""
    state = load_job(job_id) or {}
    payload = dict(state.get("payload") or {})
    mode = (payload.get("mode") or "").strip().lower()
    action = (state.get("worker_action") or "").strip().lower()

    if action == "generate_slot":
        _run_generate_studio_slot(job_id)
        return
    if action == "publish":
        _run_publish_studio_job(job_id)
        return
    if mode == "ai":
        _run_ai_studio_bootstrap(job_id)
        return

    # Mode manual — full pipeline (không studio)
    warnings: List[str] = []
    try:
        _job_step(job_id, "validate", "Đang kiểm tra dữ liệu…", progress=5)
        validate_job_payload(payload)
        color_items = _parse_color_items(payload.get("colors"))
        _job_step(job_id, "media", "Đang gắn ảnh thủ công…", progress=25)
        main_image = str(payload.get("main_image") or "").strip()
        images = [str(u).strip() for u in (payload.get("images") or []) if str(u).strip()]
        gallery = [str(u).strip() for u in (payload.get("gallery") or []) if str(u).strip()]
        colors_payload: List[Dict[str, Any]] = []
        for item in color_items:
            img = (item.get("img") or "").strip() or main_image
            colors_payload.append({"name": item["name"], "img": img})
        _job_update(job_id, warnings=warnings, product_key=new_manual_product_id())
        _finalize_product_from_media(
            job_id,
            main_image=main_image,
            images=images,
            gallery=gallery,
            colors_payload=colors_payload,
            mode="manual",
        )
    except Exception as exc:
        logger.exception("manual_product job %s failed", job_id)
        st = load_job(job_id) or {}
        if (st.get("status") or "") != "failed":
            _job_update(
                job_id,
                status="failed",
                step="error",
                message=str(exc)[:2000],
                error=str(exc)[:2000],
            )
    finally:
        with _WORKER_LOCK:
            _ACTIVE_THREADS.pop(job_id, None)


def enqueue_manual_product_job(job_id: str, *, worker_action: Optional[str] = None) -> None:
    """Chạy worker trên daemon thread (tránh timeout HTTP)."""
    if worker_action:
        _job_update(job_id, worker_action=worker_action)

    def _run() -> None:
        run_manual_product_job(job_id)

    with _WORKER_LOCK:
        existing = _ACTIVE_THREADS.get(job_id)
        if existing and existing.is_alive():
            return
        t = threading.Thread(target=_run, name=f"manual-product-{job_id[:8]}", daemon=True)
        _ACTIVE_THREADS[job_id] = t
        t.start()


def create_and_start_job(payload: Dict[str, Any], *, created_by: Optional[int] = None) -> Dict[str, Any]:
    validate_job_payload(payload)
    job_id = str(uuid.uuid4())
    mode = (payload.get("mode") or "").strip().lower()
    state: Dict[str, Any] = {
        "job_id": job_id,
        "status": "queued",
        "step": "queued",
        "message": (
            "Đã xếp hàng — Gemini đặt tên SEO rồi chờ nhập màu."
            if mode == "ai"
            else "Đã xếp hàng đăng sản phẩm."
        ),
        "progress": 0,
        "payload": payload,
        "created_by": created_by,
        "created_at": _utcnow_iso(),
        "updated_at": _utcnow_iso(),
        "result": None,
        "error": None,
        "worker_action": "bootstrap" if mode == "ai" else "full",
        "studio": None,
    }
    persist_job(job_id, state)
    enqueue_manual_product_job(job_id)
    return state


def start_studio_generate(
    job_id: str,
    *,
    kind: str,
    name: str = "",
    prompt: str = "",
    ref_urls: Optional[List[str]] = None,
    attach_url: str = "",
) -> Dict[str, Any]:
    """
    Tạo 1 ảnh theo mốc: color | main | gallery | detail.
    Khách chọn ref + (tuỳ chọn) ảnh kèm + prompt rồi mới gen.
    """
    kind_n = (kind or "").strip().lower()
    if kind_n not in ("color", "main", "gallery", "detail"):
        raise ValueError("kind phải là color | main | gallery | detail.")
    with _WORKER_LOCK:
        state = load_job(job_id)
        if not state:
            raise ValueError("Không tìm thấy job")
        status = (state.get("status") or "").strip()
        if status not in ("awaiting_input", "awaiting_colors", "ready_to_publish"):
            raise ValueError(
                f"Job đang «{status}» — chỉ tạo ảnh khi đang nhập form (awaiting_input)."
            )
        payload = dict(state.get("payload") or {})
        if (payload.get("mode") or "").strip().lower() != "ai":
            raise ValueError("Chỉ dùng cho mode AI.")
        product_key = (
            (state.get("product_key") or "").strip()
            or ((state.get("studio") or {}).get("product_key") or "").strip()
            or new_manual_product_id()
        )
        studio = dict(state.get("studio") or _init_studio(payload, product_key=product_key))
        studio["product_key"] = product_key
        if not studio.get("ref_pool"):
            studio["ref_pool"] = _ref_pool_from_payload(payload)

        color_name = (name or "").strip()
        if kind_n == "color" and not color_name:
            raise ValueError("Tạo ảnh màu cần nhập tên màu.")

        if kind_n == "color":
            idx = len([c for c in (studio.get("colors") or []) if isinstance(c, dict) and c.get("img")])
        elif kind_n == "gallery":
            idx = len(studio.get("images") or [])
        elif kind_n == "detail":
            idx = len(studio.get("gallery") or [])
        else:
            idx = 0

        selected = [str(u).strip() for u in (ref_urls or []) if str(u).strip()]
        attach = (attach_url or "").strip()
        resolved = _resolve_selected_refs(studio, ref_urls=selected, attach_url=attach)
        if not resolved:
            raise ValueError("Chọn ít nhất 1 ảnh tham khảo hoặc gửi ảnh kèm.")

        slot = {
            "kind": kind_n,
            "index": idx,
            "name": color_name if kind_n == "color" else None,
            "url": None,
            "attempt": 0,
            "user_prompt": (prompt or "").strip(),
            "ref_urls": selected[:3],
            "attach_url": attach or None,
        }
        studio["current_slot"] = slot
        studio["phase"] = kind_n
        label = _slot_label(slot)
        state.update(
            {
                "product_key": product_key,
                "studio": studio,
                "status": "generating",
                "step": f"ai_{kind_n}",
                "message": f"Đang tạo {label}…",
                "progress": 25,
                "error": None,
                "worker_action": "generate_slot",
                "updated_at": _utcnow_iso(),
            }
        )
        persist_job(job_id, state)
    enqueue_manual_product_job(job_id, worker_action="generate_slot")
    return load_job(job_id) or state


def set_job_colors(job_id: str, colors: Any) -> Dict[str, Any]:
    """Tương thích cũ: lấy màu đầu → start generate color (dùng ảnh gốc làm ref)."""
    names = _normalize_color_name_list(colors)
    if not names:
        raise ValueError("Cần ít nhất 1 màu.")
    state = load_job(job_id) or {}
    studio = dict(state.get("studio") or {})
    refs = [
        str(item.get("url") or "").strip()
        for item in (studio.get("ref_pool") or [])
        if isinstance(item, dict) and (item.get("kind") or "") == "ref"
    ][:3]
    if not refs:
        payload = dict(state.get("payload") or {})
        refs = [str(u).strip() for u in (payload.get("ref_image_urls") or []) if str(u).strip()][:3]
    return start_studio_generate(
        job_id,
        kind="color",
        name=names[0],
        prompt="",
        ref_urls=refs,
        attach_url="",
    )


def approve_studio_image(job_id: str) -> Dict[str, Any]:
    """OK ảnh hiện tại → commit vào catalog + ref_pool → chờ form mốc tiếp (không auto-gen)."""
    with _WORKER_LOCK:
        state = load_job(job_id)
        if not state:
            raise ValueError("Không tìm thấy job")
        status = (state.get("status") or "").strip()
        if status not in ("awaiting_approval",):
            raise ValueError("Chỉ duyệt khi đang chờ duyệt ảnh (awaiting_approval).")
        studio = dict(state.get("studio") or {})
        slot = dict(studio.get("current_slot") or {})
        if not (slot.get("url") or "").strip():
            raise ValueError("Chưa có ảnh để duyệt — bấm Tạo lại trước.")
        kind = (slot.get("kind") or "color").strip()
        _commit_approved_slot(studio, slot)
        # Gợi ý mốc tiếp theo hành vi người dùng
        if kind == "color":
            studio["phase"] = "color"  # có thể thêm màu nữa hoặc chuyển gallery
        elif kind == "main":
            studio["phase"] = "gallery"
        elif kind == "gallery":
            studio["phase"] = "gallery"
        else:
            studio["phase"] = "detail"
        studio["current_slot"] = None
        _refresh_studio_hints(state, studio)
        n_colors = len([c for c in (studio.get("colors") or []) if isinstance(c, dict) and c.get("img")])
        msg = (
            f"Đã duyệt. Có {n_colors} màu — thêm màu khác, hoặc tạo gallery/chi tiết, hoặc Đăng."
            if kind == "color"
            else "Đã duyệt. Chọn mốc tiếp (gallery / chi tiết / ảnh chính) hoặc Đăng sản phẩm."
        )
        state.update(
            {
                "studio": studio,
                "status": "awaiting_input",
                "step": "awaiting_input",
                "message": msg,
                "progress": 55,
                "error": None,
                "worker_action": None,
                "updated_at": _utcnow_iso(),
            }
        )
        persist_job(job_id, state)
        return state


def regenerate_studio_image(
    job_id: str,
    *,
    prompt: Optional[str] = None,
    ref_urls: Optional[List[str]] = None,
    attach_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Tạo lại slot hiện tại — có thể sửa prompt / ref / ảnh kèm."""
    with _WORKER_LOCK:
        state = load_job(job_id)
        if not state:
            raise ValueError("Không tìm thấy job")
        status = (state.get("status") or "").strip()
        if status not in ("awaiting_approval", "failed"):
            raise ValueError("Chỉ tạo lại khi đang xem ảnh / lỗi gen.")
        studio = dict(state.get("studio") or {})
        slot = dict(studio.get("current_slot") or {})
        if not slot.get("kind"):
            raise ValueError("Không còn slot ảnh để tạo lại.")
        if prompt is not None:
            slot["user_prompt"] = str(prompt).strip()
        if ref_urls is not None:
            slot["ref_urls"] = [str(u).strip() for u in ref_urls if str(u).strip()][:3]
        if attach_url is not None:
            slot["attach_url"] = str(attach_url).strip() or None
        slot["url"] = None
        studio["current_slot"] = slot
        label = _slot_label(slot)
        state.update(
            {
                "studio": studio,
                "status": "generating",
                "step": f"ai_{slot.get('kind')}",
                "message": f"Đang tạo lại {label}…",
                "progress": 35,
                "error": None,
                "worker_action": "generate_slot",
                "updated_at": _utcnow_iso(),
            }
        )
        persist_job(job_id, state)
    enqueue_manual_product_job(job_id, worker_action="generate_slot")
    return load_job(job_id) or state


def publish_studio_job(job_id: str) -> Dict[str, Any]:
    """Đăng sớm hoặc sau khi đủ ảnh — DeepSeek + taxonomy + SP + Ladipage."""
    with _WORKER_LOCK:
        state = load_job(job_id)
        if not state:
            raise ValueError("Không tìm thấy job")
        status = (state.get("status") or "").strip()
        if status in ("done", "publishing", "generating", "queued"):
            if status == "done":
                return state
            raise ValueError(f"Job đang «{status}» — chờ xong rồi đăng.")
        if status not in (
            "awaiting_approval",
            "awaiting_input",
            "ready_to_publish",
            "failed",
            "awaiting_colors",
        ):
            raise ValueError("Chưa sẵn sàng đăng.")
        studio = dict(state.get("studio") or {})
        slot = dict(studio.get("current_slot") or {})
        if status == "awaiting_approval" and (slot.get("url") or "").strip():
            try:
                _commit_approved_slot(studio, slot)
                studio["current_slot"] = None
            except ValueError:
                pass
        if not _studio_can_publish(studio):
            raise ValueError("Cần ít nhất 1 ảnh đã duyệt (màu hoặc chính) trước khi đăng.")
        state.update(
            {
                "studio": studio,
                "status": "publishing",
                "step": "publishing",
                "message": "Đang đăng sản phẩm (DeepSeek + taxonomy + Ladipage)…",
                "progress": 75,
                "error": None,
                "worker_action": "publish",
                "updated_at": _utcnow_iso(),
            }
        )
        persist_job(job_id, state)
    enqueue_manual_product_job(job_id, worker_action="publish")
    return load_job(job_id) or state
