"""
Loại tên thương hiệu / nhân vật có bản quyền khỏi tên và mô tả listing.

Mục đích: tên mặc định khi đăng (import, vision, DeepSeek) không mang nhãn hiệu
bên thứ ba — tránh chính sách hàng giả trên kênh bán và quảng cáo.
"""
from __future__ import annotations

import re

LISTING_NO_IP_PROMPT_VI = """
BẢN QUYỀN / HÀNG GIẢ (bắt buộc):
- KHÔNG ghi tên thương hiệu, nhà mốt, logo, nhân vật, phim, game, CLB/đội thể thao có bản quyền trong ten_tieng_viet, mo_ta_vi, khach_hang, phong_cach_vi, thuong_hieu_vi và mọi trường tiếng Việt hiển thị.
- Cấm kiểu: Nike, Adidas, Jordan, Gucci, Louis Vuitton, Chanel, Dior, Hermès, Prada, Balenciaga, Disney, Hello Kitty, Labubu, Pokemon, MLB, Yankees…
- Nguồn hoặc ảnh có logo/nhân vật đó: BỎ HẲN tên, mô tả trung tính theo loại hàng + form + chất liệu + họa tiết (vd. «giày thể thao đế dày», «áo thun in họa tiết», «túi đeo chéo da»).
- Không viết «phong cách + tên hãng», «replica», «like auth», «super fake», «1:1», «high copy», «hàng rep».
- thuong_hieu_vi để "" khi chỉ nhận ra thương hiệu/nhân vật bên thứ ba. Không điền hãng nổi tiếng.
"""

# Cụm Latin / tiếng Việt. Khớp cả dấu cách và gạch nối (Air Jordan, air-jordan).
_FLEX_TERMS: tuple[str, ...] = (
    "louis vuitton",
    "louisvuitton",
    "christian dior",
    "air jordan",
    "air force 1",
    "air force",
    "air max",
    "airforce",
    "new balance",
    "newbalance",
    "the north face",
    "north face",
    "northface",
    "canada goose",
    "under armour",
    "lululemon",
    "michael kors",
    "bottega veneta",
    "alexander mcqueen",
    "chrome hearts",
    "chromehearts",
    "golden goose",
    "dr. martens",
    "dr martens",
    "doc martens",
    "calvin klein",
    "tommy hilfiger",
    "ralph lauren",
    "stone island",
    "palm angels",
    "hugo boss",
    "onitsuka tiger",
    "off white",
    "off-white",
    "offwhite",
    "hello kitty",
    "hellokitty",
    "my melody",
    "mickey mouse",
    "minnie mouse",
    "donald duck",
    "winnie the pooh",
    "winnie pooh",
    "harry potter",
    "star wars",
    "dragon ball",
    "one piece",
    "crayon shin-chan",
    "shin-chan",
    "spider-man",
    "spider man",
    "spiderman",
    "iron man",
    "captain america",
    "black panther",
    "super mario",
    "baby yoda",
    "darth vader",
    "toy story",
    "buzz lightyear",
    "peppa pig",
    "paw patrol",
    "baby shark",
    "pop mart",
    "popmart",
    "sonny angel",
    "gallery dept",
    "denim tears",
    "broken planet",
    "fear of god",
    "a bathing ape",
    "manchester united",
    "real madrid",
    "chicago bulls",
    "like authentic",
    "like auth",
    "super fake",
    "high copy",
    "mirror quality",
    "hàng replica",
    "hàng rep",
    "chuck taylor",
    "stan smith",
    "hermès",
    "hermes",
    "céline",
    "celine",
    "stüssy",
    "stussy",
    "pokémon",
    "pokemon",
    "balenciaga",
    "burberry",
    "givenchy",
    "versace",
    "valentino",
    "moncler",
    "birkenstock",
    "lululemon",
    "converse",
    "newbalance",
    "yeezy",
    "supreme",
    "balenciaga",
    "chanel",
    "gucci",
    "prada",
    "fendi",
    "loewe",
    "miu miu",
    "miumiu",
    "dior",
    "nike",
    "adidas",
    "jordan",
    "puma",
    "reebok",
    "asics",
    "onitsuka",
    "skechers",
    "fila",
    "kappa",
    "umbro",
    "crocs",
    "ugg",
    "vans",
    "bape",
    "kaws",
    "amiri",
    "rhude",
    "corteiz",
    "trapstar",
    "hellstar",
    "sp5der",
    "stussy",
    "rolex",
    "cartier",
    "tiffany",
    "coach",
    "disney",
    "mickey",
    "minnie",
    "marvel",
    "batman",
    "superman",
    "avengers",
    "deadpool",
    "venom",
    "pikachu",
    "doraemon",
    "naruto",
    "ghibli",
    "totoro",
    "barbie",
    "lego",
    "hogwarts",
    "minions",
    "snoopy",
    "shinchan",
    "ultraman",
    "gundam",
    "transformers",
    "nintendo",
    "mario",
    "luigi",
    "zelda",
    "stitch",
    "frozen",
    "elsa",
    "goku",
    "luffy",
    "grogu",
    "mandalorian",
    "cocomelon",
    "bluey",
    "labubu",
    "dimoo",
    "skullpanda",
    "smiski",
    "chiikawa",
    "hachiware",
    "rilakkuma",
    "mofusand",
    "sumikko",
    "sanrio",
    "kuromi",
    "cinnamoroll",
    "pompompurin",
    "pochacco",
    "gudetama",
    "bearbrick",
    "jellycat",
    "anpanman",
    "yankees",
    "dodgers",
    "lakers",
    "juventus",
    "yeezy",
    "samba",
    "gazelle",
    "superstar",
    "dunk",
    "ysl",
    "lv",
    "mcm",
    "mlb",
    "nba",
    "nfl",
    "tnf",
    "ugg",
    "d&g",
    "h&m",
    "psg",
    "bt21",
    "bts",
    "replica",
)

