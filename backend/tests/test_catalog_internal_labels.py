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
    assert "samsung" in labels
    assert "samsung_galaxy_s" in labels
    assert "samsung_s24" in labels
    assert "samsung_s24_ultra" in labels
    assert "samsung_ultra_24" in labels


def test_extract_samsung_s26_plus_includes_brand_and_base_model():
    labels = extract_phone_device_labels("Kính cường lực NILLKIN cho Samsung S26 Plus")
    assert "samsung" in labels
    assert "samsung_s26" in labels
    assert "samsung_s26_plus" in labels


def test_extract_samsung_ultra_25_short():
    labels = extract_phone_device_labels("Bao da Samsung Ultra 25")
    assert "samsung" in labels
    assert "samsung_ultra_25" in labels


def test_extract_samsung_galaxy_a_series():
    labels = extract_phone_device_labels("Op lung Samsung Galaxy A54 / A55 5G")
    assert "samsung" in labels
    assert "samsung_galaxy_a" in labels
    assert "samsung_a54" in labels
    assert "samsung_a55" in labels


def test_extract_samsung_galaxy_m_and_f():
    labels_m = extract_phone_device_labels("Bao Galaxy M34 5G")
    assert "samsung_galaxy_m" in labels_m
    assert "samsung_m34" in labels_m
    labels_f = extract_phone_device_labels("Op Samsung F54")
    assert "samsung_galaxy_f" in labels_f
    assert "samsung_f54" in labels_f


def test_extract_samsung_z_flip_and_note():
    labels_z = extract_phone_device_labels("Op Galaxy Z Flip 6")
    assert "samsung_galaxy_z" in labels_z
    assert "samsung_z_flip" in labels_z
    assert "samsung_z_flip_6" in labels_z
    labels_n = extract_phone_device_labels("Op Note 20 Ultra Samsung")
    assert "samsung_galaxy_note" in labels_n
    assert "samsung_note_20" in labels_n
    assert "samsung_note_20_ultra" in labels_n


def test_extract_samsung_tab_not_confused_with_s_series():
    labels = extract_phone_device_labels("Mieng dan Tab S9 Ultra Samsung")
    assert "samsung_galaxy_tab" in labels
    assert "samsung_tab_s9" in labels
    assert "samsung_tab_s9_ultra" in labels
    assert "samsung_s9" not in labels


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
    assert "'iphone'" in cell
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
