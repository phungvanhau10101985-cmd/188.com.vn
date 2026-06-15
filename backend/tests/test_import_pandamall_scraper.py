"""PandaMall: URL + map variant màu/size từ scrape DOM."""

from app.services.import_batch_url_coercion import (
    FETCH_TARGET_PANDAMALL,
    coerce_url_for_excel_batch_import,
)
from app.services.import_pandamall_scraper import (
    PANDAMALL_PLATFORM_1688,
    PANDAMALL_PLATFORM_TAOBAO,
    build_pandamall_1688_pdp_url,
    build_pandamall_taobao_pdp_url,
    extract_pandamall_detail,
    is_pandamall_import_url,
    pandamall_row_to_product_data,
    resolve_pandamall_import_url,
)
from app.api.endpoints.import_1688 import _infer_import_source_for_url


def test_extract_pandamall_detail_1688():
    detail = extract_pandamall_detail("https://pandamall.vn/1688/detail/935969699245")
    assert detail == ("935969699245", PANDAMALL_PLATFORM_1688)


def test_extract_pandamall_detail_taobao():
    detail = extract_pandamall_detail("https://pandamall.vn/taobao/detail/1049735896483")
    assert detail == ("1049735896483", PANDAMALL_PLATFORM_TAOBAO)


def test_resolve_pandamall_from_1688_offer():
    url, platform = resolve_pandamall_import_url("https://detail.1688.com/offer/935969699245.html")
    assert url == build_pandamall_1688_pdp_url("935969699245")
    assert platform == PANDAMALL_PLATFORM_1688


def test_infer_import_source_pandamall_url():
    ext_id, src = _infer_import_source_for_url("https://pandamall.vn/1688/detail/935969699245")
    assert ext_id == "935969699245"
    assert src == "pandamall"


def test_coerce_excel_batch_to_pandamall():
    url, err = coerce_url_for_excel_batch_import(
        "https://detail.1688.com/offer/935969699245.html",
        FETCH_TARGET_PANDAMALL,
    )
    assert err is None
    assert url == build_pandamall_1688_pdp_url("935969699245")


def test_coerce_taobao_to_pandamall():
    url, err = coerce_url_for_excel_batch_import("T1049735896483", FETCH_TARGET_PANDAMALL)
    assert err is None
    assert url == build_pandamall_taobao_pdp_url("1049735896483")


_PANDAMALL_BOOT_RAW = {
    "title": "Bốt nữ cao gót",
    "colors": [
        {
            "label": "Màu đỏ",
            "image_url": "https://cbu01.alicdn.com/img/ibank/O1CN01TcAxsb1j8QUCo5w3p_!!4217214503-0-cib.jpg_300x300.jpg",
            "price_vnd": 678300,
            "price_cny": "170",
            "stock": 100,
            "stock_text": "(100 sản phẩm có sẵn)",
            "in_stock": True,
        },
        {
            "label": "Màu đen",
            "image_url": "https://cbu01.alicdn.com/img/ibank/O1CN014sqMvw1j8QUBWJapg_!!4217214503-0-cib.jpg_300x300.jpg",
            "price_vnd": 678300,
            "price_cny": "170",
            "stock": 100,
            "stock_text": "(100 sản phẩm có sẵn)",
            "in_stock": True,
        },
    ],
    "sizes": ["35", "36", "37", "38", "39"],
    "variant_rows": [
        {"color": "Màu đỏ", "size": "35", "price_vnd": 678300, "stock": 100, "in_stock": True},
        {"color": "Màu đỏ", "size": "36", "price_vnd": 678300, "stock": 100, "in_stock": True},
        {"color": "Màu đen", "size": "35", "price_vnd": 678300, "stock": 100, "in_stock": True},
    ],
    "gallery_images": [
        "https://cbu01.alicdn.com/img/ibank/O1CN01D8auLt1j8QUAIJPpw_!!4217214503-0-cib.jpg_100x100.jpg",
    ],
    "detail_images": [
        "https://cbu01.alicdn.com/img/ibank/O1CN01D8auLt1j8QUAIJPpw_!!4217214503-0-cib.jpg",
    ],
    "info_texts": [
        "Danh mục sản phẩm: Bốt thời trang",
        "Giới tính áp dụng: Nữ",
        "Màu sắc: Màu đỏ, Màu mơ, Màu đen",
    ],
    "cny_price_texts": ["170"],
}


