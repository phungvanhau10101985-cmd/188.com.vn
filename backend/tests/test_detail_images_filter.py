"""Cột detail_images (Nội dung): bỏ thumb NxN và ảnh PNG khi cào."""

from app.services.alicdn_urls import is_excluded_detail_content_image
from app.services.import_1688_scraper import normalize_1688_payload

_PNG = "https://gview.alicdn.com/16300288547781/1.0.0/img/17254220304978.png"
_THUMB = "https://cbu01.alicdn.com/img/ibank/O1CN01Rqp59N2Mb4OnBq2gM_!!2251189845-0-cib.310x310.jpg"
_THUMB_300 = "https://cbu01.alicdn.com/img/ibank/O1CN01abc_!!1-0-cib.jpg_300x300.jpg"
_THUMB_110 = "https://cbu01.alicdn.com/img/ibank/O1CN01abc_!!1-0-cib.110x100.jpg"
_FULL = "https://cbu01.alicdn.com/img/ibank/2019/055/963/11322369550_823790914.jpg"
_CABIN = (
    "https://188.com.vn/uploads/balo-size-cabin-40x25x20cm-mau-hong.jpg"
)


def test_detail_content_excludes_png_and_size_tokens():
    assert is_excluded_detail_content_image(_PNG)
    assert is_excluded_detail_content_image(_THUMB)
    assert is_excluded_detail_content_image(_THUMB_300)
    assert is_excluded_detail_content_image(_THUMB_110)
    assert not is_excluded_detail_content_image(_FULL)
    assert not is_excluded_detail_content_image(_CABIN)


def test_1688_gallery_drops_png_and_sized_thumbs():
    payload = {
        "structured": {
            "detail_images": [_PNG, _THUMB, _THUMB_110, _FULL],
            "carousel_images": [],
            "title_candidates": ["Áo khoác nam dáng dài mùa đông"],
        },
        "html_sample": "",
        "scripts": [],
        "document_title": "Áo khoác nam dáng dài mùa đông",
        "h1": "Áo khoác nam dáng dài mùa đông",
    }
    product = normalize_1688_payload(
        "https://detail.1688.com/offer/1234567890.html",
        "1234567890",
        payload,
    )
    gallery = product.get("gallery") or []
    assert _FULL in gallery
    assert all(not u.lower().split("?", 1)[0].endswith(".png") for u in gallery)
    assert all("310x310" not in u and "720x720" not in u and "110x100" not in u for u in gallery)
