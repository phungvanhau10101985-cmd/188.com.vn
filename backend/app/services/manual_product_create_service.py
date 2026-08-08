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
from app.services.ladipage_ai_service import _guess_mime_from_url, generate_material_text
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


_VALID_STUDIO_ASPECT_RATIOS = frozenset(
    {"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}
)


def _normalize_studio_aspect_ratio(raw: Any) -> str:
    s = str(raw or "").strip()
    return s if s in _VALID_STUDIO_ASPECT_RATIOS else "1:1"


def _patch_studio_ai_plan(
    studio: Dict[str, Any],
    *,
    image_model: Optional[str] = None,
    aspect_ratio: Optional[str] = None,
) -> None:
    plan = dict(studio.get("plan") or {})
    if image_model is not None and str(image_model).strip():
        plan["image_model"] = str(image_model).strip()
    if aspect_ratio is not None:
        plan["aspect_ratio"] = _normalize_studio_aspect_ratio(aspect_ratio)
    studio["plan"] = plan


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
    aspect_ratio: Optional[str] = None,
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
    eff_aspect = _normalize_studio_aspect_ratio(aspect_ratio) if aspect_ratio else None
    if eff_size or eff_aspect:
        image_cfg: Dict[str, Any] = {}
        if eff_size:
            image_cfg["imageSize"] = eff_size
        if eff_aspect:
            image_cfg["aspectRatio"] = eff_aspect
        gen_cfg["imageConfig"] = image_cfg

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
        "Photorealistic commercial fashion photography, sharp focus on product, "
        "accurate neutral color reproduction faithful to reference (no filter, no LUT, no shifted white balance), "
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
    "Keep the SAME product design identity from references: silhouette, print/graphic placement, "
    "proportions, fabric texture type, garment construction (layers, skirt, shorts, sleeves), "
    "and exact neckline (V-neck / round / collarless / collared — match the sample; "
    "if the sample has NO collar, do NOT invent a shirt collar, lapel, polo collar, or folded collar). "
    "Do not invent a different SKU or change the product type."
)

# Màu #2+: fidelity chỉ theo ảnh mẫu khách — không lấy kiểu đồ từ ảnh màu #1 (face-lock).
_COLOR_FOLLOWON_FIDELITY = (
    "Garment identity MUST match the customer product-sample reference only: silhouette, cut, sleeves, "
    "neckline, length, print/pattern, fabric texture, and colors. "
    "NECKLINE LOCK: copy the product-sample neckline exactly — if that sample is collarless / V-neck / "
    "round neck without a collar stand, the output MUST stay collarless (no áo cổ bẻ, no lapel, no polo collar). "
    "Never borrow collar or neckline from the Color #1 face-lock photo. "
    "The Color #1 / face-lock reference must NOT contribute any clothing, colorway, or product design."
)

_COLOR_PRESERVE = (
    "Match ONLY the garment/print colors from the reference — same hue, saturation, brightness, undertone. "
    "Do not recolor to a prettier shade."
)

_STUDIO_NEW_PHOTO_BRIEF = (
    "GENERATE A COMPLETELY NEW professional e-commerce photograph from scratch — "
    "NOT an edit, collage, overlay, or copy-paste of the reference upload. "
    "The attached reference is for product identity and color sampling ONLY. "
    "NEVER reproduce from the reference photo: background (bed, quilt, wall, floor), hanger, hook, clip, "
    "original lighting, original camera angle, original crop, props, packaging, or any partial body part "
    "(leg, hand, face) visible in the customer upload. "
    "Output one clean, coherent catalog image following the shoot settings below."
)


def _studio_color_match_brief(
    state: Dict[str, Any],
    slot: Dict[str, Any],
    *,
    cname: str,
    color_index: int = 0,
) -> str:
    """Ảnh khách upload = mẫu SP (kiểu, màu, cắt may); màu #2+ chỉ lấy khuôn mặt từ ảnh màu #1."""
    # vision_* từ màu #1 mô tả SP cũ — không dùng cho màu #2+ (tránh gen nhầm kiểu đồ #1).
    vision_colors = (
        []
        if color_index >= 1
        else [str(c).strip() for c in (state.get("vision_colors") or []) if str(c).strip()]
    )
    vision_analysis = (
        "" if color_index >= 1 else str(state.get("vision_analysis") or "").strip()
    )
    ref_urls = [str(u).strip() for u in (slot.get("ref_urls") or []) if str(u).strip()]
    attach = str(slot.get("attach_url") or "").strip()
    pool = (state.get("studio") or {}).get("ref_pool") or []
    pool_by_url = {
        str(item.get("url") or "").strip(): str(item.get("kind") or "").strip()
        for item in pool
        if isinstance(item, dict) and str(item.get("url") or "").strip()
    }
    face_url = _first_approved_color_url(state.get("studio") or {}) if color_index >= 1 else ""
    color_ref_urls = [u for u in ref_urls if u and u != face_url]
    if attach and attach not in color_ref_urls:
        color_ref_urls.insert(0, attach)

    uses_customer_orig = any(pool_by_url.get(u) == "ref" for u in color_ref_urls) or (
        color_index <= 0 and bool((state.get("payload") or {}).get("ref_image_urls"))
    )

    if color_index >= 1 and face_url:
        lines = [
            "Reference order: image #1 = NEW customer product sample for THIS colorway "
            "(full garment: silhouette, cut, sleeves, neckline, print/pattern, fabric, colors). "
            "Image #2 = approved Color #1 catalog photo — FACE/HAIR/SKIN ONLY. "
            "CRITICAL: Ignore and discard ALL clothing worn in image #2 (including its collar/neckline); "
            "do not recolor or restyle the Color #1 garment. "
            "The output outfit must match image #1's product, worn by image #2's face.",
            "NECKLINE: follow image #1 only. If image #1 shows a collarless / V-neck / simple open neck "
            "with no shirt collar, do NOT add a folded collar (áo cổ bẻ) — that mistake often comes from "
            "copying clothing on image #2.",
            f"Colorway label «{cname}» is a hint only; follow the customer sample in image #1 if it conflicts.",
            "Do NOT paste, trace, photocomposite, or 'extend' either reference photo. "
            "Do NOT keep the sample background or hanger shot.",
            "This colorway may be a completely different product from Color #1 — not merely a recolor.",
        ]
        if uses_customer_orig or color_ref_urls:
            lines.append(
                "Customer upload (image #1) is the sole product authority: extract garment design + colors; "
                "discard its background/hanger/model body — keep only the Color #1 face identity from image #2."
            )
        return " ".join(lines)

    lines = [
        "PRODUCT SAMPLE: from the customer upload reference, reproduce this colorway's garment design — silhouette, cut, "
        "construction, print/pattern, trims, and fabric colors (hue, saturation, undertone). "
        f"Colorway label «{cname}» is a hint only; follow the uploaded sample if it conflicts.",
        "Do NOT paste, trace, photocomposite, or 'extend' the reference photo. Do NOT keep the reference background or hanger shot.",
        "Each colorway may use a DIFFERENT product sample upload — do not assume the same garment template as other colorways unless the upload shows it.",
    ]
    if uses_customer_orig:
        lines.insert(
            1,
            "Customer upload — treat as the authoritative product sample for this colorway: extract garment design + colors; "
            "discard background, hanger, and any model visible in that photo.",
        )
    if vision_analysis:
        lines.append(f"Product design to render (from vision): {vision_analysis[:500]}.")
    if vision_colors:
        lines.append(
            "Observed colors in upload: "
            + ", ".join(vision_colors[:8])
            + f" — map «{cname}» to the matching swatch."
        )
    return " ".join(lines)


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