_CJK_TERMS: tuple[str, ...] = (
    "路易威登",
    "加拿大鹅",
    "泡泡玛特",
    "哆啦A梦",
    "哆啦A夢",
    "亚历山大麦昆",
    "克罗心",
    "金鹅",
    "圣罗兰",
    "巴黎世家",
    "香奈儿",
    "香奈爾",
    "爱马仕",
    "愛馬仕",
    "普拉达",
    "普拉達",
    "巴宝莉",
    "纪梵希",
    "范思哲",
    "华伦天奴",
    "罗意威",
    "新百伦",
    "阿迪达斯",
    "卡地亚",
    "劳力士",
    "蔻驰",
    "古驰",
    "古奇",
    "迪奥",
    "迪奧",
    "芬迪",
    "缪缪",
    "赛琳",
    "麦昆",
    "耐克",
    "阿迪",
    "乔丹",
    "匡威",
    "彪马",
    "万斯",
    "斐乐",
    "北面",
    "蒙口",
    "迪士尼",
    "三丽鸥",
    "凯蒂猫",
    "库洛米",
    "拉布布",
    "宝可梦",
    "皮卡丘",
    "奥特曼",
    "高达",
    "米奇",
    "米妮",
    "高仿",
    "精仿",
    "原单",
    "复刻",
    "莆田",
    "A货",
)

_CUSTOM_PATTERNS: tuple[str, ...] = (
    r"(?<![A-Za-z0-9])1\s*[:：]\s*1(?![A-Za-z0-9])",
)


def _flex_pattern(term: str) -> str:
    parts = [p for p in re.split(r"[\s\-]+", term.strip()) if p]
    body = r"[\s\-]*".join(re.escape(p) for p in parts)
    return rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])"


def _compile_ip_regex() -> re.Pattern[str]:
    flex = sorted({t.strip() for t in _FLEX_TERMS if t.strip()}, key=len, reverse=True)
    cjk = sorted({t.strip() for t in _CJK_TERMS if t.strip()}, key=len, reverse=True)
    parts = [_flex_pattern(t) for t in flex]
    parts.extend(re.escape(t) for t in cjk)
    parts.extend(_CUSTOM_PATTERNS)
    return re.compile("|".join(parts), re.IGNORECASE | re.UNICODE)


_IP_RE = _compile_ip_regex()


def listing_text_has_ip(text: str) -> bool:
    if not text or not str(text).strip():
        return False
    return _IP_RE.search(str(text)) is not None


def _tidy_after_ip_strip(text: str) -> str:
    t = _IP_RE.sub(" ", text)
    t = re.sub(r"(?:\s*[,;/|·•]+\s*){2,}", ", ", t)
    t = re.sub(r"\s+([,;])", r"\1", t)
    t = re.sub(r"(?:^|\s)[,;/|·•]+(?=\s|$)", " ", t)
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"\[\s*\]", "", t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\s*\n\s*", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip(" ,.;·|—-")


def strip_listing_ip_terms(text: str) -> str:
    """Bỏ tên thương hiệu, nhân vật bản quyền và từ ngữ hàng nhái."""
    if not text or not str(text).strip():
        return ""
    if not listing_text_has_ip(text):
        return str(text).strip()
    return _tidy_after_ip_strip(str(text))
