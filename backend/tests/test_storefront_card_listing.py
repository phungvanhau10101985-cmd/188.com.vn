"""Thẻ danh mục chỉ giữ field đang vẽ. Job ảnh không nằm trong uvicorn."""

from types import SimpleNamespace

from app.models.product import Product

from app.services.image_localization_job_runtime import image_localization_embedded_in_api
from app.services.storefront_card_listing import (
    build_storefront_card_payload,
    card_listing_query_options,
    is_storefront_category_card_request,
    is_storefront_grid_card_request,
    slim_product_info_for_card,
)


def test_home_grid_uses_card_payload_without_search():
    assert is_storefront_grid_card_request(
        admin_list=False,
        q="",
        product_id="",
        warehouse_clearance_only=False,
    )
    assert not is_storefront_grid_card_request(
        admin_list=False,
        q="áo thun",
        product_id="",
        warehouse_clearance_only=False,
    )
    assert not is_storefront_grid_card_request(
        admin_list=False,
        q="",
        product_id="A1",
        warehouse_clearance_only=False,
    )


def test_category_card_request_is_only_category_browse():
    assert is_storefront_category_card_request(
        admin_list=False,
        q="",
        product_id="",
        warehouse_clearance_only=False,
        category="Thời trang Nữ",
        subcategory=None,
        sub_subcategory=None,
    )
    assert not is_storefront_category_card_request(
        admin_list=False,
        q="áo thun",
        product_id="",
        warehouse_clearance_only=False,
        category="Thời trang Nữ",
        subcategory=None,
        sub_subcategory=None,
    )
    assert not is_storefront_category_card_request(
        admin_list=True,
        q="",
        product_id="",
        warehouse_clearance_only=False,
        category="Thời trang Nữ",
        subcategory=None,
        sub_subcategory=None,
    )
    assert not is_storefront_category_card_request(
        admin_list=False,
        q="",
        product_id="",
        warehouse_clearance_only=True,
        category="Thời trang Nữ",
        subcategory=None,
        sub_subcategory=None,
    )
    assert not is_storefront_category_card_request(
        admin_list=False,
        q="",
        product_id="",
        warehouse_clearance_only=False,
        category=None,
        subcategory=None,
        sub_subcategory=None,
    )


def test_card_payload_keeps_tile_fields_and_drops_heavy_ones():
    product = SimpleNamespace(
        id=7,
        product_id="A1",
        code="U1",
        name="Áo",
        slug="ao",
        price=100000,
        brand_name="188",
        main_image="",
        images=["https://cdn.example/1.jpg", "https://cdn.example/2.jpg", "https://cdn.example/3.jpg"],
        video_link="https://cdn.example/v.mp4",
        available=3,
        sizes=["M"],
        colors=[{"name": "Đen", "price": 100000}, {"name": "Trắng", "price": 120000}],
        color="Đen",
        product_info={
            "specifications": {"style": "bỏ"},
            "variants": {
                "pairs": [{"color": "Đen", "size": "M", "price": 100000}],
                "price_pairs": [{"price": 120000}],
            },
        },
        description="mô tả dài",
        gallery=["https://cdn.example/detail.jpg"],
        cost_cny=10,
        meta_title="seo",
        chinese_name="中文",
        category="Thời trang Nữ",
        subcategory="Áo",
        sub_subcategory=None,
        category_id=4,
        is_active=True,
        is_warehouse_clearance=False,
        base_sku=None,
        deposit_require=False,
        purchases=9,
        rating_point=4.5,
        rating_total=12,
        source_stock_status="unknown",
    )
    payload = build_storefront_card_payload(product)
    assert payload["images"] == ["https://cdn.example/1.jpg", "https://cdn.example/2.jpg"]
    assert payload["product_info"] == {
        "variants": {
            "pairs": [{"color": "Đen", "size": "M", "price": 100000}],
            "price_pairs": [{"price": 120000}],
        }
    }
    assert payload["video_link"].endswith("v.mp4")
    assert payload["purchases"] == 9
    for key in ("description", "gallery", "cost_cny", "meta_title", "chinese_name"):
        assert key not in payload
    assert slim_product_info_for_card({"specifications": {"a": 1}}) is None


def test_card_listing_select_omits_description_and_gallery():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db = sessionmaker(bind=create_engine("sqlite://"))()
    try:
        query = db.query(Product).options(*card_listing_query_options()).filter(Product.id.in_([1]))
        sql = str(query.statement.compile(compile_kwargs={"literal_binds": True})).lower()
    finally:
        db.close()
    assert "products.description" not in sql
    assert "products.gallery" not in sql
    assert "products.consult_image_text" not in sql
    assert "products.main_image" in sql
    assert "products.images" in sql


def test_image_localization_is_not_embedded_in_api_by_default(monkeypatch):
    from app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "IMAGE_LOCALIZATION_EMBEDDED_IN_API", False, raising=False)
    assert image_localization_embedded_in_api() is False
