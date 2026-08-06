# backend/tests/test_ladipage_material_image_urls.py
from unittest.mock import MagicMock, patch

from app.services import ladipage_ai_service as svc


def test_collect_product_image_urls_dedupes_and_orders():
    product = MagicMock()
    product.main_image = "https://cdn.example/a.jpg"
    product.images = ["https://cdn.example/a.jpg", "https://cdn.example/b.jpg"]
    assert svc._collect_product_image_urls(product) == [
        "https://cdn.example/a.jpg",
        "https://cdn.example/b.jpg",
    ]


def test_pick_usable_product_image_urls_skips_broken():
    product = {
        "main_image": "https://cdn.example/broken.jpg",
        "gallery_urls": [
            "https://cdn.example/broken.jpg",
            "https://cdn.example/good.jpg",
        ],
    }

    def fake_usable(url: str, *, timeout: int = 15) -> bool:
        return url.endswith("good.jpg")

    with patch.object(svc, "_is_usable_reference_image_url", side_effect=fake_usable):
        assert svc.pick_usable_product_image_urls(product) == ["https://cdn.example/good.jpg"]


def test_generate_material_image_tries_next_gallery_on_failure():
    product = {
        "main_image": "https://cdn.example/bad.jpg",
        "gallery_urls": [
            "https://cdn.example/bad.jpg",
            "https://cdn.example/good.jpg",
        ],
    }

    with patch.object(svc, "pick_usable_product_image_urls", return_value=["https://cdn.example/bad.jpg", "https://cdn.example/good.jpg"]):
        with patch.object(svc, "_gemini_edit_image_from_url", side_effect=[RuntimeError("bad"), b"png-bytes"]):
            with patch.object(svc, "_upload_ladipage_image", return_value="https://cdn.188.com.vn/site/ladipage/1/x.png"):
                out = svc.generate_material_image(1, "Da PU", ["A", "B"], single_product=product)
    assert out["image_url"] == "https://cdn.188.com.vn/site/ladipage/1/x.png"


def test_resolve_material_product_image_keeps_existing():
    product = {"main_image": "https://cdn.example/a.jpg", "gallery_urls": ["https://cdn.example/a.jpg"]}
    current = {
        "image_url": "https://cdn.example/picked.jpg",
        "image_object_position": "30% 70%",
    }
    out = svc.resolve_material_product_image(product, current)
    assert out == {
        "image_url": "https://cdn.example/picked.jpg",
        "image_object_position": "30% 70%",
    }


def test_resolve_material_product_image_picks_first_usable():
    product = {
        "main_image": "https://cdn.example/broken.jpg",
        "gallery_urls": ["https://cdn.example/broken.jpg", "https://cdn.example/good.jpg"],
    }

    with patch.object(svc, "pick_usable_product_image_urls", return_value=["https://cdn.example/good.jpg"]):
        out = svc.resolve_material_product_image(product, {})
    assert out == {"image_url": "https://cdn.example/good.jpg", "image_object_position": "50% 50%"}


def test_collect_product_image_urls_from_dict_includes_colors():
    product = {
        "main_image": "https://cdn.example/main.jpg",
        "colors": [{"name": "Đen", "img": "https://cdn.example/black.jpg"}],
        "color_image_urls": ["https://cdn.example/red.jpg"],
    }
    assert svc._collect_product_image_urls_from_dict(product) == [
        "https://cdn.example/main.jpg",
        "https://cdn.example/black.jpg",
        "https://cdn.example/red.jpg",
    ]
