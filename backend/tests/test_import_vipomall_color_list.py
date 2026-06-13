"""Vipomall: màu/variant + ảnh từ .product-type-list-size (section «Màu sắc» / «Mẫu»)."""

from app.services.import_vipomall_scraper import vipomall_row_to_product_data

_VIPOMALL_COLOR_LIST_RAW = {
    "title": "Túi xách unicorn",
    "colors": [
        {
            "label": "Vàng cổ điển",
            "image_url": "https://cbu01.alicdn.com/img/ibank/O1CN01EK9l6d1JwdcJCpDCd_!!2200953351093-0-cib.jpg",
        },
        {
            "label": "Nâu cổ điển",
            "image_url": "https://cbu01.alicdn.com/img/ibank/O1CN01FhjZwi1JwdcO4j2T1_!!2200953351093-0-cib.jpg",
        },
        {
            "label": "Xanh lá cổ điển",
            "image_url": "https://cbu01.alicdn.com/img/ibank/O1CN013vTt661JwdcNKeCTJ_!!2200953351093-0-cib.jpg",
        },
    ],
    "variant_rows": [
        {
            "color": "Vàng cổ điển",
            "size": "",
            "stock": 14,
            "price_vnd": 663850,
            "price_text": "663.850 đ",
            "stock_text": "(14 SP có sẵn)",
            "in_stock": True,
        },
        {
            "color": "Nâu cổ điển",
            "size": "",
            "stock": 38,
            "price_vnd": 663850,
            "price_text": "663.850 đ",
            "stock_text": "(38 SP có sẵn)",
            "in_stock": True,
        },
        {
            "color": "Xanh lá cổ điển",
            "size": "",
            "stock": 37,
            "price_vnd": 663850,
            "price_text": "663.850 đ",
            "stock_text": "(37 SP có sẵn)",
            "in_stock": True,
        },
    ],
    "sizes": [],
    "gallery_images": [],
    "detail_images": [],
}


def test_vipomall_color_list_section_maps_to_colors_with_images():
    product = vipomall_row_to_product_data(
        _VIPOMALL_COLOR_LIST_RAW,
        "https://vipomall.vn/san-pham/123?platform_type=10",
        "123",
    )
    colors = product.get("colors") or []
    assert len(colors) == 3
    assert colors[0]["name"] == "Vàng cổ điển"
    assert "O1CN01EK9l6d1JwdcJCpDCd" in colors[0]["img"]
    assert colors[1]["name"] == "Nâu cổ điển"
    assert "O1CN01FhjZwi1JwdcO4j2T1" in colors[1]["img"]
    assert colors[2]["name"] == "Xanh lá cổ điển"
    assert "O1CN013vTt661JwdcNKeCTJ" in colors[2]["img"]
    assert product.get("color_swatch_images_1688") == [c["img"] for c in colors]
    assert product.get("sizes") == []
    assert product.get("product_info", {}).get("variants", {}).get("sizes") is None
    assert product.get("price") == 663850.0


def test_vipomall_color_only_layout_ignores_stale_size_list_from_scraper():
    """Dù JS còn sizeSet cũ (tên màu), layout chỉ-màu vẫn ép sizes=[]."""
    raw = {
        **_VIPOMALL_COLOR_LIST_RAW,
        "sizes": ["Vàng cổ điển", "Nâu cổ điển"],
    }
    product = vipomall_row_to_product_data(
        raw,
        "https://vipomall.vn/san-pham/123?platform_type=10",
        "123",
    )
    assert product.get("sizes") == []


