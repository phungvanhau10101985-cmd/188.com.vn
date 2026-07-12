from app.models.product import Product
from app.services.catalog_internal_labels import (
    extract_phone_device_labels,
    is_phone_accessory_product,
    meta_internal_labels_for_product,
)


def _product(**kwargs) -> Product:
    p = Product()
    for k, v in kwargs.items():
        setattr(p, k, v)
    return p


def test_extract_iphone_15_pro_max():
    labels = extract_phone_device_labels("Ốp lưng iPhone 15 Pro Max trong suốt")
    assert "iphone_15" in labels
    assert "iphone_15_pro_max" in labels


def test_extract_iphone_16_17_slash():
    labels = extract_phone_device_labels("Ốp lưng iphone 16/17 pro da cá sấu")
    assert "iphone_16" in labels
    assert "iphone_17" in labels


def test_extract_samsung_s24_ultra():
    labels = extract_phone_device_labels("Ốp Samsung Galaxy S24 Ultra chống sốc")
    assert "samsung_s24_ultra" in labels
    assert "samsung_ultra_24" in labels


def test_extract_samsung_ultra_25_short():
    labels = extract_phone_device_labels("Bao da Samsung Ultra 25")
    assert "samsung_ultra_25" in labels


def test_phone_accessory_internal_labels_auto():
    p = _product(
        name="Ốp lưng điện thoại iPhone 16 Pro",
        category="Phụ kiện điện thoại & công nghệ",
        subcategory="Ốp lưng điện thoại",
        sub_subcategory="Ốp lưng iPhone",
        product_info={},
    )
    cell = meta_internal_labels_for_product(p)
    assert cell.startswith("[")
    assert "'phu_kien_dien_thoai'" in cell
    assert "'iphone_16'" in cell


def test_internal_label_override_from_product_info():
    p = _product(
        name="Ốp lưng iPhone 15",
        category="Phụ kiện",
        product_info={"internal_labels": ["iphone_15", "sale_tet"]},
    )
    cell = meta_internal_labels_for_product(p)
    assert "'iphone_15'" in cell
    assert "'sale_tet'" in cell
    assert "phu_kien_dien_thoai" not in cell


def test_is_phone_accessory_by_category():
    p = _product(
        name="Miếng dán kính cường lực",
        subcategory="Phụ kiện điện thoại",
    )
    assert is_phone_accessory_product(p) is True
