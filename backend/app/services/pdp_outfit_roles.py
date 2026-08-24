"""Phân vai trò phối đồ từ danh mục 3 cấp — thuần, không I/O."""
from __future__ import annotations

from typing import List, Literal, Optional, Sequence, Tuple

OutfitRole = Literal["top", "bottom", "dress", "shoes", "bag", "accessory"]
OutfitGender = Literal["Nam", "Nữ", "unisex"]
NotFashionReason = Literal["not_fashion", "no_slots"]

FASHION_CAT1_PREFIXES: Tuple[str, ...] = (
    "thời trang nam",
    "thời trang nữ",
    "giày dép nam",
    "giày dép nữ",
    "túi xách nam",
    "túi xách nữ",
    "phụ kiện nam",
    "phụ kiện nữ",
    "trang sức thời trang",
    "đồng hồ",
)

SLOT_LABELS: dict[str, str] = {
    "top": "Áo",
    "bottom": "Quần",
    "dress": "Váy",
    "shoes": "Giày",
    "bag": "Túi",
    "accessory": "Phụ kiện",
}

ROLE_LABELS: dict[str, str] = {
    "top": "áo",
    "bottom": "quần",
    "dress": "váy",
    "shoes": "giày",
    "bag": "túi",
    "accessory": "phụ kiện",
}

_DRESS_KEYS = (
    "váy liền",
    "đầm",
    "jumpsuit",
    "jump suit",
    "váy maxi",
    "váy midi",
    "váy ngắn",
    "váy dài",
)
_BOTTOM_KEYS = (
    "quần",
    "jean",
    "jeans",
    "short",
    "shorts",
    "chân váy",
    "váy chữ a",
)
_TOP_KEYS = (
    "áo",
    "sơ mi",
    "thun",
    "khoác",
    "vest",
    "hoodie",
    "blazer",
    "cardigan",
    "len",
    "croptop",
    "crop top",
    "tank",
    "polo",
)


def _cell(value: object) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    return s


def _norm(value: object) -> str:
    text = _cell(value)
    if not text:
        return ""
    return " ".join(text.lower().split())


def _join_parts(*parts: object) -> str:
    return " | ".join(_norm(p) for p in parts if _norm(p))


def infer_gender(*labels: object) -> OutfitGender:
    blob = _join_parts(*labels)
    has_nam = " nam" in f" {blob} " or blob.endswith(" nam") or " nam/" in blob
    has_nu = " nữ" in f" {blob} " or blob.endswith(" nữ") or " nữ/" in blob
    if has_nam and not has_nu:
        return "Nam"
    if has_nu and not has_nam:
        return "Nữ"
    return "unisex"


def is_fashion_category(cat1: object) -> bool:
    n = _norm(cat1)
    if not n:
        return False
    return any(n == p or n.startswith(p + " ") or n.startswith(p) for p in FASHION_CAT1_PREFIXES)


def _contains_any(blob: str, keys: Sequence[str]) -> bool:
    return any(k in blob for k in keys)


def is_mixed_apparel_set(
    category: object = None,
    subcategory: object = None,
    sub_subcategory: object = None,
    name: object = None,
) -> bool:
    """Bộ áo+váy / set golf — không phải một váy để phối."""
    blob = _join_parts(category, subcategory, sub_subcategory, name)
    if not blob:
        return False
    if any(k in blob for k in ("bộ trang phục", "bo trang phuc", "set đồ", "set do", "bộ đồ", "bo do")):
        return True
    has_top = _contains_any(blob, ("áo ", "ao ", "áo dài", "áo croptop", "crop"))
    has_dress = _contains_any(blob, ("váy", "đầm", "dam "))
    if has_top and has_dress and any(k in blob for k in ("phối váy", "phoi vay", "phối đầm", " kèm ", "kèm váy")):
        return True
    return False