STUDIO_MIN_COLOR_IMAGES = 1
STUDIO_MIN_GALLERY_IMAGES = 2
STUDIO_MIN_MATERIAL_IMAGES = 1


def _studio_color_count(studio: Dict[str, Any]) -> int:
    return len(
        [
            c
            for c in (studio.get("colors") or [])
            if isinstance(c, dict) and (c.get("img") or "").strip()
        ]
    )


def _studio_gallery_count(studio: Dict[str, Any]) -> int:
    return len([u for u in (studio.get("images") or []) if str(u or "").strip()])


def _studio_has_material_image(studio: Dict[str, Any]) -> bool:
    return bool((studio.get("material_image") or "").strip())


def _studio_publish_missing(studio: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    n_colors = _studio_color_count(studio)
    if n_colors < STUDIO_MIN_COLOR_IMAGES:
        missing.append(f"ít nhất {STUDIO_MIN_COLOR_IMAGES} ảnh màu ({n_colors}/{STUDIO_MIN_COLOR_IMAGES})")
    n_gallery = _studio_gallery_count(studio)
    if n_gallery < STUDIO_MIN_GALLERY_IMAGES:
        missing.append(f"ít nhất {STUDIO_MIN_GALLERY_IMAGES} ảnh gallery ({n_gallery}/{STUDIO_MIN_GALLERY_IMAGES})")
    if not _studio_has_material_image(studio):
        missing.append(f"{STUDIO_MIN_MATERIAL_IMAGES} ảnh chất liệu (0/{STUDIO_MIN_MATERIAL_IMAGES})")
    return missing


def _init_studio(payload: Dict[str, Any], *, product_key: str) -> Dict[str, Any]:
    g_count = max(
        STUDIO_MIN_GALLERY_IMAGES,
        min(12, int(payload.get("gallery_count") if payload.get("gallery_count") is not None else STUDIO_MIN_GALLERY_IMAGES)),
    )
    d_count = max(0, min(12, int(payload.get("detail_count") if payload.get("detail_count") is not None else 0)))
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
            "aspect_ratio": _normalize_studio_aspect_ratio(payload.get("aspect_ratio")),
        },
        "ref_pool": _ref_pool_from_payload(payload),
        "phase": "color",
        "suggested_prompt": "",
        "color_names": [],
        "colors": [],
        "main_image": "",
        "images": [],
        "gallery": [],
        "material_image": "",
        "material_callouts": [],
        "material_body": "",
        "current_slot": None,
        "can_publish": False,
        "next_actions": ["color"],
    }


def _studio_can_publish(studio: Dict[str, Any]) -> bool:
    return len(_studio_publish_missing(studio)) == 0


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
    """Giữ thứ tự ref_urls đã merge (màu #2+: mẫu SP trước, mặt #1 sau). Không tự chèn mẫu cũ từ pool khi đã có ref."""
    ordered: List[str] = []
    attach = (attach_url or "").strip()
    ref_list = [str(u).strip() for u in (ref_urls or []) if str(u).strip()]
    # Đã merge sẵn: giữ nguyên thứ tự (không prepend attach làm đảo face/product).
    if ref_list:
        if attach and attach not in ref_list:
            # attach mới chưa có trong list → đưa lên đầu (mẫu SP ưu tiên)
            ordered.append(attach)
        for u in ref_list:
            if u and u not in ordered:
                ordered.append(u)
            if len(ordered) >= 3:
                break
        return ordered[:3]
    if attach:
        ordered.append(attach)
    if ordered:
        return ordered[:3]
    # fallback: ảnh gốc trong pool (chỉ khi chưa có ref/attach)
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


def _first_approved_color_url(studio: Dict[str, Any]) -> str:
    for row in studio.get("colors") or []:
        if not isinstance(row, dict):
            continue
        u = (row.get("img") or "").strip()
        if u:
            return u
    return ""


