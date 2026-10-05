"""Ảnh biến thể bị pipeline đánh dấu xóa vẫn giữ URL gốc — không để storefront lấy gallery[index]."""
from app.services.image_localization_service import (
    ImageProcessResult,
    ProductImageLocalizationService,
)


def test_deleted_localization_keeps_color_img_and_drops_gallery_copy():
    svc = ProductImageLocalizationService.__new__(ProductImageLocalizationService)
    product = type("P", (), {})()
    url = "https://cdn.example/sku.jpg"
    product.colors = [{"img": url, "sku": "2W31-15GBN-DC24V", "name": "2W31-15GBN-DC24V"}]
    product.images = [url]
    product.gallery = [url]
    product.main_image = url
    results = {
        url: ImageProcessResult(url, None, "deleted", "Ảnh chứa domain"),
    }

    svc._apply_results(product, results)

    assert product.colors[0]["img"] == url
    assert product.colors[0]["sku"] == "2W31-15GBN-DC24V"
    assert product.images == []
    assert product.gallery == []
    assert product.main_image is None
