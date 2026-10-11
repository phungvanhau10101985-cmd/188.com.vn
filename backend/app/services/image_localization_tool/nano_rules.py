"""Hành vi bản địa hóa ảnh khớp nanoai.vn (classifier, engine, prompt, hậu kiểm, kho sheet)."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Sequence

LANGUAGE_LABELS = {
    "vi": "Vietnamese",
    "en": "English",
    "th": "Thai",
    "id": "Indonesian",
}

IMAGE_LOC_COMPLEX_KEYWORDS = [
    "规格", "参数", "尺寸表", "型号", "技术参数",
    "table", "chart", "diagram", "specification",
    "洗涤说明", "洗涤方式", "洗涤标识", "洗水唛",
    "衣物护理", "面料保养", "WASHING INSTRUCTION",
]

IMAGE_LOC_LAUNDRY_KEYWORDS = [
    "洗涤", "清洗", "保养", "护理", "清洁",
    "水洗", "干洗", "手洗", "机洗", "水温",
    "晾干", "风干", "阴干", "烘干", "熨烫", "漂白",
    "洗水唛", "洗涤标识", "洗标", "衣物护理", "面料保养",
    "洗涤说明", "洗涤方式", "洗涤建议", "洗涤小贴士",
    "WASHING", "CARE LABEL", "WASHING LABEL",
    "HAND WASH", "MACHINE WASH", "DRY CLEAN",
    "DO NOT BLEACH", "DO NOT IRON",
]

IMAGE_LOC_FACTORY_INTRO_KEYWORDS = [
    "源头工厂", "实力工厂", "工厂", "生产车间", "车间",
    "制鞋团队", "设计团队", "开发设计团队",
    "出货品质严控", "品质严控", "鞋业", "品控", "质检",
]

IMAGE_LOC_URGENT_DELETE_KEYWORDS = [
    "荐", "退", "价", "换", "Click", "推", "热卖",
    "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026", "2027", "2028", "2029", "2030",
    "一件代发", "一手货源", "货源充足", "大量现货", "批发现货", "批发价", "批发商",
    "清仓处理", "xả kho", "thanh lý", "大量招实体", "招网店", "招微商", "招代理",
    "网店代理", "微商代理", "实体店代理", "未经授权", "盗用图片", "投诉原图",
    "我公司", "本公司", "公司投诉", "本店所有", "本店货源", "本店产品",
    "价格优惠", "量大从优", "量大价优", "价格表", "báo giá", "报价单", "价目表",
    "批发价格", "优惠价格", "关于退换", "拒收货物", "签收须知", "概不负责",
    "特此声明", "郑重声明", "七天退换", "7天退换", "品质保证",
    "当天发货", "当天发出", "微信联系", "QQ联系", "电话联系", "手机号码", "热线电话",
    "免费送货", "miễn phí", "free ship", "更优惠", "立减", "满减", "折扣", "促销",
    "特价", "秒杀", "抢先购", "淘金币", "消费券", "优惠券", "叠加优惠", "叠加消费券",
    "下单立减", "官方立减", "折上折", "更划算", "券后价",
    "618抢先购", "618抢先", "618大促", "双11", "双十一", "双12", "双十二", "百亿补贴",
    "限时优惠", "限时特价", "限时抢购", "限时秒杀", "热卖促销", "促销价", "活动价",
    "购物津贴", "红包", "点击进入", "立即购买", "BUY NOW", "购买链接",
    "热卖推荐", "爆款推荐", "新品推荐", "ON SALE", "BIG SALE", "HOT SALE",
    "DISCOUNT", "PROMOTION", "SPECIAL OFFER", "NEW ARRIVAL", "BEST SELLER", "TOP SELLER",
    "生产日期", "出厂日期", "生产年份", "年份标注", "库存处理", "积压库存",
    "尾货清仓", "清库存", "老款式", "旧款式", "过季款", "下架款", "停产款", "停售款",
    "不再生产", "Click to buy", "Click here", "推荐购买", "热门推荐",
]

IMAGE_LOC_SIZE_TABLE_TITLE_PATTERNS = [
    "尺码表", "尺寸表", "尺码对照表", "尺寸对照表", "选择尺码", "选尺码",
    "sizechart", "sizetable", "sizeguide",
]

IMAGE_LOC_SIZE_LABELS = [
    "胸围", "腰围", "臀围", "肩宽", "衣长", "袖长", "裤长", "裙长",
    "身高", "体重", "脚长", "内长", "鞋码", "欧码", "码数",
    "chest", "waist", "hip", "shoulder", "length", "sleeve", "height", "weight", "footlength",
]

IMAGE_LOC_LAUNDRY_STRONG_PATTERNS = [
    "洗涤说明", "洗涤方式", "洗涤建议", "洗涤小贴士", "洗涤标识",
    "洗水唛", "洗标", "护理说明", "washinginstruction", "carelabel", "washinglabel",
]

IMAGE_LOC_DOMAIN_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z]{2,})+(?:/\S*)?",
    re.IGNORECASE,
)
HANZI_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")
_REMOVE_MODEL = (
    " Erase only the fashion model photograph: face, hair, body, and clothing. "
    "Fill only that photo area with the surrounding plain background. "
    "Replace each Chinese text string with its translation in the same position and size. "
    "Do not keep the original Chinese beside, above, or under the translation. "
    "Do not add a second copy of any line. "
    "Do not change centimeter measurements or bust, waist, and hip numbers. "
    "Still convert 斤 body weight to kilograms as instructed."
)
_STRIP_PHOTOS = (
    " Erase the fashion model photograph: face, hair, body, and clothing on the person. "
    "Also erase product photographs: the garment on a hanger, flat lay, mannequin, and fabric close-ups. "
    "Fill those photo areas with the surrounding plain background. "
    "Keep the size table, centimeter measurements, size labels, product specification text, "
    "laundry icons, and care instruction text. "
    "Replace each Chinese text string with its translation in the same position and size. "
    "Do not keep the original Chinese beside, above, or under the translation. "
    "Do not add a second copy of any line. "
    "Do not invent measurements. "
    "Do not change centimeter measurements or bust, waist, and hip numbers. "
    "Still convert 斤 body weight to kilograms as instructed."
)


def language_prompt(language: str, remove_model: bool = False, strip_photos: bool = False) -> str:
    target = LANGUAGE_LABELS.get((language or "vi").strip().lower(), language or "Vietnamese")
    if strip_photos:
        remove = _STRIP_PHOTOS
    elif remove_model:
        remove = _REMOVE_MODEL
    else:
        remove = ""
    return (
        "ROLE: E-commerce Image Localization Agent\n\n"
        f"Translate every Chinese text element in the attached product image into {target}. "
        "Preserve product details, layout, dimensions, aspect ratio, text placement, original colors, and image quality. "
        "Remove website URLs and domains from the image. "
        "Convert every Chinese weight to kilograms: 1 斤 = 0.5 kg. "
        "A 体重 column on a Chinese size chart or try-on table is in 斤 when the cell has no kg label; "
        "replace each of those numbers with kilograms and write kg. Example: 94 斤 becomes 47 kg. "
        f"Do not convert centimeters or bust, waist, and hip measurements.{remove} "
        "Return only the processed image file, with no explanation."
    )


def select_localization_engine(
    *,
    classification: str,
    allows_ai: bool,
    gemini_mode: str = "openai",
    has_size_or_laundry: bool = False,
    force_ai: bool = False,
) -> str:
    """delete | keep | local | ai. Bật AI thì mọi ảnh còn lại đi GPT; tắt AI thì vẽ local."""
    del gemini_mode, has_size_or_laundry, force_ai
    if classification == "delete":
        return "delete"
    if classification == "keep":
        return "keep"
    if not allows_ai:
        return "local"
    return "ai"


def image_loc_gpt_verify_attempts() -> int:
    """Số lần tạo lại ảnh khi hậu kiểm còn mực loang. Hết lần thì dừng job."""
    raw = (os.getenv("IMAGE_LOCALIZATION_GPT_VERIFY_ATTEMPTS") or "2").strip()
    try:
        value = int(raw)
    except ValueError:
        return 2
    return max(1, min(5, value))


def image_loc_ink_bleed_model() -> str:
    return (os.getenv("IMAGE_LOCALIZATION_INK_BLEED_MODEL") or "gemini-3.5-flash-lite").strip() or "gemini-3.5-flash-lite"


INK_BLEED_PROMPT = (
    "Look only for ink bleed on the printed text: strokes that smear, a gray or colored halo around letters, "
    "or color running into the background past the letter edge. "
    "Normal anti-aliasing and a flat filled background are not bleed.\n"
    'Return JSON only: {"bleed":false,"where":""}\n'
    'If bleed is true, "where" is a short place such as "size table" or "laundry text".'
)


def is_real_chinese_hanzi(char: str) -> bool:
    if not char or len(char) != 1:
        return False
    cp = ord(char)
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0xF900 <= cp <= 0xFAFF
        or 0x20000 <= cp <= 0x2A6DF
    )


def count_hanzi(text: str) -> int:
    return sum(1 for ch in text or "" if is_real_chinese_hanzi(ch))


def has_chinese_text(text: str) -> bool:
    return bool(HANZI_RE.search(text or ""))


def convert_jin_weight_text(text: str) -> str:
    def _repl(match: re.Match) -> str:
        import math

        raw = float(match.group(1)) * 0.5 * 100
        rounded = math.floor(raw + 0.5) if raw >= 0 else math.ceil(raw - 0.5)
        kg = rounded / 100
        shown = f"{kg:.2f}".rstrip("0").rstrip(".")
        return f"{shown} kg"

    return re.sub(r"(\d+(?:\.\d+)?)\s*斤", _repl, text or "")


def _as_blocks(blocks: Sequence[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in blocks or []:
        if isinstance(item, dict):
            text = str(item.get("text") or "")
            bbox = item.get("bbox") or []
            layout_only = bool(item.get("layoutOnly") or item.get("layout_only"))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            text = str(item[0] or "")
            bbox = item[1] or []
            layout_only = False
        else:
            continue
        try:
            box = [int(float(v)) for v in list(bbox)[:4]]
        except (TypeError, ValueError):
            box = []
        if len(box) < 4:
            box = [0, 0, 0, 0]
        row = {"text": text, "bbox": box}
        if layout_only:
            row["layoutOnly"] = True
        out.append(row)
    return out


def _compact_text(texts: Sequence[str]) -> str:
    return re.sub(r"[\s\u3000:_：\-|/]+", "", "\n".join(texts).lower())


def strip_factory_intro_text(text: str) -> Dict[str, Any]:
    keys = sorted(
        [key for key in IMAGE_LOC_FACTORY_INTRO_KEYWORDS if key and key in (text or "")],
        key=len,
        reverse=True,
    )
    if not keys:
        return {"matched": False, "text": text}
    next_text = text
    for key in keys:
        next_text = next_text.replace(key, " ")
    next_text = re.sub(r"\s+", " ", next_text)
    next_text = re.sub(r"^[\s:：,，、|/／\-]+|[\s:：,，、|/／\-]+$", "", next_text).strip()
    return {"matched": True, "text": next_text}


def has_size_table_context(blocks: Sequence[Any]) -> bool:
    rows = _as_blocks(blocks)
    texts = [row["text"] for row in rows if str(row["text"]).strip()]
    if not texts:
        return False
    compact = _compact_text(texts)
    if any(pattern in compact for pattern in IMAGE_LOC_SIZE_TABLE_TITLE_PATTERNS):
        return True
    label_count = sum(1 for label in IMAGE_LOC_SIZE_LABELS if label in compact)
    size_token_count = 0
    size_re = re.compile(
        r"^(?:xxxs|xxs|xs|s|m|l|xl|xxl|xxxl|xxxxl|\d{2,3})(?:[-/](?:xxxs|xxs|xs|s|m|l|xl|xxl|xxxl|xxxxl|\d{2,3}))*$"
    )
    measure_re = re.compile(r"^\d+(?:[.,]\d+)?(?:cm|mm|kg|g|斤)?$")
    for text in texts:
        token = re.sub(r"[\s\u3000]+", "", text.lower())
        if size_re.match(token) or measure_re.match(token):
            size_token_count += 1
    combined = "\n".join(texts).lower()
    has_size_keyword = any(key in compact for key in ("尺码", "尺寸", "size"))
    has_unit = bool(re.search(r"(?:cm|厘米|mm|kg|斤)", combined, re.IGNORECASE))
    if has_size_keyword and label_count >= 1 and size_token_count >= 3:
        return True
    if label_count >= 2 and size_token_count >= 5:
        return True
    return label_count >= 2 and has_unit and size_token_count >= 3


def has_laundry_care_context(blocks: Sequence[Any]) -> bool:
    rows = _as_blocks(blocks)
    texts = [row["text"] for row in rows if str(row["text"]).strip()]
    if not texts:
        return False
    compact = _compact_text(texts)
    if any(pattern in compact for pattern in IMAGE_LOC_LAUNDRY_STRONG_PATTERNS):
        return True
    detected = set()
    for text in texts:
        lowered = text.lower()
        for keyword in IMAGE_LOC_LAUNDRY_KEYWORDS:
            if keyword in text or keyword.lower() in lowered:
                detected.add(keyword)
    if len(detected) < 2:
        return False
    return bool(re.search(r"手洗|机洗|水洗|干洗|漂白|熨烫|烘干|handwash|machinewash|dryclean|bleach|iron|tumbledry", compact))


def is_laundry_instruction_image(blocks: Sequence[Any]) -> bool:
    if has_laundry_care_context(blocks):
        return True
    return any(
        any(keyword in (row["text"] or "") for keyword in IMAGE_LOC_LAUNDRY_KEYWORDS)
        for row in _as_blocks(blocks)
    )


def image_loc_sheet_kinds(blocks: Sequence[Any]) -> List[str]:
    kinds: List[str] = []
    if has_size_table_context(blocks):
        kinds.append("size")
    if is_laundry_instruction_image(blocks):
        kinds.append("laundry")
    return kinds


def apparel_sheet_kinds(blocks: Sequence[Any]) -> List[str]:
    """Bảng size hoặc hướng dẫn giặt đủ ngữ cảnh. Một chữ giặt lẻ không tính."""
    kinds: List[str] = []
    if has_size_table_context(blocks):
        kinds.append("size")
    if has_laundry_care_context(blocks):
        kinds.append("laundry")
    return kinds


def resolve_stored_image_loc_sheet(kinds: Sequence[str], stored: Dict[str, str]) -> Optional[str]:
    if not kinds:
        return None
    urls = [str((stored or {}).get(kind) or "").strip() for kind in kinds]
    if any(not url for url in urls):
        return None
    unique = list(dict.fromkeys(urls))
    return unique[0] if len(unique) == 1 else None


def _block_has_return_cluster(text: str) -> bool:
    return "退" in (text or "")


def _urgent_delete_hit(text: str) -> Optional[str]:
    raw = text or ""
    lowered = raw.lower()
    for keyword in IMAGE_LOC_URGENT_DELETE_KEYWORDS:
        if not keyword:
            continue
        if len(keyword) == 1:
            if keyword in raw:
                return keyword
            continue
        if keyword in raw or keyword.lower() in lowered:
            return keyword
    return None


def _contains_complex_keyword(blocks: Sequence[Dict[str, Any]]) -> Optional[str]:
    for block in blocks:
        text = block.get("text") or ""
        lowered = text.lower()
        for keyword in IMAGE_LOC_COMPLEX_KEYWORDS:
            if keyword in text or keyword.lower() in lowered:
                return keyword
    return None


def _overlap_ratio(blocks: Sequence[Dict[str, Any]]) -> float:
    hanzi = [block for block in blocks if has_chinese_text(block.get("text") or "")]
    if len(hanzi) < 2:
        return 0.0
    overlap_total = 0.0
    overlap_count = 0
    for i, left in enumerate(hanzi):
        a = left["bbox"]
        for right in hanzi[i + 1 :]:
            b = right["bbox"]
            ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
            iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
            inter = ix * iy
            area_a = max(1, (a[2] - a[0]) * (a[3] - a[1]))
            area_b = max(1, (b[2] - b[0]) * (b[3] - b[1]))
            if inter > 0:
                overlap_total += inter / min(area_a, area_b)
                overlap_count += 1
    return overlap_total / overlap_count if overlap_count else 0.0


def classify_image(
    blocks: Sequence[Any],
    _ignore: Sequence[Any] = (),
    _original_url: str = "",
) -> Dict[str, Any]:
    del _ignore, _original_url
    nonempty = [block for block in _as_blocks(blocks) if str(block.get("text") or "").strip()]
    for block in nonempty:
        if _block_has_return_cluster(block.get("text") or ""):
            continue
        hit = _urgent_delete_hit(block.get("text") or "")
        if hit:
            return {
                "type": "delete",
                "reason": f"URGENT DELETE: {hit}",
                "details": {
                    "detected_keyword": hit,
                    "text_snippet": str(block.get("text") or "")[:100],
                    "urgent_delete": True,
                },
            }
    total_hanzi = sum(count_hanzi(block.get("text") or "") for block in nonempty)
    if total_hanzi < 2:
        return {
            "type": "keep",
            "reason": (
                "Không có chữ Hán (chỉ có Latin/số/ký tự thông thường)"
                if total_hanzi == 0
                else f"Chỉ có {total_hanzi} ký tự Hán, cần ít nhất 2 ký tự"
            ),
            "details": {"hanzi_count": total_hanzi, "has_sufficient_hanzi": False, "is_clean": True},
        }
    laundry_kw = next(
        (
            keyword
            for block in nonempty
            for keyword in IMAGE_LOC_LAUNDRY_KEYWORDS
            if keyword in (block.get("text") or "")
        ),
        None,
    )
    if laundry_kw or has_laundry_care_context(nonempty):
        return {
            "type": "gemini",
            "reason": f"Chứa từ khóa hướng dẫn giặt tẩy: {laundry_kw or 'laundry'} - {total_hanzi} Hán tự",
            "details": {
                "laundry_keyword": laundry_kw or "laundry",
                "hanzi_count": total_hanzi,
                "has_laundry_care": True,
            },
        }
    overlap = _overlap_ratio(nonempty)
    if overlap > 0.05:
        return {
            "type": "gemini",
            "reason": f"Chữ Hán bị đè nghiêm trọng ({overlap * 100:.1f}% > 5%) - {total_hanzi} Hán tự",
            "details": {"overlap_ratio": overlap, "hanzi_count": total_hanzi, "has_overlap": True},
        }
    complex_kw = _contains_complex_keyword(nonempty)
    if complex_kw:
        return {
            "type": "gemini",
            "reason": f"Chứa nội dung phức tạp: {complex_kw} - {total_hanzi} Hán tự",
            "details": {"complex_keyword": complex_kw, "hanzi_count": total_hanzi},
        }
    return {
        "type": "local",
        "reason": f"Ảnh nhiều chữ Hán thông thường ({len(nonempty)} blocks, {total_hanzi} Hán tự, không bị đè, không phức tạp)",
        "details": {"text_blocks": len(nonempty), "hanzi_count": total_hanzi, "is_normal_chinese": True},
    }


def _cluster_sorted_edges(values: Sequence[float], gap: float) -> List[List[float]]:
    if not values:
        return []
    sorted_values = sorted(values)
    groups = [[sorted_values[0]]]
    for value in sorted_values[1:]:
        group = groups[-1]
        if value - group[-1] <= gap:
            group.append(value)
        else:
            groups.append([value])
    return groups


def _overlay_items_look_like_table(items: Sequence[Dict[str, Any]]) -> bool:
    if len(items) < 6:
        return False
    rows = _cluster_sorted_edges([item["bbox"]["y"] for item in items], 18)
    if len(rows) >= 2:
        centers = sorted(sum(group) / len(group) for group in rows)
        gaps = [value - centers[index] for index, value in enumerate(centers[1:])]
        if gaps and max(gaps) >= 150:
            return False
    columns = [group for group in _cluster_sorted_edges([item["bbox"]["x"] for item in items], 28) if len(group) >= 3]
    row_groups = _cluster_sorted_edges([item["bbox"]["y"] for item in items], 14)
    return len(columns) >= 2 and len(row_groups) >= 4


def _append_table_layout_neighbors(all_blocks: Sequence[Dict[str, Any]], draw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    probes = []
    for block in draw:
        if not str(block.get("text") or "").strip():
            continue
        box = block["bbox"]
        probes.append(
            {
                "bbox": {
                    "x": box[0],
                    "y": box[1],
                    "width": max(1, box[2] - box[0]),
                    "height": max(1, box[3] - box[1]),
                }
            }
        )
    if not _overlay_items_look_like_table(probes):
        return draw
    top = min(item["bbox"]["y"] for item in probes) - 8
    bottom = max(item["bbox"]["y"] + item["bbox"]["height"] for item in probes) + 36
    left = min(item["bbox"]["x"] for item in probes) - 8
    right = max(item["bbox"]["x"] + item["bbox"]["width"] for item in probes) + 560
    extra: List[Dict[str, Any]] = []
    draw_ids = {id(block) for block in draw}
    for block in all_blocks:
        if id(block) in draw_ids:
            continue
        text = str(block.get("text") or "").strip()
        if not text or has_chinese_text(text):
            continue
        box = block["bbox"]
        mid_x = (box[0] + box[2]) / 2
        mid_y = (box[1] + box[3]) / 2
        if mid_y < top or mid_y > bottom or mid_x < left or mid_x > right:
            continue
        copied = dict(block)
        copied["layoutOnly"] = True
        extra.append(copied)
    return draw + extra if extra else draw


def local_blocks_need_draw(blocks: Sequence[Any]) -> Dict[str, Any]:
    rows = _as_blocks(blocks)
    for block in rows:
        if _block_has_return_cluster(block.get("text") or ""):
            continue
        if _urgent_delete_hit(block.get("text") or ""):
            return {
                "action": "deleted",
                "blocks": [],
                "message": "Xóa theo keyword cấm trong local translator",
            }
    draw: List[Dict[str, Any]] = []
    for block in rows:
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        if _block_has_return_cluster(text):
            draw.append({"text": "", "bbox": block["bbox"]})
            continue
        factory = strip_factory_intro_text(text)
        if factory["matched"] and count_hanzi(factory["text"]) < 2:
            draw.append({"text": "", "bbox": block["bbox"]})
            continue
        if factory["matched"]:
            text = factory["text"]
        is_domain = bool(IMAGE_LOC_DOMAIN_REGEX.search(text) or re.search(r"www\.|\.com|\.cn|\.net|\.org|\.vn", text, re.I))
        is_old_year = bool(re.search(r"2019|2020|2021|2022|2023|2024", text))
        has_jin = "斤" in text
        if is_domain or is_old_year:
            draw.append({"text": "", "bbox": block["bbox"]})
            continue
        if not has_jin and count_hanzi(text) == 1:
            continue
        if has_jin or has_chinese_text(text) or re.fullmatch(r"\d+(?:[.,]\d+)?\s*cm", text, re.I):
            copied = dict(block)
            copied["text"] = text
            draw.append(copied)
    if not draw:
        return {"action": "empty", "blocks": [], "message": "Không có block local cần xử lý"}
    return {
        "action": "draw",
        "blocks": _append_table_layout_neighbors(rows, draw),
        "message": "OCR: DeepSeek dịch chữ + vẽ lại chữ lên ảnh (local)",
    }


def remaining_chinese_on_localized_image(texts: Sequence[str]) -> List[str]:
    left = []
    for raw in texts:
        text = str(raw or "").strip()
        if text and has_chinese_text(text):
            left.append(text)
    return left


def localized_image_fix(*, bleed: bool, chinese_count: int) -> str:
    if bleed:
        return "gpt"
    if chinese_count > 0:
        return "deepseek"
    return "ok"


def localized_image_problem(*, bleed: bool, where: str = "", chinese: Sequence[str]) -> str:
    parts = []
    if bleed:
        parts.append(f"mực loang: {where}" if where else "mực loang")
    if chinese:
        parts.append("còn chữ Trung: " + " | ".join(list(chinese)[:4])[:180])
    return " — ".join(parts)


def parse_ink_bleed_verdict(raw: str) -> Optional[Dict[str, Any]]:
    start = (raw or "").find("{")
    end = (raw or "").rfind("}")
    if start < 0 or end <= start:
        return None
    import json

    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("bleed"), bool):
        return None
    where = re.sub(r"\s+", " ", str(parsed.get("where") or "")).strip()[:120]
    return {"bleed": parsed["bleed"], "where": where}


def chinese_blocks_to_redraw(blocks: Sequence[Any]) -> List[Dict[str, Any]]:
    return [
        block
        for block in _as_blocks(blocks)
        if not block.get("layoutOnly") and has_chinese_text(block.get("text") or "")
    ]


def deepseek_image_prompt(text: str, language: str = "vi") -> str:
    target = LANGUAGE_LABELS.get((language or "vi").strip().lower(), language or "Vietnamese")
    return (
        f'Translate the following short text into {target} for an e-commerce product image:\n'
        f'"{text}"\n'
        "REQUIREMENTS:\n"
        f"1. Return ONLY the {target} result. Do not repeat the prompt.\n"
        "2. Preserve all measurements and numbers (45kg, 5cm, etc.).\n"
        "3. Translate both English and Chinese text when present.\n"
        "4. If Chinese is already paired with an English gloss of the same phrase "
        '(e.g. "结构图 /Structure"), return one '
        f"{target} phrase. Do not repeat the meaning.\n"
        "5. Keep standard abbreviations such as NC and NO.\n"
        "6. Keep the full meaning of a short label. Do not shorten it to one fragment. "
        "Do not add words that are not in the source.\n"
        "7. Do not add explanations, model codes, or SKUs that are not in the source.\n"
        "8. A short spec label must stay short enough for one line on the original row. "
        "Do not turn it into a sentence.\n"
        "9. A note or a full sentence must read as natural prose. "
        "Do not capitalize a word in the middle of the sentence.\n"
        "10. A poster slogan must stay one short line. Do not add adjectives that are not in the source."
    )
