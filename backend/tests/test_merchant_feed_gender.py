from app.models.product import Product
from app.services.merchant_feed_tsv import (
    _normalized_gender,
    infer_gender_from_name_and_categories,
)


def _product(**kwargs) -> Product:
    p = Product()
    for k, v in kwargs.items():
        setattr(p, k, v)
    return p


def test_infer_male_from_name():
    p = _product(name="Giày oxford da nam cao cấp")
    assert infer_gender_from_name_and_categories(p) == "male"


def test_infer_female_from_category():
    p = _product(
        name="Váy midi hoa nhí",
        category="Thời trang Nữ",
        subcategory="Váy Nữ",
    )
    assert infer_gender_from_name_and_categories(p) == "female"


def test_infer_unisex_when_both_present():
    p = _product(name="Áo thun basic unisex nam nữ")
    assert infer_gender_from_name_and_categories(p) == "unisex"


def test_infer_empty_when_no_gender_signal():
    p = _product(name="Túi đeo chéo mini", category="Phụ kiện")
    assert infer_gender_from_name_and_categories(p) == ""


def test_vietnam_place_name_not_treated_as_male():
    p = _product(name="Quà lưu niệm Việt Nam")
    assert infer_gender_from_name_and_categories(p) == ""


def test_product_info_gender_overrides_inference():
    p = _product(
        name="Váy dạ hội",
        category="Thời trang Nữ",
        product_info={"gender": "male"},
    )
    assert _normalized_gender(p) == "male"


def test_inference_used_when_product_info_gender_missing():
    p = _product(
        name="Giày sneaker",
        category="Giày dép Nam",
        subcategory="Sneaker Nam",
    )
    assert _normalized_gender(p) == "male"


def test_warehouse_clearance_custom_label_and_internal_label():
    from app.services.catalog_internal_labels import meta_internal_labels_for_product
    from app.services.merchant_feed_tsv import _custom_labels_1_to_4

    p_wh = _product(
        name="Áo Sơ Mi Nam Thanh Lý",
        is_warehouse_clearance=True,
    )
    c1, c2, c3, c4 = _custom_labels_1_to_4(p_wh)
    assert c1 == "thanh_ly_kho"
    assert "thanh_ly_kho" in meta_internal_labels_for_product(p_wh)

    p_normal = _product(
        name="Áo Sơ Mi Nam Mới",
        is_warehouse_clearance=False,
    )
    c1_norm, _, _, _ = _custom_labels_1_to_4(p_normal)
    assert c1_norm == ""
    assert "thanh_ly_kho" not in meta_internal_labels_for_product(p_normal)

