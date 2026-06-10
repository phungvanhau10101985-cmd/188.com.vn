from app.services.product_rating_question_groups import (
    RATING_GROUP_ID_UNASSIGNED,
    apply_import_rating_question_groups_to_product_data,
    coalesce_group_rating,
    infer_rating_group_id_from_text,
)


def test_coalesce_group_rating_defaults_to_888():
    assert RATING_GROUP_ID_UNASSIGNED == 888
    assert coalesce_group_rating(None) == 888
    assert coalesce_group_rating(0) == 888
    assert coalesce_group_rating(1000) == 888
    assert coalesce_group_rating("") == 888
    assert coalesce_group_rating(27) == 27
    assert coalesce_group_rating(0, inferred=18) == 18


def test_apply_import_sets_888_for_unknown_product_type():
    pd = {
        "name": "Máy lọc không khí mini không thuộc catalog",
        "category": "Điện tử",
        "subcategory": "Phụ kiện",
        "sub_subcategory": "Lọc không khí",
        "group_rating": 0,
    }
    apply_import_rating_question_groups_to_product_data(pd)
    assert pd["group_rating"] == 888


def test_apply_import_matches_vali_tui_du_lich():
    pd = {
        "name": "定制3C认证2025新款电动行李箱轻盈大容量旅行箱20寸登机箱加logo",
        "category": "Phụ kiện",
        "subcategory": "Vali túi du lịch",
        "sub_subcategory": "Vali điện",
        "group_rating": 0,
    }
    apply_import_rating_question_groups_to_product_data(pd)
    assert pd["group_rating"] == 94


def test_apply_import_matches_golf_groups():
    assert infer_rating_group_id_from_text("Bóng golf Titleist Pro V1") == 88
    assert infer_rating_group_id_from_text("Thảm cỏ nhân tạo sân golf") == 89
    assert infer_rating_group_id_from_text("Găng tay chơi golf nam") == 91
    assert infer_rating_group_id_from_text("Gậy đánh golf driver TaylorMade") == 92
    assert infer_rating_group_id_from_text("Túi gậy golf stand bag") == 93


def test_apply_import_keeps_rule_match():
    pd = {
        "name": "Giày sneaker nữ cao cấp",
        "category": "Giày dép Nữ",
        "subcategory": "Sneaker nữ",
        "sub_subcategory": "Sneaker nữ",
        "group_rating": 0,
    }
    apply_import_rating_question_groups_to_product_data(pd)
    assert pd["group_rating"] == 27
