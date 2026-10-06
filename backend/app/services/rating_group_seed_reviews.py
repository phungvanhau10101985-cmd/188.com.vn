"""
Tạo 100 đánh giá import cho nhóm đánh giá của danh mục cấp 3 mới.

Bám cách nhóm dựng sẵn trên server: tiêu đề ngắn, 4 hoặc 5 sao, shop 188.COM.VN trả lời,
không ảnh. Nội dung gọi món theo cách khách hay nói («dép», «giày», «vòng cổ»),
không dán nguyên tên danh mục, và không gắn chất liệu/kiểu của ngành khác.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy.orm import Session

from app.models.product_review import ProductReview
from app.services.rating_group_alloc import _table_names

SEED_REVIEW_COUNT = 100
_SHOP = "188.COM.VN"

_HO = (
    "Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng",
    "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý",
)
_TEN_NU = (
    "Lan", "Hương", "Trang", "Ngọc", "Linh", "Hà", "Vy", "Chi", "Nhung", "Thảo",
    "Huyền", "Trâm", "Yến", "Mai", "Hạnh", "Dung", "Phương", "Quỳnh", "Oanh", "My",
)
_TEN_NAM = (
    "Minh", "Hùng", "Dũng", "Tuấn", "Long", "Khoa", "Phong", "Đạt", "Kiên", "Tùng",
    "Huy", "Quân", "Bảo", "Thắng", "Cường", "Sơn", "Việt", "Đức", "Nam", "Quang",
)
_TEN_NU_SET = frozenset(t.casefold() for t in _TEN_NU)
_TEN_NAM_SET = frozenset(t.casefold() for t in _TEN_NAM)

_REPLY_5 = (
    "Cảm ơn {p} đã đánh giá ạ.",
    "Dạ {shop} cảm ơn {p} đã chia sẻ ạ.",
    "{shop} cảm ơn {p} đã ủng hộ.",
    "Cảm ơn {p} đã đặt hàng tại {shop} ạ.",
)
_REPLY_4 = (
    "Dạ {shop} cảm ơn {p} đã góp ý, shop ghi nhận ạ.",
    "Cảm ơn {p} đã phản hồi thật, {shop} sẽ xem lại ạ.",
    "{shop} cảm ơn {p}, góp ý này shop lưu lại.",
)


def _audience(cat1: str, cat2: str, cat3: str) -> str:
    blob = f" {cat1} {cat2} {cat3} ".casefold()
    has_nu = " nữ" in blob
    has_nam = " nam" in blob
    if has_nu and has_nam:
        return "unisex"
    if has_nu:
        return "female"
    if has_nam:
        return "male"
    return "unisex"


def _product_noun(cat3: str) -> str:
    name = re.sub(r"\s+", " ", (cat3 or "").strip())
    lowered = name.casefold()
    for suffix in (" nam nữ", " nữ", " nam"):
        if lowered.endswith(suffix):
            name = name[: -len(suffix)].strip()
            break
    return name or (cat3 or "").strip() or "sản phẩm"


# Cách khách hay gọi. Cụm dài đứng trước («vòng cổ» trước «vòng»).
_SPOKEN_HEADS = (
    ("vòng cổ", "vòng cổ"),
    ("dây chuyền", "dây chuyền"),
    ("bông tai", "bông tai"),
    ("đồng hồ", "đồng hồ"),
    ("chân váy", "chân váy"),
    ("dây dắt", "dây dắt"),
    ("đồ ngủ", "đồ ngủ"),
    ("đồ bộ", "bộ đồ"),
    ("dép", "dép"),
    ("sandal", "sandal"),
    ("sneaker", "giày"),
    ("giày", "giày"),
    ("boot", "boot"),
    ("túi", "túi"),
    ("balo", "balo"),
    ("vali", "vali"),
    ("áo", "áo"),
    ("quần", "quần"),
    ("váy", "váy"),
    ("đầm", "đầm"),
    ("vest", "vest"),
    ("nhẫn", "nhẫn"),
    ("lắc", "lắc"),
    ("vòng", "vòng"),
    ("ví", "ví"),
)


def _spoken_noun(cat3: str) -> str:
    name = _product_noun(cat3).casefold()
    for head, spoken in sorted(_SPOKEN_HEADS, key=lambda item: len(item[0]), reverse=True):
        if head in name:
            return spoken
    first = name.split()
    return first[0] if first else "món này"


def _with_noun(line: str, noun: str) -> str:
    text = line.replace("{n}", noun)
    if text.casefold().startswith(noun.casefold()):
        return noun[:1].upper() + noun[1:] + text[len(noun) :]
    return text


def _kind(path: str) -> str:
    t = path.casefold()
    if any(k in t for k in ("chó", "mèo", "thú cưng", "thú nuôi")):
        return "generic"
    if any(k in t for k in ("vali", "hành lý")):
        return "luggage"
    if any(k in t for k in ("giày", "dép", "sandal", "boot", "sneaker")):
        return "footwear"
    if any(k in t for k in ("túi", "balo", "ví ")):
        return "bag"
    if any(k in t for k in ("đồng hồ",)):
        return "watch"
    if any(k in t for k in ("nhẫn", "vòng", "lắc", "bông tai", "dây chuyền")):
        return "jewelry"
    if any(k in t for k in ("áo", "quần", "váy", "đầm", "đồ bộ", "đồ ngủ", "vest", "chân váy")):
        return "apparel"
    return "generic"


def _name_pool(tens: tuple, rng: random.Random) -> List[str]:
    pool = [f"{ho} {ten}" for ho in _HO for ten in tens]
    rng.shuffle(pool)
    return pool


def reviewer_name_gender(user_name: str) -> str:
    """'female' hoặc 'male' theo tên đệm/tên gọi cuối."""
    given = (user_name or "").strip().split()[-1].casefold() if (user_name or "").strip() else ""
    if given in _TEN_NU_SET:
        return "female"
    if given in _TEN_NAM_SET:
        return "male"
    return ""


def _reviewers(audience: str, rng: random.Random, count: int) -> List[tuple]:
    """(tên, xưng hô). Nữ → toàn tên nữ/chị; nam → toàn tên nam/anh; không giới → trộn đều."""
    if audience == "female":
        names = _name_pool(_TEN_NU, rng)[:count]
        return [(name, "chị") for name in names]
    if audience == "male":
        names = _name_pool(_TEN_NAM, rng)[:count]
        return [(name, "anh") for name in names]
    half = count // 2
    female = [(name, "chị") for name in _name_pool(_TEN_NU, rng)[: half + (count % 2)]]
    male = [(name, "anh") for name in _name_pool(_TEN_NAM, rng)[:half]]
    mixed = female + male
    rng.shuffle(mixed)
    return mixed[:count]


def _lines(kind: str, noun: str):
    common = [
        "Nhận {n} đúng như hình, gói cũng chắc.",
        "Giao {n} nhanh, về là dùng được luôn.",
        "{n} ổn so với giá, có khi mình mua lại.",
        "Đặt {n} lần đầu, về đúng như mô tả.",
        "Shop gói {n} cẩn thận, không móp.",
    ]
    if noun in ("dép", "sandal"):
        footwear = [
            "Đi {n} êm, không cấn ngón.",
            "Quai {n} chắc, mưa nhỏ không tuột.",
            "Mang {n} nửa ngày vẫn ổn.",
            "{n} nhẹ, đi trong nhà hay ra đường đều được.",
            "Đi {n} cả buổi không đau chân.",
        ]
    else:
        footwear = [
            "Đi {n} êm, size vừa chân.",
            "Đế {n} bám, mưa nhỏ không trơn.",
            "Mang {n} nửa ngày không đau mũi.",
            "{n} ôm chân, không rộng gót.",
            "Mang {n} đi làm cả ngày vẫn ổn.",
        ]
    specific = {
        "apparel": [
            "Mặc {n} lên form vừa, vải không xù.",
            "{n} mặc thoáng, đường may gọn.",
            "{n} đúng size mình chọn, mặc cả ngày vẫn ổn.",
            "Vải {n} mát, giặt xong không nhăn nhiều.",
            "{n} lên dáng tự nhiên, không bị bóng.",
        ],
        "footwear": footwear,
        "bag": [
            "{n} đựng vừa đồ hàng ngày, khóa kéo mượt.",
            "Quai {n} chắc, đeo vai không tuột.",
            "Ngăn {n} chia rõ, lấy đồ nhanh.",
            "{n} may đều, không chỉ thừa.",
            "{n} đứng form, để vài ngày không xẹp.",
        ],
        "luggage": [
            "Kéo {n} nhẹ tay, bánh xe chạy êm.",
            "Khóa {n} khớp, đựng đồ đi chơi cuối tuần vừa.",
            "{n} đứng vững, kéo không bị đổ.",
            "Tay cầm {n} chắc, kéo trên sàn không kêu to.",
            "{n} gọn hơn mình nghĩ, cho vào cốp xe vừa.",
        ],
        "watch": [
            "Đeo {n} vừa cổ tay, mặt nhìn rõ.",
            "Dây {n} không cấn, khóa giữ ổn.",
            "{n} nhẹ, đeo cả ngày không khó chịu.",
            "Kim {n} chạy đều, ngoài trời vẫn thấy giờ.",
            "{n} đúng mẫu mình chọn, hộp giao kèm đủ.",
        ],
        "jewelry": [
            "Đeo {n} vừa, không kẹt khóa.",
            "{n} sáng nhẹ, đeo đi làm không vướng.",
            "Khóa {n} đóng chắc, đeo cả buổi không tuột.",
            "{n} nhẹ, đeo không bị kích.",
            "Hộp {n} gói gọn, bên trong đúng mô tả.",
        ],
        "generic": [
            "{n} dùng ổn, đúng như mô tả.",
            "Mở {n} ra kiểm tra, không thiếu gì.",
            "{n} lắp dùng được ngay, không phải chỉnh nhiều.",
            "Dùng {n} vài ngày vẫn ổn, chưa thấy lỗi.",
            "{n} gọn, để dùng hàng ngày tiện.",
        ],
    }
    caveats = {
        "apparel": "size hơi rộng hơn số mình hay mặc.",
        "footwear": "đi mới hơi cứng, mang thêm vài bữa thì êm hơn.",
        "bag": "quai hơi cứng lúc mới đeo.",
        "luggage": "hơi nặng hơn mình tưởng một chút.",
        "watch": "dây hơi cứng những ngày đầu.",
        "jewelry": "khóa hơi nhỏ, đeo vẫn được.",
        "generic": "giao chậm hơn dự kiến khoảng một hôm.",
    }
    lines = [_with_noun(line, noun) for line in common + specific.get(kind, specific["generic"])]
    return lines, caveats.get(kind, caveats["generic"])


def _content(kind: str, noun: str, index: int, star: int) -> str:
    lines, caveat = _lines(kind, noun)
    closers = (
        "",
        " Mình nhận hàng rồi dùng luôn.",
        " Sẽ giới thiệu cho người nhà.",
        " Hộp không móp.",
        " Khớp phần mô tả trên web.",
        " Mình giữ lại dùng tiếp.",
        " Không phải đổi trả.",
        " Người nhà xem cũng ưng.",
        " Lần này đặt đúng món cần.",
        " Để dùng hàng ngày ổn.",
    )
    text = f"{lines[index % len(lines)]}{closers[index // len(lines)]}".strip()
    if star == 4:
        text = f"{text} Chỉ có điều {caveat}"
    if noun.casefold() not in text.casefold():
        text = f"Mình lấy {noun}. {text}"
    return text[:500]


def seed_reviews_for_new_group(
    db: Session,
    group_id: int,
    *,
    cat1: str,
    cat2: str,
    cat3: str,
) -> int:
    """
    Ghi 100 đánh giá import cho ``group_id`` nếu nhóm chưa có đánh giá nào.
    Trả số bản ghi vừa tạo (0 nếu bỏ qua).
    """
    gid = int(group_id or 0)
    if gid <= 0 or "product_reviews" not in _table_names(db):
        return 0
    existing = (
        db.query(ProductReview.id)
        .filter(ProductReview.group == gid)
        .limit(1)
        .first()
    )
    if existing:
        return 0

    audience = _audience(cat1, cat2, cat3)
    noun = _spoken_noun(cat3)
    kind = _kind(f"{cat1} {cat2} {cat3}")
    rng = random.Random(gid)
    reviewers = _reviewers(audience, rng, SEED_REVIEW_COUNT)
    now = datetime.now(timezone.utc)
    rows: List[ProductReview] = []
    for i in range(SEED_REVIEW_COUNT):
        star = 4 if i % 10 == 7 else 5
        user_name, pronoun = reviewers[i]
        reply_tpl = _REPLY_4[i % len(_REPLY_4)] if star == 4 else _REPLY_5[i % len(_REPLY_5)]
        created = now - timedelta(days=2 + (i % 17), hours=(i * 3) % 20, minutes=(i * 11) % 50)
        reply_at = created + timedelta(hours=2 + (i % 6))
        rows.append(
            ProductReview(
                user_name=user_name,
                star=star,
                title="Hài Lòng" if star == 4 else "Cực Hài Lòng",
                content=_content(kind, noun, i, star),
                group=gid,
                product_id=None,
                useful=0 if i % 5 == 0 else 1 + ((i * 3) % 18),
                reply_name=_SHOP,
                reply_content=reply_tpl.format(p=pronoun, shop=_SHOP),
                reply_at=reply_at,
                images=[],
                is_active=True,
                is_imported=True,
                created_at=created,
            )
        )
    db.add_all(rows)
    db.flush()
    return len(rows)