def _approved_color_urls(studio: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for row in studio.get("colors") or []:
        if not isinstance(row, dict):
            continue
        u = (row.get("img") or "").strip()
        if u and u not in out:
            out.append(u)
    return out


def _merge_color_slot_refs(
    studio: Dict[str, Any],
    selected: List[str],
    *,
    attach_url: str = "",
    color_index: int = 0,
) -> List[str]:
    """Màu #1: ref do admin upload/chọn. Màu #2+: mẫu SP khách trước, khuôn mặt màu #1 sau."""
    picked = [str(u).strip() for u in (selected or []) if str(u).strip()]
    attach = (attach_url or "").strip()
    if color_index <= 0:
        merged: List[str] = []
        if attach:
            merged.append(attach)
        for u in picked:
            if u not in merged:
                merged.append(u)
        if not merged:
            raise ValueError("Ảnh màu đầu: upload ảnh mẫu sản phẩm cho màu này.")
        return merged[:3]
    face = _first_approved_color_url(studio)
    if not face:
        raise ValueError("Cần duyệt ảnh màu #1 trước khi tạo màu tiếp theo.")
    approved = set(_approved_color_urls(studio))
    # Có ảnh kèm: chỉ dùng đúng mẫu SP vừa upload (+ mặt #1). Không kèm mẫu màu cũ.
    if attach and attach != face and attach not in approved:
        return [attach, face]
    products: List[str] = []
    for u in picked:
        if not u or u == face or u in approved or u in products:
            continue
        # Bỏ mẫu SP màu #1 trong pool (kind=ref đã dùng cho màu trước) — chỉ nhận URL mới chọn.
        products.append(u)
        if len(products) >= 1:
            break
    if not products:
        raise ValueError(
            "Ảnh màu tiếp theo: upload ảnh mẫu sản phẩm (có thể khác mẫu/màu so với màu #1)."
        )
    # Thứ tự gửi AI: #1 mẫu SP khách (kiểu đồ), #2 ảnh màu #1 (chỉ mặt)
    return [products[0], face]


def _merge_customer_orig_refs(
    studio: Dict[str, Any],
    selected: List[str],
    *,
    for_color: bool = False,
    color_index: int = 0,
    attach_url: str = "",
) -> List[str]:
    """Tương thích: gallery/material dùng selected; color dùng _merge_color_slot_refs."""
    if for_color:
        return _merge_color_slot_refs(
            studio, selected, attach_url=attach_url, color_index=color_index
        )
    pool = studio.get("ref_pool") or []
    orig = [
        str(item.get("url") or "").strip()
        for item in pool
        if isinstance(item, dict) and (item.get("kind") or "") == "ref"
    ]
    orig = [u for u in orig if u]
    return (selected or orig)[:3]


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
    if kind == "material":
        return "ảnh chất liệu (Ladipage)"
    return "ảnh"


_DEFAULT_MATERIAL_CALLOUTS = ["Chất lượng cao", "Mềm mại thoải mái", "Bền theo thời gian"]


def _studio_ladipage_context(state: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(state.get("payload") or {})
    pname = (state.get("vision_product_name") or payload.get("product_name") or "").strip()
    material = (payload.get("material") or "").strip()
    return {
        "product_names": [pname] if pname else [],
        "dominant_material": material,
        "gender_hint": (payload.get("gender") or "").strip(),
        "is_category_landing": False,
    }


def _resolve_studio_material_copy(
    state: Dict[str, Any],
    material: str,
    *,
    notes: str = "",
) -> Dict[str, Any]:
    """DeepSeek: ưu điểm chất liệu + callout in trên ảnh."""
    material = (material or "").strip()
    if not material:
        return {"body": "", "callouts": list(_DEFAULT_MATERIAL_CALLOUTS)}
    try:
        data = generate_material_text(
            _studio_ladipage_context(state),
            material,
            custom_instruction=(notes or "").strip() or None,
        )
        if data and isinstance(data.get("callouts"), list) and data.get("callouts"):
            callouts = [str(x).strip() for x in data["callouts"] if str(x).strip()][:3]
            return {
                "body": str(data.get("body") or "").strip(),
                "callouts": callouts or list(_DEFAULT_MATERIAL_CALLOUTS),
            }
    except Exception as exc:
        logger.warning("studio material copy DeepSeek failed: %s", exc)
    return {"body": "", "callouts": list(_DEFAULT_MATERIAL_CALLOUTS)}


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
        color_idx = int(slot.get("index") or 0)
        color_brief = _studio_color_match_brief(state, slot, cname=cname, color_index=color_idx)
        attempt = int(slot.get("attempt") or 1)
        variation = ""
        if color_idx == 0 and attempt > 1:
            variation = (
                f" Regeneration attempt #{attempt}: MUST show a clearly DIFFERENT model identity "
                "(different face, hair, pose, stance, expression) while keeping the same "
                "configured age group, gender, and ethnicity — do NOT reuse the same person likeness "
                "as previous generations in this session."
            )
        elif color_idx >= 1:
            variation = (
                " MODEL FACE LOCK: Image #2 is the approved Color #1 catalog photo — copy ONLY that model's "
                "face, hair, and skin tone. Completely IGNORE the clothing AND neckline/collar on image #2. "
                "Image #1 is the NEW customer product sample — the output garment MUST match image #1 "
                "(may be a totally different style/cut/neckline from Color #1, not a recolor). "
                "Same person from image #2 wearing the product from image #1."
            )
        fidelity = _COLOR_FOLLOWON_FIDELITY if color_idx >= 1 else _FIDELITY
        if notes:
            fidelity = (
                f"{fidelity} "
                "ADMIN NOTES reinforce or refine structure (cut/collar/neckline/sleeve/length): "
                "obey them together with the product-sample neckline — never invent a collar the sample lacks."
            )
        base = (
            f"{_STUDIO_NEW_PHOTO_BRIEF} "
            "Create a premium e-commerce colorway photo — single clean image, worn or displayed correctly. "
            f"{color_brief}{variation} "
            f"{fidelity} "
            f"Shopper: {gender_txt}. {look}"
        )
    elif kind == "main":
        base = (
            f"{_STUDIO_NEW_PHOTO_BRIEF} "
            "Create a premium e-commerce HERO product photo that customers want to buy. "
            f"{_FIDELITY} {_COLOR_PRESERVE} "
            f"Shopper: {gender_txt}. Material feel: {material_txt}. Fashion style: {style_txt}. "
            f"{look} "
            "Square-friendly composition, product fills frame confidently, retail-ready quality."
        )
    elif kind == "gallery":
        angle = _GALLERY_ANGLES[idx % len(_GALLERY_ANGLES)]
        base = (
            f"{_STUDIO_NEW_PHOTO_BRIEF} "
            "Create another premium commercial catalog photo of the SAME product. "
            f"{_FIDELITY} {_COLOR_PRESERVE} "
            f"Camera/composition: {angle}. "
            f"Shopper: {gender_txt}. Style: {style_txt}. Material: {material_txt}. "
            f"{look}"
        )
    elif kind == "material":
        raw_callouts = slot.get("material_callouts") or studio.get("material_callouts") or []
        callouts = (
            [str(c).strip() for c in raw_callouts if str(c).strip()][:3]
            if isinstance(raw_callouts, list)
            else []
        )
        callout_str = (
            "; ".join(callouts)
            if callouts
            else "; ".join(_DEFAULT_MATERIAL_CALLOUTS)
        )
        base = (
            f"Chỉnh sửa ảnh sản phẩm đính kèm thành ảnh cận cảnh chất liệu «{material_txt}» "
            "chuyên nghiệp cho trang landing: zoom cận cảnh bề mặt/kết cấu chất liệu thật của đúng sản phẩm trong ảnh, "
            "ánh sáng studio đẹp, nền trung tính sang trọng. "
            f"{_FIDELITY}"
            "Trên ảnh in trực tiếp các nhãn/chú thích ngắn tiếng Việt (callout badges) nêu ưu điểm và điểm đáng mua "
            f"của loại chất liệu này — bố cục đẹp, không che vùng chất liệu chính: "
            f"{callout_str}. "
            "Không watermark, không chữ tiếng Trung, không logo hãng khác. Bố cục vuông, rõ nét, chuyên nghiệp."
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
        # Ghi chú admin + ảnh mẫu cùng hướng (vd không cổ) → siết chặt; nếu lệch ảnh mẫu thì theo ghi chú.
        base = (
            f"ADMIN STRUCTURE NOTE (HIGH PRIORITY): {notes}. "
            "Apply this to the garment structure (collar/neckline, sleeves, length, cut). "
            "If the product-sample photo already matches the note (e.g. both collarless), keep that structure — "
            "do NOT invent a shirt collar / áo cổ bẻ. "
            "If the note conflicts with the sample, follow the admin note for that detail only; "
            "keep fabric/print/color from the product sample elsewhere.\n"
            f"{base}"
        )
    return base


def _suggested_prompt_for_phase(state: Dict[str, Any], *, kind: str, name: str = "", index: int = 0) -> str:
    slot = {"kind": kind, "name": name, "index": index, "user_prompt": ""}
    return _build_studio_slot_prompt(state, slot)


def _studio_detail_count(studio: Dict[str, Any]) -> int:
    return len([u for u in (studio.get("gallery") or []) if str(u or "").strip()])


def _compute_next_actions(studio: Dict[str, Any]) -> List[str]:
    actions: List[str] = []
    if _studio_color_count(studio) < STUDIO_MIN_COLOR_IMAGES:
        actions.append("color")
    if _studio_gallery_count(studio) < STUDIO_MIN_GALLERY_IMAGES:
        actions.append("gallery")
    if not _studio_has_material_image(studio):
        actions.append("material")
    # Ảnh chi tiết: tuỳ chọn — gợi ý sau khi đủ gallery tối thiểu
    if (
        _studio_gallery_count(studio) >= STUDIO_MIN_GALLERY_IMAGES
        and _studio_detail_count(studio) == 0
    ):
        actions.append("detail")
    if _studio_can_publish(studio):
        actions.append("publish")
    if not actions:
        actions.append("color")
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
    elif phase == "material":
        idx = 0
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
            label=name[:80],
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
    elif kind == "material":
        studio["material_image"] = url
        callouts = slot.get("material_callouts") or studio.get("material_callouts") or []
        body = str(slot.get("material_body") or studio.get("material_body") or "").strip()
        if isinstance(callouts, list) and callouts:
            studio["material_callouts"] = [str(c).strip() for c in callouts if str(c).strip()][:3]
        if body:
            studio["material_body"] = body
        _add_to_ref_pool(
            studio, url=url, label="Ảnh chất liệu", kind="material", pool_id="material-0"
        )
    else:
        raise ValueError(f"Slot không hợp lệ: {kind}")
    studio["can_publish"] = _studio_can_publish(studio)


def job_public_view(state: Dict[str, Any]) -> Dict[str, Any]:
    """Shape trả API (kèm studio / vision)."""
    payload = dict(state.get("payload") or {})
    studio_raw = state.get("studio")
    studio_out = None
    if isinstance(studio_raw, dict):
        studio_out = dict(studio_raw)
        studio_out["can_publish"] = _studio_can_publish(studio_out)
        studio_out["next_actions"] = _compute_next_actions(studio_out)
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
        "studio": studio_out,
        "payload": payload,
        "mode": str(payload.get("mode") or "").strip() or None,
    }


def _parse_job_iso_ts(raw: Any) -> Optional[datetime]:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def maybe_recover_interrupted_job(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Worker chạy in-memory — mất điện/restart khiến job kẹt generating/queued.
    Khôi phục về trạng thái tương tác để admin tiếp tục.
    """
    status = str(state.get("status") or "").strip()
    if status not in ("generating", "queued", "publishing"):
        return state
    updated = _parse_job_iso_ts(state.get("updated_at"))
    if updated is None:
        return state
    age_sec = (datetime.now(timezone.utc) - updated.astimezone(timezone.utc)).total_seconds()
    if age_sec < 90:
        return state
    job_id = str(state.get("job_id") or "").strip()
    if not job_id:
        return state
    studio = dict(state.get("studio") or {})
    slot = dict(studio.get("current_slot") or {})
    payload = dict(state.get("payload") or {})
    mode = str(payload.get("mode") or "").strip().lower()
    if (slot.get("url") or "").strip():
        state["status"] = "awaiting_approval"
        state["message"] = (
            "Phiên bị gián đoạn (tắt máy/mất điện) — ảnh đã tạo vẫn còn. Bấm OK — Tiếp hoặc Tạo lại."
        )
    elif slot.get("kind"):
        state["status"] = "awaiting_approval"
        state["message"] = "Phiên bị gián đoạn — bấm Tạo lại để tiếp tục tạo ảnh."
    elif studio.get("ref_pool") or studio.get("colors"):
        state["status"] = "awaiting_input"
        state["message"] = "Đã khôi phục phiên Studio — tiếp tục chọn mốc và tạo ảnh."
    elif mode == "ai" and status in ("generating", "queued"):
        state["status"] = "awaiting_colors"
        state["message"] = "Phiên AI bị gián đoạn — kiểm tra tên/màu rồi tiếp tục Studio."
    else:
        state["status"] = "failed"
        state["message"] = "Phiên bị gián đoạn — bấm Thử lại hoặc tạo phiên mới."
    state["error"] = None
    state["worker_action"] = None
    state["updated_at"] = _utcnow_iso()
    persist_job(job_id, state)
    return state


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
        # Mode AI: không bắt buộc ảnh gốc lúc tạo job — ref theo từng màu ở Studio; đặt tên SEO khi đăng.
        refs = payload.get("ref_image_urls") or []
        if refs and len([u for u in refs if str(u).strip()]) > 3:
            raise ValueError("Mode AI tối đa 3 ảnh gốc (tuỳ chọn).")
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


def _extract_vision_name_json(text: str) -> Tuple[str, str, List[str], str]:
    """Parse JSON tên SP + màu chủ đạo + danh sách màu; nếu bị cắt MAX_TOKENS vẫn cố lấy ten_san_pham."""
    text = (text or "").strip()
    if not text:
        return "", "", [], ""
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
    ten_mau = str(parsed.get("ten_mau") or parsed.get("color_name") or "").strip()
    if not ten_mau:
        m3 = re.search(r'"ten_mau"\s*:\s*"((?:\\.|[^"\\])*)"', text)
        if m3:
            try:
                ten_mau = json.loads(f'"{m3.group(1)}"')
            except Exception:
                ten_mau = m3.group(1).replace('\\"', '"').strip()
    if not ten_mau and colors_out:
        ten_mau = colors_out[0]
    if len(ten_mau) > 40:
        ten_mau = ten_mau[:40].strip()
    if len(name) > 120:
        name = name[:120].strip()
    return name, analysis, colors_out, ten_mau


def _extract_color_name_json(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        parsed = json.loads(text[start:end] if start >= 0 and end > start else text)
    except Exception:
        parsed = {}
    name = str(parsed.get("ten_mau") or parsed.get("color_name") or parsed.get("mau") or "").strip()
    if not name:
        m = re.search(r'"ten_mau"\s*:\s*"((?:\\.|[^"\\])*)"', text)
        if m:
            try:
                name = json.loads(f'"{m.group(1)}"')
            except Exception:
                name = m.group(1).replace('\\"', '"').strip()
    if len(name) > 40:
        name = name[:40].strip()
    return name


def _dedupe_studio_color_name(studio: Dict[str, Any], name: str) -> str:
    base = (name or "").strip()[:40]
    if not base:
        return base
    existing = {
        str(c.get("name") or "").strip().lower()
        for c in (studio.get("colors") or [])
        if isinstance(c, dict) and str(c.get("name") or "").strip()
    }
    if base.lower() not in existing:
        return base
    for i in range(2, 24):
        candidate = f"{base} {i}"[:40].strip()
        if candidate.lower() not in existing:
            return candidate
    return f"{base} mới"[:40]


def name_colorway_from_reference_images(
    image_urls: List[str],
    *,
    admin_hint: str = "",
) -> Tuple[str, List[str]]:
    """Gemini vision: đọc màu SP chủ đạo từ ảnh mẫu khách upload → tên màu tiếng Việt."""
    warnings: List[str] = []
    api_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if len(api_key) < 10:
        warnings.append("vision_color: thiếu GEMINI_API_KEY.")
        return "", warnings

    urls = [str(u).strip() for u in (image_urls or []) if str(u).strip()][:3]
    if not urls:
        warnings.append("vision_color: thiếu ảnh mẫu.")
        return "", warnings

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
            warnings.append(f"vision_color: tải ảnh {idx + 1} lỗi: {exc}")

    if not image_parts:
        warnings.append("vision_color: không tải được ảnh.")
        return "", warnings

    model = (getattr(settings, "GEMINI_MODEL", "") or "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    model = model.replace("-latest", "")
    hint = (admin_hint or "").strip()
    prompt = (
        "Bạn nhận diện MÀU SẢN PHẨM CHỦ ĐẠO trên ảnh thời trang (màu vải/in chính của SP).\n"
        "Trả ĐÚNG một JSON ngắn (không markdown):\n"
        '{"ten_mau":"..."}\n'
        "Quy tắc ten_mau: tiếng Việt ngắn 1–4 từ (VD: Tím, Be nhạt, Xanh navy, Hồng phấn, Trắng kem). "
        "Không emoji, không mã, không mô tả dài."
    )
    if hint:
        prompt += f"\nGợi ý admin (chỉ dùng nếu khớp ảnh): {hint}."

    parts: List[Dict[str, Any]] = [{"text": prompt}, *image_parts]
    gem_url = f"{GEMINI_BASE_URL}/models/{model}:generateContent?key={api_key}"
    gen_cfg: Dict[str, Any] = {
        "temperature": 0.15,
        "maxOutputTokens": 256,
        "responseMimeType": "application/json",
        "thinkingConfig": {"thinkingBudget": 0},
    }

    def _call(cfg: Dict[str, Any]) -> Dict[str, Any]:
        return _gemini_request_json(
            gem_url,
            {"contents": [{"role": "user", "parts": parts}], "generationConfig": cfg},
            timeout=60,
        )

    try:
        body = _call(gen_cfg)
    except Exception as exc:
        cfg2 = dict(gen_cfg)
        cfg2.pop("thinkingConfig", None)
        try:
            body = _call(cfg2)
            warnings.append(f"vision_color: fallback config: {exc}")
        except Exception as exc2:
            warnings.append(f"vision_color: {exc2}")
            return "", warnings

    text = ""
    try:
        cands = body.get("candidates") or []
        if cands:
            resp_parts = ((cands[0].get("content") or {}).get("parts") or [])
            for p in resp_parts:
                if isinstance(p, dict) and p.get("text"):
                    text += str(p["text"])
    except Exception:
        text = ""
    color_name = _extract_color_name_json(text)
    if not color_name:
        warnings.append("vision_color: không đọc được tên màu từ ảnh.")
    return color_name, warnings


def _resolve_color_sample_urls_for_vision(
    studio: Dict[str, Any],
    refs: List[str],
    *,
    color_index: int,
) -> List[str]:
    """URL ảnh mẫu SP khách (bỏ ref mặt màu #1)."""
    face = _first_approved_color_url(studio) if color_index >= 1 else ""
    sample = [u for u in refs if u and u != face]
    return sample or list(refs[:1])


def _resolve_studio_color_name(
    state: Dict[str, Any],
    studio: Dict[str, Any],
    slot: Dict[str, Any],
    refs: List[str],
) -> Tuple[str, List[str], Dict[str, Any]]:
    """
    Admin gõ tên màu → dùng.
    Màu #1 (chưa có tên SP): 1 lần Gemini gộp tên SEO + tên màu từ ảnh mẫu.
    Màu #2+ hoặc đã có tên SP: chỉ Gemini đọc tên màu.
    Trả (tên_màu, warnings, state_patches).
    """
    warnings: List[str] = list(state.get("warnings") or [])
    patches: Dict[str, Any] = {}
    color_index = int(slot.get("index") or 0)
    admin_hint = (slot.get("name") or "").strip()
    if admin_hint:
        return _dedupe_studio_color_name(studio, admin_hint), warnings, patches

    payload = dict(state.get("payload") or {})
    admin_product = (payload.get("product_name") or payload.get("name") or "").strip()
    vision_product = (state.get("vision_product_name") or "").strip()
    sample_urls = _resolve_color_sample_urls_for_vision(studio, refs, color_index=color_index)
    use_combined_vision = color_index == 0 and not admin_product and not vision_product

    if use_combined_vision:
        vision_name, vision_analysis, vision_colors, ten_mau, vw = name_product_from_reference_images(
            sample_urls,
            gender=str(payload.get("gender") or "").strip(),
            material=str(payload.get("material") or "").strip(),
            style=str(payload.get("style") or "").strip(),
            notes=str(payload.get("notes") or "").strip(),
        )
        warnings.extend(vw)
        color_name = (ten_mau or "").strip()
        if vision_name:
            patches = {
                "vision_product_name": vision_name,
                "vision_analysis": vision_analysis or None,
                "vision_colors": vision_colors or [],
                "name_source": "gemini_vision",
                "payload": {**payload, "product_name": vision_name},
            }
        if not color_name and vision_colors:
            color_name = str(vision_colors[0] or "").strip()
    else:
        color_name, vw = name_colorway_from_reference_images(sample_urls)
        warnings.extend(vw)

    if not color_name:
        color_name = f"Màu {color_index + 1}"
        warnings.append(f"vision_color: fallback tên «{color_name}».")
    return _dedupe_studio_color_name(studio, color_name), warnings, patches


def name_product_from_reference_images(
    image_urls: List[str],
    *,
    gender: str = "",
    material: str = "",
    style: str = "",
    colors: Optional[List[str]] = None,
    notes: str = "",
) -> Tuple[str, str, List[str], str, List[str]]:
    """
    Gemini vision đọc 1–3 ảnh gốc → (tên SEO, phân tích, mau_sac[], ten_mau, warnings).
    """
    warnings: List[str] = []
    api_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if len(api_key) < 10:
        warnings.append("vision_name: thiếu GEMINI_API_KEY.")
        return "", "", [], "", warnings

    urls = [str(u).strip() for u in (image_urls or []) if str(u).strip()][:3]
    if not urls:
        warnings.append("vision_name: thiếu ảnh gốc.")
        return "", "", [], "", warnings

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
        return "", "", [], "", warnings

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
        "Đồng thời nhận MÀU SP CHỦ ĐẠO trên ảnh (ten_mau) và liệt kê thêm màu phụ nếu có (mau_sac).\n"
        "Quy tắc tên:\n"
        "- 45–90 ký tự, tự nhiên, có loại SP + đặc điểm bán (đối tượng, họa tiết, form).\n"
        "- Không mã SKU, không emoji, không dấu ngoặc thừa.\n"
        "- Không liệt kê hết size/màu ở cuối tên.\n"
        "- Có thể nêu motif/nhân vật in trên áo nếu nhìn thấy vì khách hay search.\n"
        f"Gợi ý admin — Giới tính: {gender_txt}; Chất liệu: {material_txt}; "
        f"Phong cách: {style_txt}; Màu gợi ý: {colors_txt}; Ghi chú: {notes_txt}.\n"
        "Trả ĐÚNG một JSON ngắn (không markdown, không giải thích):\n"
        '{"ten_san_pham":"...","ten_mau":"...","loai_san_pham":"...","diem_noi_bat":"...","mo_ta_ngan":"...","mau_sac":["..."]}\n'
        "Quy tắc ten_mau: tiếng Việt ngắn 1–4 từ (VD: Tím, Be nhạt, Xanh navy) — màu vải/in chính của SP trên ảnh."
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
                return "", "", [], "", warnings
        else:
            warnings.append(f"vision_name: {exc}")
            return "", "", [], "", warnings

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
        return "", "", [], "", warnings
    if "MAX" in finish.upper() and "TOKEN" in finish.upper():
        warnings.append("vision_name: output bị cắt MAX_TOKENS — đang parse phần còn lại.")

    name, analysis, colors_out, ten_mau = _extract_vision_name_json(text)
    if not name:
        warnings.append("vision_name: thiếu ten_san_pham trong JSON.")
        return "", analysis, colors_out, ten_mau, warnings
    return name, analysis, colors_out, ten_mau, warnings


def name_product_from_reference_image(
    image_url: str,
    *,
    gender: str = "",
    material: str = "",
    style: str = "",
    colors: Optional[List[str]] = None,
    notes: str = "",
) -> Tuple[str, str, List[str], str, List[str]]:
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


def _apply_studio_material_image_to_ladipage(
    db: Session,
    lp: Any,
    material_url: str,
    *,
    material_name: str = "",
    material_body: str = "",
    material_callouts: Optional[List[str]] = None,
) -> None:
    """Gắn ảnh + copy chất liệu Studio vào section material của Ladipage 1 SP."""
    url = (material_url or "").strip()
    if not url:
        return
    from app.models.ladipage import LadipageSection

    sections = (
        db.query(LadipageSection)
        .filter(LadipageSection.ladipage_id == int(lp.id))
        .all()
    )
    mat = (material_name or "").strip()
    body = (material_body or "").strip()
    callouts = [str(c).strip() for c in (material_callouts or []) if str(c).strip()][:3]
    for section in sections:
        if (section.section_type or "").strip() != "material":
            continue
        data = dict(section.data or {})
        data["image_url"] = url
        data["image_source"] = "product"
        data["image_object_position"] = str(data.get("image_object_position") or "").strip() or "50% 50%"
        if mat:
            data["material"] = mat
        if body:
            data["body"] = body
        if callouts:
            data["callouts"] = callouts
        section.data = data
        db.add(section)
        break
    db.flush()


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
    """Mode AI: khởi tạo studio → awaiting_input (tạo từng màu, đặt tên SEO khi đăng)."""
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
        admin_name = (payload.get("product_name") or payload.get("name") or "").strip()
        name_source = "admin" if admin_name else "pending_vision"

        _refresh_studio_hints({"payload": payload, "studio": studio}, studio)

        if admin_name:
            msg = (
                f"Tên SP: {admin_name[:80]}. "
                "Nhập màu đầu tiên + upload ảnh tham chiếu màu đó rồi bấm Tạo."
            )
        else:
            msg = (
                "Sang Studio: upload ảnh mẫu từng màu — AI tự đọc tên màu. "
                "Ảnh màu đầu: AI đọc luôn tên SEO sản phẩm từ ảnh."
            )

        _job_update(
            job_id,
            status="awaiting_input",
            step="awaiting_input",
            message=msg,
            progress=20,
            payload=payload,
            product_key=product_key,
            studio=studio,
            vision_product_name=admin_name or None,
            vision_analysis=None,
            vision_colors=[],
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
        aspect_ratio = _normalize_studio_aspect_ratio(plan.get("aspect_ratio"))
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

        payload = dict(state.get("payload") or {})
        if kind == "color":
            admin_color_before = (slot.get("name") or "").strip()
            resolved_name, name_warnings, vision_patches = _resolve_studio_color_name(
                state, studio, slot, refs
            )
            slot["name"] = resolved_name
            studio["current_slot"] = slot
            label = _slot_label(slot)
            if name_warnings:
                warnings_state = list(state.get("warnings") or [])
                warnings_state.extend(name_warnings)
                state = {**state, "warnings": warnings_state}
            product_title = (vision_patches.get("vision_product_name") or "").strip()
            payload_patch = vision_patches.get("payload")
            if vision_patches:
                patch_body = {k: v for k, v in vision_patches.items() if k != "payload"}
                state = {**state, **patch_body}
                if payload_patch:
                    state = {**state, "payload": payload_patch}
            if admin_color_before:
                color_msg = f"Màu «{resolved_name}» — đang tạo {label}…"
            elif product_title:
                color_msg = (
                    f"AI đọc tên SP «{product_title[:72]}» + màu «{resolved_name}» "
                    f"từ ảnh mẫu — đang tạo {label}…"
                )
            else:
                color_msg = f"AI đọc màu «{resolved_name}» từ ảnh mẫu — đang tạo {label}…"
            update_kw: Dict[str, Any] = {
                "message": color_msg,
                "progress": 28,
                "studio": studio,
                "warnings": state.get("warnings"),
            }
            if vision_patches:
                update_kw.update({k: v for k, v in vision_patches.items() if k != "payload"})
                if payload_patch:
                    update_kw["payload"] = payload_patch
            _job_update(job_id, **update_kw)
        if kind == "material":
            material_txt = (payload.get("material") or "").strip()
            copy = _resolve_studio_material_copy(
                state,
                material_txt,
                notes=str(slot.get("user_prompt") or "").strip(),
            )
            slot["material_callouts"] = copy.get("callouts") or []
            slot["material_body"] = copy.get("body") or ""
            studio["material_callouts"] = slot["material_callouts"]
            studio["material_body"] = slot["material_body"]
            studio["current_slot"] = slot
            _job_update(
                job_id,
                message=f"Đang tạo {label} — ưu điểm: {', '.join(slot['material_callouts'][:3])}…",
                studio=studio,
            )
        prompt = _build_studio_slot_prompt({**state, "studio": studio}, slot)
        raw = _gemini_edit_from_urls(
            refs,
            prompt,
            image_model=model_id,
            image_size=model_size,
            aspect_ratio=aspect_ratio,
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
        name_source = state.get("name_source") or ("admin" if admin_name else "pending_vision")

        if mode == "ai" and not admin_name and not vision_name:
            vision_refs: List[str] = []
            if (main_image or "").strip():
                vision_refs.append(main_image.strip())
            elif colors_payload:
                first_img = (colors_payload[0].get("img") or "").strip()
                if first_img:
                    vision_refs.append(first_img)
            if not vision_refs:
                raise RuntimeError("Chưa có ảnh màu để Gemini đặt tên SEO.")
            _job_update(
                job_id,
                status="publishing",
                step="vision_name",
                message="Gemini đọc lại ảnh màu để đặt tên SEO (fallback)…",
                progress=72,
                error=None,
            )
            color_names_for_vision = [str(c.get("name") or "").strip() for c in colors_payload if c.get("name")]
            vision_name, vision_analysis, vision_colors, _ten_mau, vw = name_product_from_reference_images(
                vision_refs[:1],
                gender=gender,
                material=material,
                style=style,
                colors=color_names_for_vision or _parse_colors(payload.get("colors")),
                notes=(payload.get("notes") or "").strip(),
            )
            warnings.extend(vw)
            if vision_name:
                name_source = "gemini_vision"
                payload = {**payload, "product_name": vision_name}
                state = {
                    **state,
                    "payload": payload,
                    "vision_product_name": vision_name,
                    "vision_analysis": vision_analysis or None,
                    "vision_colors": vision_colors or [],
                    "name_source": name_source,
                    "warnings": warnings,
                }
                persist_job(job_id, state)
            else:
                detail = "; ".join([w for w in vw if w][:3]) or "Gemini không trả tên hợp lệ."
                raise RuntimeError(
                    "Chưa đặt được tên SEO từ ảnh màu. "
                    f"Chi tiết: {detail} "
                    "Thử lại hoặc kiểm tra GEMINI_API_KEY."
                )

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

        studio_state = dict(state.get("studio") or {})
        material_image = (studio_state.get("material_image") or "").strip()
        if material_image:
            _apply_studio_material_image_to_ladipage(
                db,
                lp,
                material_image,
                material_name=material,
                material_body=str(studio_state.get("material_body") or "").strip(),
                material_callouts=studio_state.get("material_callouts") or [],
            )
            db.commit()
            db.refresh(lp)

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
    image_model: Optional[str] = None,
    aspect_ratio: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Tạo 1 ảnh theo mốc: color | main | gallery | detail | material.
    Khách chọn ref + (tuỳ chọn) ảnh kèm + prompt rồi mới gen.
    """
    kind_n = (kind or "").strip().lower()
    if kind_n not in ("color", "main", "gallery", "detail", "material"):
        raise ValueError("kind phải là color | main | gallery | detail | material.")
    with _WORKER_LOCK:
        state = load_job(job_id)
        if not state:
            raise ValueError("Không tìm thấy job")
        status = (state.get("status") or "").strip()
        if status not in ("awaiting_input", "awaiting_colors", "ready_to_publish"):
            raise ValueError(
                f"Job đang «{status}» — không thể tạo ảnh mới. "
                "Nếu đang xem ảnh vừa tạo, bấm «Tạo lại»; nếu đang gen, chờ vài giây."
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
        _patch_studio_ai_plan(studio, image_model=image_model, aspect_ratio=aspect_ratio)
        if not studio.get("ref_pool"):
            studio["ref_pool"] = _ref_pool_from_payload(payload)

        color_name = (name or "").strip()
        # Tên màu để trống: worker _resolve_studio_color_name đọc từ ảnh mẫu (Gemini vision).

        if kind_n == "color":
            idx = len([c for c in (studio.get("colors") or []) if isinstance(c, dict) and c.get("img")])
        elif kind_n == "gallery":
            idx = len(studio.get("images") or [])
        elif kind_n == "detail":
            idx = len(studio.get("gallery") or [])
        elif kind_n == "material":
            idx = 0
        else:
            idx = 0

        selected = [str(u).strip() for u in (ref_urls or []) if str(u).strip()]
        attach = (attach_url or "").strip()
        color_index = 0
        if kind_n == "color":
            color_index = len(
                [c for c in (studio.get("colors") or []) if isinstance(c, dict) and c.get("img")]
            )
            selected = _merge_customer_orig_refs(
                studio,
                selected,
                for_color=True,
                color_index=color_index,
                attach_url=attach,
            )
            if attach:
                _add_to_ref_pool(
                    studio,
                    url=attach,
                    label=f"Mẫu {color_name or 'SP'}"[:80],
                    kind="ref",
                    pool_id=f"color-ref-{color_index}-{len(studio.get('ref_pool') or [])}",
                )
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
            studio["phase"] = "color"
        elif kind == "main":
            studio["phase"] = "gallery"
        elif kind == "gallery":
            studio["phase"] = (
                "gallery"
                if _studio_gallery_count(studio) < STUDIO_MIN_GALLERY_IMAGES
                else ("material" if not _studio_has_material_image(studio) else "detail")
            )
        elif kind == "detail":
            studio["phase"] = "detail"
        elif kind == "material":
            studio["phase"] = "material"
        else:
            studio["phase"] = "gallery"
        studio["current_slot"] = None
        _refresh_studio_hints(state, studio)
        n_colors = _studio_color_count(studio)
        n_gallery = _studio_gallery_count(studio)
        n_detail = _studio_detail_count(studio)
        missing = _studio_publish_missing(studio)
        if _studio_can_publish(studio):
            msg = (
                "Đã duyệt — đủ ảnh màu, gallery và chất liệu. "
                f"Ảnh chi tiết tuỳ chọn ({n_detail}). Bấm «Đăng sản phẩm»."
            )
        elif kind == "color":
            msg = (
                f"Đã duyệt màu ({n_colors}/{STUDIO_MIN_COLOR_IMAGES}). "
                f"Tiếp: gallery ({n_gallery}/{STUDIO_MIN_GALLERY_IMAGES}), "
                f"ảnh chất liệu ({1 if _studio_has_material_image(studio) else 0}/{STUDIO_MIN_MATERIAL_IMAGES}). "
                "Ảnh chi tiết tuỳ chọn."
            )
        elif kind == "material":
            msg = (
                "Đã duyệt ảnh chất liệu. "
                + (
                    "Đủ điều kiện đăng — có thể thêm ảnh chi tiết (tuỳ chọn) rồi bấm «Đăng sản phẩm»."
                    if not missing
                    else f"Còn thiếu: {', '.join(missing)}."
                )
            )
        elif kind == "gallery":
            msg = (
                f"Đã duyệt gallery ({n_gallery}/{STUDIO_MIN_GALLERY_IMAGES}). "
                + (
                    "Đủ gallery — tiếp ảnh chất liệu (bắt buộc) hoặc ảnh chi tiết (tuỳ chọn)."
                    if not missing and _studio_gallery_count(studio) >= STUDIO_MIN_GALLERY_IMAGES
                    else (
                        "Đủ điều kiện đăng — có thể thêm ảnh chi tiết (tuỳ chọn)."
                        if not missing
                        else f"Còn thiếu: {', '.join(missing)}."
                    )
                )
            )
        elif kind == "detail":
            msg = (
                f"Đã duyệt ảnh chi tiết ({n_detail}). "
                + (
                    "Đủ điều kiện đăng — bấm «Đăng sản phẩm»."
                    if not missing
                    else f"Còn thiếu: {', '.join(missing)}."
                )
            )
        else:
            msg = f"Đã duyệt. Còn thiếu: {', '.join(missing)}." if missing else "Đã duyệt — có thể đăng sản phẩm."
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


def adopt_studio_images(
    job_id: str,
    *,
    kind: str,
    urls: List[str],
) -> Dict[str, Any]:
    """
    Dùng ảnh đã có trong pool (ảnh màu / gallery / chi tiết / ref…) làm ảnh gallery hoặc chi tiết
    — không gen AI. kind: gallery | detail | material.
    """
    kind_n = (kind or "").strip().lower()
    if kind_n not in ("gallery", "detail", "material"):
        raise ValueError("kind phải là gallery | detail | material.")
    picked = [str(u).strip() for u in (urls or []) if str(u).strip()]
    if not picked:
        raise ValueError("Chọn ít nhất 1 ảnh đã tạo để dùng.")
    if kind_n == "material":
        picked = picked[:1]
    else:
        picked = picked[:6]

    with _WORKER_LOCK:
        state = load_job(job_id)
        if not state:
            raise ValueError("Không tìm thấy job")
        status = (state.get("status") or "").strip()
        if status not in ("awaiting_input", "awaiting_colors", "ready_to_publish"):
            raise ValueError(
                f"Job đang «{status}» — chỉ chọn ảnh khi đang chờ tạo/duyệt mốc tiếp."
            )
        payload = dict(state.get("payload") or {})
        if (payload.get("mode") or "").strip().lower() != "ai":
            raise ValueError("Chỉ dùng cho mode AI.")
        studio = dict(state.get("studio") or {})
        pool_urls = {
            str(item.get("url") or "").strip()
            for item in (studio.get("ref_pool") or [])
            if isinstance(item, dict) and str(item.get("url") or "").strip()
        }
        for row in studio.get("colors") or []:
            if isinstance(row, dict):
                u = str(row.get("img") or "").strip()
                if u:
                    pool_urls.add(u)
        for u in list(studio.get("images") or []) + list(studio.get("gallery") or []):
            s = str(u or "").strip()
            if s:
                pool_urls.add(s)
        mat = str(studio.get("material_image") or "").strip()
        if mat:
            pool_urls.add(mat)

        unknown = [u for u in picked if u not in pool_urls]
        if unknown:
            raise ValueError("Chỉ chọn ảnh đã có trong Studio (ảnh màu / ảnh đã tạo).")

        added = 0
        if kind_n == "gallery":
            existing = {str(x).strip() for x in (studio.get("images") or []) if str(x or "").strip()}
            images = list(studio.get("images") or [])
            for u in picked:
                if u in existing:
                    continue
                images.append(u)
                existing.add(u)
                i = len(images) - 1
                _add_to_ref_pool(
                    studio, url=u, label=f"Gallery {i + 1}", kind="gallery", pool_id=f"gallery-{i}"
                )
                added += 1
            studio["images"] = images
            studio["phase"] = "gallery"
        elif kind_n == "detail":
            existing = {str(x).strip() for x in (studio.get("gallery") or []) if str(x or "").strip()}
            details = list(studio.get("gallery") or [])
            for u in picked:
                if u in existing:
                    continue
                details.append(u)
                existing.add(u)
                i = len(details) - 1
                _add_to_ref_pool(
                    studio, url=u, label=f"Chi tiết {i + 1}", kind="detail", pool_id=f"detail-{i}"
                )
                added += 1
            studio["gallery"] = details
            studio["phase"] = "detail"
        else:
            studio["material_image"] = picked[0]
            _add_to_ref_pool(
                studio, url=picked[0], label="Ảnh chất liệu", kind="material", pool_id="material-0"
            )
            added = 1
            studio["phase"] = "material"

        if added == 0:
            raise ValueError("Ảnh đã có trong mục này — chọn ảnh khác hoặc tạo mới.")

        studio["current_slot"] = None
        _refresh_studio_hints(state, studio)
        label = (
            "gallery"
            if kind_n == "gallery"
            else ("chi tiết" if kind_n == "detail" else "chất liệu")
        )
        missing = _studio_publish_missing(studio)
        msg = (
            f"Đã thêm {added} ảnh {label} từ ảnh đã tạo."
            + (
                " Đủ điều kiện đăng — bấm «Đăng sản phẩm»."
                if not missing
                else f" Còn thiếu: {', '.join(missing)}."
            )
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
    image_model: Optional[str] = None,
    aspect_ratio: Optional[str] = None,
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
        _patch_studio_ai_plan(studio, image_model=image_model, aspect_ratio=aspect_ratio)
        slot = dict(studio.get("current_slot") or {})
        if not slot.get("kind"):
            raise ValueError("Không còn slot ảnh để tạo lại.")
        if prompt is not None:
            slot["user_prompt"] = str(prompt).strip()
        slot_attach = str(slot.get("attach_url") or attach_url or "").strip()
        if ref_urls is not None:
            picked = [str(u).strip() for u in ref_urls if str(u).strip()][:3]
            if (slot.get("kind") or "").strip() == "color":
                color_index = int(slot.get("index") or 0)
                picked = _merge_customer_orig_refs(
                    studio,
                    picked,
                    for_color=True,
                    color_index=color_index,
                    attach_url=slot_attach,
                )
            slot["ref_urls"] = picked
        elif (slot.get("kind") or "").strip() == "color":
            color_index = int(slot.get("index") or 0)
            slot["ref_urls"] = _merge_customer_orig_refs(
                studio,
                [str(u).strip() for u in (slot.get("ref_urls") or []) if str(u).strip()],
                for_color=True,
                color_index=color_index,
                attach_url=slot_attach,
            )
        if attach_url is not None:
            slot["attach_url"] = str(attach_url).strip() or None
            if (slot.get("kind") or "").strip() == "color":
                color_index = int(slot.get("index") or 0)
                slot["ref_urls"] = _merge_customer_orig_refs(
                    studio,
                    [str(u).strip() for u in (slot.get("ref_urls") or []) if str(u).strip()],
                    for_color=True,
                    color_index=color_index,
                    attach_url=str(attach_url).strip(),
                )
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
            missing = _studio_publish_missing(studio)
            raise ValueError(
                "Chưa đủ ảnh để đăng — cần "
                + ", ".join(missing)
                + "."
            )
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
