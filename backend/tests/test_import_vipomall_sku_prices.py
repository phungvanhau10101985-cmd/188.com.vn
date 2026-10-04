"""Vipomall API: mỗi SKU giữ tên, ảnh, mã, tệ và giá bán riêng."""

from types import SimpleNamespace

from app.services.import_vipomall_scraper import (
    _listing_vnd_for_cny,
    vipomall_api_detail_to_product_data,
    vipomall_label_is_model_code,
)
from app.services.variant_sale_price import resolve_variant_quote


def _sku(sku_id, name, cny, img, stock=10, *, color=None, size=None):
    props = []
    if color is not None or size is None and color is None and size is None:
        props.append(
            {
                "prop_name": "Model Quy cách" if color is None and size is None else "Màu sắc",
                "value_name": name if color is None and size is None else color,
            }
        )
    if size:
        if not props:
            props.append({"prop_name": "Màu sắc", "value_name": color or name})
        props.append({"prop_name": "Kích cỡ", "value_name": size})
    return {
        "sku_id": sku_id,
        "price": cny,
        "stock": stock,
        "img_url": img,
        "sku_prop_list": props,
    }


def test_api_detail_maps_each_model_price_image_and_code():
    detail = {
        "product_name": "Van điện từ",
        "original_product_name": "电磁阀",
        "original_product_url": "https://detail.1688.com/offer/1217276629.html",
        "original_shop_name": "余姚店",
        "shop_name": "Yongchuang",
        "main_img_url_list": ["https://cbu01.alicdn.com/img/ibank/gallery.jpg"],
        "description": '<p>Mo ta</p><img src="https://cbu01.alicdn.com/img/ibank/detail.jpg">',
        "product_sku_info_list": [
            _sku("1", "2W41-15GBN-AC220V", 77, "https://cbu01.alicdn.com/img/ibank/cheap.jpg"),
            _sku("2", "2W41-50GBN-AC220V", 440, "https://cbu01.alicdn.com/img/ibank/dear.jpg", stock=0),
            _sku("3", "2W41-50GBN-DC24V", 440, "https://cbu01.alicdn.com/img/ibank/dear-dc.jpg"),
        ],
    }
    product = vipomall_api_detail_to_product_data(
        detail,
        "https://vipomall.vn/san-pham/1217276629?platform_type=10&merchant_id=101",
        "1217276629",
    )
    colors = product["colors"]
    assert [c["name"] for c in colors] == ["2W41-15GBN-AC220V", "2W41-50GBN-DC24V"]
    assert colors[0]["sku"] == "2W41-15GBN-AC220V"
    assert colors[0]["sku_code"] == "2W41-15GBN-AC220V"
    assert colors[0]["price_cny"] == 77
    assert colors[0]["price"] == _listing_vnd_for_cny(77)
    assert "cheap.jpg" in colors[0]["img"]
    assert colors[1]["price_cny"] == 440
    assert colors[1]["price"] == _listing_vnd_for_cny(440)
    assert colors[1]["price"] > colors[0]["price"]
    assert product["price"] == colors[0]["price"]
    assert product["pro_lower_price"] == "77"
    assert product["pro_high_price"] == "440"
    assert product["cost_cny"] == 77
    assert product["main_image"].endswith("cheap.jpg") or "cheap.jpg" in product["main_image"]
    assert product["chinese_name"] == "电磁阀"
    assert "detail.1688.com" in product["link_default"]
    assert any("detail.jpg" in u for u in product["gallery"])


def test_api_detail_color_and_size_keep_pair_price():
    detail = {
        "product_name": "Áo",
        "product_sku_info_list": [
            {
                "sku_id": "s1",
                "price": 80,
                "stock": 3,
                "img_url": "https://cbu01.alicdn.com/img/ibank/red.jpg",
                "sku_prop_list": [
                    {"prop_name": "Màu sắc", "value_name": "Đỏ"},
                    {"prop_name": "Kích cỡ", "value_name": "S"},
                ],
            },
            {
                "sku_id": "m1",
                "price": 120,
                "stock": 3,
                "img_url": "https://cbu01.alicdn.com/img/ibank/red.jpg",
                "sku_prop_list": [
                    {"prop_name": "Màu sắc", "value_name": "Đỏ"},
                    {"prop_name": "Kích cỡ", "value_name": "M"},
                ],
            },
        ],
    }
    product = vipomall_api_detail_to_product_data(detail, "https://vipomall.vn/san-pham/9?platform_type=10", "9")
    assert [c["name"] for c in product["colors"]] == ["Đỏ"]
    assert product["colors"][0]["sku"] == "Đỏ"
    assert product["colors"][0]["price"] == _listing_vnd_for_cny(80)
    assert "red.jpg" in product["colors"][0]["img"]
    assert product["sizes"] == ["S", "M"]
    pairs = product["product_info"]["variants"]["pairs"]
    assert len(pairs) == 2
    by_size = {p["size"]: p for p in pairs}
    assert by_size["M"]["price"] == _listing_vnd_for_cny(120)
    assert by_size["M"]["sku_code"] == "m1"
    assert by_size["M"]["price_cny"] == 120

    stub = SimpleNamespace(colors=product["colors"], product_info=product["product_info"])
    quote = resolve_variant_quote(stub, "Đỏ", "M")
    assert quote["price"] == _listing_vnd_for_cny(120)
    assert quote["sku_code"] == "m1"
    assert quote["price_cny"] == 120
    cheap = resolve_variant_quote(stub, "Đỏ", "")
    assert cheap["price"] == _listing_vnd_for_cny(80)

    from app.services.product_info_web_compact import compact_product_info_for_web

    packed = {"product_info": product["product_info"]}
    compact_product_info_for_web(packed)
    kept = packed["product_info"]["variants"]["price_pairs"]
    assert {row["size"]: row["sku_code"] for row in kept} == {"S": "s1", "M": "m1"}


def test_model_code_is_not_translated_chinese_color_is(monkeypatch):
    assert vipomall_label_is_model_code("2W41-15GBN-AC220V") is True
    assert vipomall_label_is_model_code("红色") is False

    def _fake_translate(entries):
        for entry in entries:
            if entry.get("name") == "红色":
                entry["name"] = "Đỏ"

    monkeypatch.setattr(
        "app.services.variant_color_translate.apply_deepseek_translations_to_color_entries",
        _fake_translate,
    )
    detail = {
        "product_name": "Áo",
        "product_sku_info_list": [
            _sku("1", "2W41-15GBN-AC220V", 77, "https://cbu01.alicdn.com/img/ibank/a.jpg"),
            {
                "sku_id": "c1",
                "price": 80,
                "stock": 4,
                "img_url": "https://cbu01.alicdn.com/img/ibank/red.jpg",
                "sku_prop_list": [{"prop_name": "颜色", "value_name": "红色"}],
            },
        ],
    }
    product = vipomall_api_detail_to_product_data(detail, "https://vipomall.vn/san-pham/1?platform_type=10", "1")
    by_name = {c["name"]: c for c in product["colors"]}
    assert "2W41-15GBN-AC220V" in by_name
    assert by_name["2W41-15GBN-AC220V"]["sku"] == "2W41-15GBN-AC220V"
    assert by_name["Đỏ"]["sku"] == "Đỏ"
    assert "红色" not in by_name