def test_pandamall_row_maps_colors_sizes_and_product_id():
    product = pandamall_row_to_product_data(
        _PANDAMALL_BOOT_RAW,
        "https://pandamall.vn/1688/detail/935969699245",
        "935969699245",
        platform=PANDAMALL_PLATFORM_1688,
    )
    assert product["product_id"] == "A935969699245"
    assert product["origin"] == "1688"
    assert len(product["colors"]) == 2
    assert product["colors"][0]["name"] == "Màu đỏ"
    assert "O1CN01TcAxsb1j8QUCo5w3p" in product["colors"][0]["img"]
    assert product["sizes"] == ["35", "36", "37", "38", "39"]
    assert product["price"] == 678300.0
    assert product["pro_lower_price"] == "170"
    assert product["product_info"]["variants"]["source"] == "pandamall"
    pairs = product["product_info"]["variants"]["pairs"]
    assert {"color": "Màu đỏ", "size": "35"} in pairs
    assert is_pandamall_import_url("https://pandamall.vn/taobao/detail/1049735896483")


_PANDAMALL_SHIRT_GALLERY_THUMBS = [
    "https://cbu01.alicdn.com/img/ibank/O1CN015pV83s1rvtsXYEkZq_!!3906805694-0-cib.jpg_100x100.jpg",
    "https://cbu01.alicdn.com/img/ibank/O1CN01PEcjge1rvtsZ0UoPl_!!3906805694-0-cib.jpg_100x100.jpg",
    "https://cbu01.alicdn.com/img/ibank/O1CN01yGNINB1rvtsNxdL9f_!!3906805694-0-cib.jpg_100x100.jpg",
    "https://cbu01.alicdn.com/img/ibank/O1CN01jj6FZY1rvuL9nm5VO_!!3906805694-0-cib.jpg_100x100.jpg",
    "https://cbu01.alicdn.com/img/ibank/O1CN0187xD8H1rvuL9LkxKI_!!3906805694-0-cib.jpg_100x100.jpg",
]


def test_pandamall_gallery_from_swiper_thumb_strip():
    raw = {
        "title": "Áo sơ mi nam",
        "colors": [],
        "sizes": ["M/38", "L/39"],
        "variant_rows": [],
        "gallery_images": _PANDAMALL_SHIRT_GALLERY_THUMBS,
        "detail_images": [],
    }
    product = pandamall_row_to_product_data(
        raw,
        "https://pandamall.vn/1688/detail/123456789",
        "123456789",
    )
    assert len(product["images"]) == 5
    assert all("_100x100" not in u for u in product["images"])
    assert product["images"][0].endswith("O1CN015pV83s1rvtsXYEkZq_!!3906805694-0-cib.jpg")
    assert product["main_image"] == product["images"][0]


_PANDAMALL_SWIPE_COLOR_RAW = {
    "title": "Giày cao gót",
    "layout_mode": "color_only",
    "colors": [
        {
            "label": "Màu cam 14cm",
            "image_url": "https://img.alicdn.com/bao/uploaded/i2/1678094875/TB2hTFJdlNkpuFjy0FaXXbRCVXa_!!1678094875.jpg_500x500.jpg",
            "in_stock": True,
        },
        {
            "label": "Màu cam 16cm",
            "image_url": "https://img.alicdn.com/bao/uploaded/i2/1678094875/TB2nMl3dbRkpuFjSspmXXc.9XXa_!!1678094875.jpg_500x500.jpg",
            "in_stock": True,
        },
        {
            "label": "Nude 14cm (Màu da, 14cm)",
            "image_url": "https://img.alicdn.com/bao/uploaded/i4/1678094875/TB2Ya0PdbXlpuFjSszfXXcSGXXa_!!1678094875.jpg_500x500.jpg",
            "in_stock": True,
        },
        {
            "label": "Đen 14cm",
            "image_url": "https://img.alicdn.com/bao/uploaded/i3/1678094875/TB2Sr8QdmtkpuFjy0FhXXXQzFXa_!!1678094875.jpg_500x500.jpg",
            "in_stock": True,
        },
    ],
    "variant_rows": [
        {"color": "Màu cam 14cm", "size": "", "in_stock": True},
        {"color": "Màu cam 16cm", "size": "", "in_stock": True},
        {"color": "Nude 14cm (Màu da, 14cm)", "size": "", "in_stock": True},
        {"color": "Đen 14cm", "size": "", "in_stock": True},
    ],
    "sizes": [],
    "gallery_images": [],
    "detail_images": [],
}