def infer_outfit_role(
    category: object,
    subcategory: object = None,
    sub_subcategory: object = None,
    name: object = None,
) -> Optional[OutfitRole]:
    cat1 = _norm(category)
    rest = _join_parts(subcategory, sub_subcategory, name)
    blob = _join_parts(category, subcategory, sub_subcategory, name)
    if not cat1 and not rest:
        return None
    if not is_fashion_category(category) and cat1:
        return None

    if cat1.startswith("giày dép"):
        return "shoes"
    if cat1.startswith("túi xách"):
        return "bag"
    if (
        cat1.startswith("phụ kiện nam")
        or cat1.startswith("phụ kiện nữ")
        or cat1.startswith("trang sức")
        or cat1 == "đồng hồ"
        or cat1.startswith("đồng hồ ")
    ):
        return "accessory"

    if cat1.startswith("thời trang") or not cat1:
        if _contains_any(rest, _DRESS_KEYS) or _contains_any(blob, ("đầm", "jumpsuit")):
            if "chân váy" in rest and "váy liền" not in rest and "đầm" not in rest:
                return "bottom"
            return "dress"
        if _contains_any(rest, _BOTTOM_KEYS) or _contains_any(blob, ("quần ", " jean", "short")):
            return "bottom"
        if _contains_any(rest, _TOP_KEYS) or _contains_any(blob, _TOP_KEYS):
            return "top"
    return None


def target_cat1_names(slot: OutfitRole, gender: OutfitGender) -> List[str]:
    if slot == "shoes":
        base = "Giày dép"
    elif slot == "bag":
        base = "Túi xách"
    elif slot == "accessory":
        if gender == "Nam":
            return ["Phụ kiện Nam"]
        if gender == "Nữ":
            return ["Phụ kiện Nữ"]
        return ["Phụ kiện Nam", "Phụ kiện Nữ"]
    else:
        base = "Thời trang"

    if gender == "Nam":
        return [f"{base} Nam"]
    if gender == "Nữ":
        return [f"{base} Nữ"]
    return [f"{base} Nam", f"{base} Nữ"]


def slots_for_anchor(role: OutfitRole, gender: OutfitGender) -> List[OutfitRole]:
    female = gender in ("Nữ", "unisex")
    male = gender in ("Nam", "unisex")
    ordered: List[OutfitRole] = []

    def add(slot: OutfitRole) -> None:
        if slot != role and slot not in ordered:
            ordered.append(slot)

    if role == "top":
        if male:
            add("bottom")
        if female:
            add("dress")
            add("bottom")
        add("shoes")
        add("bag")
        add("accessory")
    elif role == "bottom":
        add("top")
        add("shoes")
        add("bag")
        add("accessory")
    elif role == "dress":
        add("shoes")
        add("bag")
        add("accessory")
    elif role == "shoes":
        add("top")
        if male:
            add("bottom")
        if female:
            add("dress")
            add("bottom")
        add("bag")
        add("accessory")
    elif role == "bag":
        add("top")
        if female:
            add("dress")
            add("bottom")
        add("shoes")
        add("accessory")
    elif role == "accessory":
        add("top")
        if female:
            add("dress")
            add("bottom")
        add("shoes")
        add("bag")
    return ordered


def _is_skirt_bottom(category: object, subcategory: object, sub_subcategory: object, name: object) -> bool:
    """Chân váy đang là bottom — tab Váy vẫn nhận."""
    if infer_outfit_role(category, subcategory, sub_subcategory, name) != "bottom":
        return False
    blob = _join_parts(subcategory, sub_subcategory, name)
    return "chân váy" in blob or "váy chữ a" in blob or "chan vay" in blob


def row_matches_slot_keywords(slot: OutfitRole, category: object, subcategory: object, sub_subcategory: object, name: object) -> bool:
    """Sau khi đã lọc cat1: top/bottom/dress bắt buộc đúng từ khóa; shoes/bag/accessory tin cat1."""
    if slot in ("shoes", "bag", "accessory"):
        return True
    role = infer_outfit_role(category, subcategory, sub_subcategory, name)
    if slot == "dress":
        if is_mixed_apparel_set(category, subcategory, sub_subcategory, name):
            return False
        return role == "dress" or _is_skirt_bottom(category, subcategory, sub_subcategory, name)
    return role == slot


def classify_anchor(
    category: object,
    subcategory: object = None,
    sub_subcategory: object = None,
    name: object = None,
) -> Tuple[Optional[OutfitRole], OutfitGender, Optional[NotFashionReason]]:
    gender = infer_gender(category, subcategory)
    if not is_fashion_category(category):
        return None, gender, "not_fashion"
    role = infer_outfit_role(category, subcategory, sub_subcategory, name)
    if role is None:
        return None, gender, "no_slots"
    return role, gender, None