_VIPOMALL_VARIANT_ONLY_RAW = {
    "title": "JZQ012 bóng bơm hơi thông minh",
    "colors": [
        {
            "label": "JZQ012 bóng bơm hơi thông minh màu đen",
            "image_url": "https://cbu01.alicdn.com/img/ibank/O1CN01Hm7Csd1POBoG5SVRY_!!946661830-0-cib.jpg",
        },
        {
            "label": "JZQ012 bóng bơm hơi thông minh màu xám",
            "image_url": "https://cbu01.alicdn.com/img/ibank/O1CN01qp6L1B1POBoFdCMLI_!!946661830-0-cib.jpg",
        },
        {
            "label": "JZQ012 bóng bơm hơi thông minh màu đỏ hồng",
            "image_url": "https://cbu01.alicdn.com/img/ibank/O1CN01FW9Fqy1POBoGfvOya_!!946661830-0-cib.jpg",
        },
    ],
    "variant_rows": [
        {
            "color": "JZQ012 bóng bơm hơi thông minh màu đen",
            "size": "",
            "image_url": "https://cbu01.alicdn.com/img/ibank/O1CN01Hm7Csd1POBoG5SVRY_!!946661830-0-cib.jpg",
            "stock": 5368,
            "price_vnd": 140971,
            "price_text": "140.971 đ",
            "stock_text": "(5368 SP có sẵn)",
            "in_stock": True,
        },
        {
            "color": "JZQ012 bóng bơm hơi thông minh màu xám",
            "size": "",
            "image_url": "https://cbu01.alicdn.com/img/ibank/O1CN01qp6L1B1POBoFdCMLI_!!946661830-0-cib.jpg",
            "stock": 1495,
            "price_vnd": 140971,
            "price_text": "140.971 đ",
            "stock_text": "(1495 SP có sẵn)",
            "in_stock": True,
        },
        {
            "color": "JZQ012 bóng bơm hơi thông minh màu đỏ hồng",
            "size": "",
            "image_url": "https://cbu01.alicdn.com/img/ibank/O1CN01FW9Fqy1POBoGfvOya_!!946661830-0-cib.jpg",
            "stock": 1033,
            "price_vnd": 140971,
            "price_text": "140.971 đ",
            "stock_text": "(1033 SP có sẵn)",
            "in_stock": True,
        },
    ],
    "sizes": [],
    "gallery_images": [],
    "detail_images": [],
}


def test_vipomall_variant_only_product_names_map_to_colors_without_sizes():
    product = vipomall_row_to_product_data(
        _VIPOMALL_VARIANT_ONLY_RAW,
        "https://vipomall.vn/san-pham/456?platform_type=10",
        "456",
    )
    colors = product.get("colors") or []
    assert len(colors) == 3
    assert "màu đen" in colors[0]["name"]
    assert "O1CN01Hm7Csd1POBoG5SVRY" in colors[0]["img"]
    assert product.get("sizes") == []
    assert product.get("product_info", {}).get("variants", {}).get("variant_only") is True
    assert product.get("price") == 140971.0
    pairs = product.get("product_info", {}).get("variants", {}).get("pairs") or []
    assert len(pairs) == 3
    assert pairs[0].get("size") == ""


def test_vipomall_remaps_mislabeled_variant_rows_from_size_field():
    """JS section unknown có thể gán tên variant vào size — Python chuyển về colors."""
    raw = {
        "title": "JZQ012",
        "colors": [],
        "variant_rows": [
            {
                "color": "",
                "size": "JZQ012 bóng bơm hơi thông minh màu đen",
                "image_url": "https://cbu01.alicdn.com/img/ibank/O1CN01Hm7Csd1POBoG5SVRY_!!946661830-0-cib.jpg",
                "stock": 100,
                "price_vnd": 140971,
                "in_stock": True,
            },
        ],
        "sizes": ["JZQ012 bóng bơm hơi thông minh màu đen"],
        "gallery_images": [],
        "detail_images": [],
    }
    product = vipomall_row_to_product_data(
        raw,
        "https://vipomall.vn/san-pham/456?platform_type=10",
        "456",
    )
    assert len(product.get("colors") or []) == 1
    assert product.get("sizes") == []
    assert "màu đen" in (product.get("colors") or [])[0]["name"]