def test_pandamall_ver_swipe_color_buttons_map_variants_and_first_jpg():
    product = pandamall_row_to_product_data(
        _PANDAMALL_SWIPE_COLOR_RAW,
        "https://pandamall.vn/taobao/detail/123456789",
        "123456789",
        platform=PANDAMALL_PLATFORM_TAOBAO,
    )
    colors = product.get("colors") or []
    assert len(colors) == 4
    assert colors[0]["name"] == "Màu cam 14cm"
    assert colors[0]["img"].endswith("TB2hTFJdlNkpuFjy0FaXXbRCVXa_!!1678094875.jpg")
    assert "_500x500" not in colors[0]["img"]
    assert product.get("sizes") == []
    variants = product.get("product_info", {}).get("variants", {})
    assert variants.get("variant_only") is True
    pairs = variants.get("pairs") or []
    assert {"color": "Màu cam 14cm", "size": ""} in pairs


_PANDAMALL_BAG_RAW = {
    "title": "Túi xách nữ",
    "layout_mode": "color_only",
    "colors": [
        {
            "label": "Xám cổ điển",
            "image_url": "https://cbu01.alicdn.com/img/ibank/22679636703_2115707610.jpg_300x300.jpg",
            "price_vnd": 837900,
            "price_cny": "210",
            "stock": 50,
            "stock_text": "(50 sản phẩm có sẵn)",
            "in_stock": True,
        },
        {
            "label": "Vàng cổ điển",
            "image_url": "https://cbu01.alicdn.com/img/ibank/22587145244_2115707610.jpg_300x300.jpg",
            "price_vnd": 837900,
            "price_cny": "210",
            "stock": 130,
            "stock_text": "(130 sản phẩm có sẵn)",
            "in_stock": True,
        },
        {
            "label": "Xanh lá cổ điển",
            "image_url": "https://cbu01.alicdn.com/img/ibank/22587124757_2115707610.jpg_300x300.jpg",
            "price_vnd": 837900,
            "price_cny": "210",
            "stock": 125,
            "stock_text": "(125 sản phẩm có sẵn)",
            "in_stock": True,
        },
        {
            "label": "Nâu cổ điển",
            "image_url": "https://cbu01.alicdn.com/img/ibank/22504341850_2115707610.jpg_300x300.jpg",
            "price_vnd": 837900,
            "price_cny": "210",
            "stock": 49,
            "stock_text": "(49 sản phẩm có sẵn)",
            "in_stock": True,
        },
    ],
    "variant_rows": [
        {"color": "Xám cổ điển", "size": "", "price_vnd": 837900, "stock": 50, "in_stock": True},
        {"color": "Vàng cổ điển", "size": "", "price_vnd": 837900, "stock": 130, "in_stock": True},
        {"color": "Xanh lá cổ điển", "size": "", "price_vnd": 837900, "stock": 125, "in_stock": True},
        {"color": "Nâu cổ điển", "size": "", "price_vnd": 837900, "stock": 49, "in_stock": True},
    ],
    "sizes": [],
    "gallery_images": [],
    "detail_images": [],
    "cny_price_texts": ["210"],
}


def test_pandamall_bag_color_only_maps_variants_without_sizes():
    product = pandamall_row_to_product_data(
        _PANDAMALL_BAG_RAW,
        "https://pandamall.vn/1688/detail/123456789",
        "123456789",
    )
    colors = product.get("colors") or []
    assert len(colors) == 4
    assert colors[0]["name"] == "Xám cổ điển"
    assert "22679636703_2115707610" in colors[0]["img"]
    assert product.get("sizes") == []
    assert product.get("price") == 837900.0
    assert product.get("pro_lower_price") == "210"
    variants = product.get("product_info", {}).get("variants", {})
    assert variants.get("variant_only") is True
    assert variants.get("sizes") is None
    pairs = variants.get("pairs") or []
    assert len(pairs) == 4
    assert all(p.get("size") == "" for p in pairs)
    assert {"color": "Vàng cổ điển", "size": ""} in pairs


def test_pandamall_color_only_ignores_stale_size_list_from_scraper():
    raw = {**_PANDAMALL_BAG_RAW, "sizes": ["Xám cổ điển", "Vàng cổ điển"]}
    product = pandamall_row_to_product_data(
        raw,
        "https://pandamall.vn/1688/detail/123456789",
        "123456789",
    )
    assert product.get("sizes") == []
