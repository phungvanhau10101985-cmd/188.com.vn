import pytest
from pydantic import ValidationError

from app.schemas.address import AddressCreate


def test_address_normalizes_phone_and_blank_district():
    addr = AddressCreate(
        full_name="Mr Hậu",
        phone="0965 384 188",
        province="Tỉnh Vĩnh Long",
        district="  ",
        ward="Phường Bến Tre",
        street_address="  12 Nguyễn Huệ  ",
    )
    assert addr.phone == "0965384188"
    assert addr.district is None
    assert addr.street_address == "12 Nguyễn Huệ"


def test_address_rejects_short_street_in_vietnamese():
    with pytest.raises(ValidationError) as exc:
        AddressCreate(
            full_name="Mr Hậu",
            phone="0965384188",
            street_address="12",
        )
    assert "Địa chỉ cụ thể" in str(exc.value)


def test_address_rejects_bad_phone_in_vietnamese():
    with pytest.raises(ValidationError) as exc:
        AddressCreate(
            full_name="Mr Hậu",
            phone="123",
            street_address="12 Nguyễn Huệ",
        )
    assert "Số điện thoại" in str(exc.value)
