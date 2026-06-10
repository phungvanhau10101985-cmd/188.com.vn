from types import SimpleNamespace

from app.services.product_image_visibility import (
    colors_valid_for_import,
    delete_product_if_no_variant_or_images,
    product_should_remove_after_localization,
)


def test_colors_valid_for_import_requires_name_and_http_image():
    assert colors_valid_for_import([]) is False
    assert colors_valid_for_import([{"name": "Đỏ"}]) is False
    assert colors_valid_for_import([{"name": "Đỏ", "img": "ftp://x/y.jpg"}]) is False
    assert colors_valid_for_import([{"name": "Đỏ", "img": "https://cdn.example/a.jpg"}]) is True
    assert colors_valid_for_import(
        [
            {"name": "Trắng", "img": "https://cdn.example/a.jpg"},
            {"name": "Đen"},
            {"name": "Xám", "img": "https://cdn.example/b.jpg"},
        ]
    ) is True
    assert colors_valid_for_import(
        [
            {"name": "Trắng"},
            {"name": "Đen"},
        ]
    ) is False


def test_product_should_remove_after_localization():
    empty_variant = SimpleNamespace(colors=[], main_image="", images=[], gallery=[])
    assert product_should_remove_after_localization(empty_variant) is True

    no_images = SimpleNamespace(
        colors=[{"name": "Đỏ", "img": ""}],
        main_image="",
        images=[],
        gallery=[],
    )
    assert product_should_remove_after_localization(no_images) is True

    ok = SimpleNamespace(
        colors=[{"name": "Đỏ", "img": "https://cdn.example/a.jpg"}],
        main_image="",
        images=[],
        gallery=[],
    )
    assert product_should_remove_after_localization(ok) is False


def test_delete_product_if_no_variant_or_images_keeps_valid_product():
    product = SimpleNamespace(
        id=1,
        product_id="A123",
        is_active=True,
        colors=[{"name": "Đỏ", "img": "https://cdn.example/a.jpg"}],
        main_image="",
        images=[],
        gallery=[],
    )
    assert delete_product_if_no_variant_or_images(None, product) == "kept"
