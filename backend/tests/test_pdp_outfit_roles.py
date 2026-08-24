from app.services.pdp_outfit_roles import (
    classify_anchor,
    infer_gender,
    infer_outfit_role,
    is_fashion_category,
    is_mixed_apparel_set,
    row_matches_slot_keywords,
    slots_for_anchor,
    target_cat1_names,
)
from app.services.pdp_outfit_suggestions import color_families_from_product, score_outfit_candidate


def test_fashion_and_non_fashion():
    assert is_fashion_category("Giày dép Nam")
    assert is_fashion_category("Thời trang Nữ")
    assert is_fashion_category("Đồng hồ")
    assert not is_fashion_category("Đồ gia dụng")
    assert not is_fashion_category("Mỹ phẩm & làm đẹp")


def test_infer_roles():
    assert infer_outfit_role("Giày dép Nam", "Giày tây nam", "Giày tây da") == "shoes"
    assert infer_outfit_role("Túi xách Nữ", "Túi tote") == "bag"
    assert infer_outfit_role("Phụ kiện Nam", "Thắt lưng") == "accessory"
    assert infer_outfit_role("Thời trang Nam", "Áo sơ mi nam", "Áo sơ mi dài tay") == "top"
    assert infer_outfit_role("Thời trang Nam", "Quần âu nam") == "bottom"
    assert infer_outfit_role("Thời trang Nữ", "Váy liền", "Đầm dự tiệc") == "dress"
    assert infer_outfit_role("Thời trang Nữ", "Chân váy", "Chân váy chữ A") == "bottom"


def test_gender():
    assert infer_gender("Giày dép Nam") == "Nam"
    assert infer_gender("Túi xách Nữ") == "Nữ"
    assert infer_gender("Đồng hồ") == "unisex"


def test_classify_anchor_hides_non_fashion():
    role, gender, reason = classify_anchor("Đồ gia dụng", "Nồi")
    assert role is None
    assert reason == "not_fashion"


def test_slots_shoes_nam():
    assert slots_for_anchor("shoes", "Nam") == ["top", "bottom", "bag", "accessory"]


def test_slots_shoes_nu_includes_dress_and_bottom():
    assert slots_for_anchor("shoes", "Nữ") == ["top", "dress", "bottom", "bag", "accessory"]


def test_vay_tab_accepts_chan_vay():
    assert row_matches_slot_keywords(
        "dress", "Thời trang Nữ", "Chân váy", "Chân váy chữ A", "Chân váy nữ"
    )
    assert infer_outfit_role("Thời trang Nữ", "Chân váy", "Chân váy chữ A") == "bottom"


def test_golf_set_is_not_a_dress_slot_item():
    name = "Bộ trang phục golf nữ PGM áo dài tay phối váy ngắn ôm eo — YF697"
    assert is_mixed_apparel_set("Thời trang Nữ", "Đồ yoga fitness & tập Nữ", None, name)
    assert not row_matches_slot_keywords(
        "dress",
        "Thời trang Nữ",
        "Đồ yoga fitness & tập Nữ",
        "áo crop tập yoga nữ lưng hở",
        name,
    )


def test_slots_dress():
    assert slots_for_anchor("dress", "Nữ") == ["shoes", "bag", "accessory"]


def test_target_cat1():
    assert target_cat1_names("bag", "Nam") == ["Túi xách Nam"]
    assert target_cat1_names("top", "Nữ") == ["Thời trang Nữ"]


class _P:
    def __init__(self, **kw):
        self.style = kw.get("style")
        self.occasion = kw.get("occasion")
        self.name = kw.get("name", "")
        self.color = kw.get("color")
        self.colors = kw.get("colors")
        self.price = kw.get("price", 0)
        self.purchases = kw.get("purchases", 0)
        self.material = kw.get("material")
        self.category = kw.get("category")
        self.subcategory = kw.get("subcategory")
        self.sub_subcategory = kw.get("sub_subcategory")


def test_score_style_occasion_color_price():
    anchor = _P(style="công sở", occasion="đi làm", name="Giày tây nam da đen", price=800000, purchases=10)
    good = _P(style="công sở", occasion="đi làm", name="Túi xách nam da đen", price=750000, purchases=3)
    other = _P(style="casual", occasion="dạo phố", name="Túi canvas trắng", price=200000, purchases=99)
    sg, pg, rg = score_outfit_candidate(anchor, good)
    so, po, _ro = score_outfit_candidate(anchor, other)
    assert sg >= 5
    assert so == 0
    assert any("phong cách" in x.lower() for x in rg)
    assert pg == 3
    assert po == 0


def test_formal_shoe_rejects_sport_hoodie():
    anchor = _P(name="Giày tây nam da đen công sở", style="công sở", price=800000)
    hoodie = _P(name="Áo hoodie nam thể thao", style="casual", price=350000, purchases=500)
    shirt = _P(name="Áo sơ mi nam công sở trắng", style="công sở", price=420000, purchases=20)
    sh, _ph, rh = score_outfit_candidate(anchor, hoodie, slot="top")
    ss, _ps, rs = score_outfit_candidate(anchor, shirt, slot="top")
    assert sh == 0
    assert ss >= 2
    assert rs


def test_thoi_trang_without_keywords_is_not_guessed_as_top():
    assert infer_outfit_role("Thời trang Nam", "Khác", "Hàng tổng") is None


def test_assemble_not_fashion_hides_block():
    from app.services.pdp_outfit_suggestions import assemble_outfit_response

    out = assemble_outfit_response(
        None,  # type: ignore[arg-type]
        {"applicable": False, "reason": "not_fashion", "anchor": None, "slots": []},
        serialize_rows=lambda _rows: [],
    )
    assert out["applicable"] is False
    assert out["slots"] == []
    assert out["reason"] == "not_fashion"


def test_color_families_skip_nan():
    p = _P(name="Giày sneaker", color="nan", colors=[{"name": "nan"}])
    assert color_families_from_product(p) == set()
    p2 = _P(name="Giày tây đen", color="nan")
    assert "black" in color_families_from_product(p2)
