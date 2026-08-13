"""404 nghiệp vụ vs 404 route không tồn tại."""
from types import SimpleNamespace

from app.core.http_errors import business_404_content


def test_business_404_keeps_vietnamese_phone_message():
    exc = SimpleNamespace(detail="Không tìm thấy đơn hàng với số điện thoại này.")
    assert business_404_content(exc) == {
        "detail": "Không tìm thấy đơn hàng với số điện thoại này.",
    }


def test_business_404_keeps_dict_payload():
    payload = {
        "ok": False,
        "detail": "Không tìm thấy đơn hàng với số điện thoại này.",
        "query": "0369597965",
        "query_type": "phone",
    }
    assert business_404_content(SimpleNamespace(detail=payload)) == payload


def test_starlette_default_not_found_is_unmatched_route():
    assert business_404_content(SimpleNamespace(detail="Not Found")) is None
    assert business_404_content(SimpleNamespace(detail="Not found")) is None
    assert business_404_content(SimpleNamespace(detail="")) is None
    assert business_404_content(SimpleNamespace()) is None
