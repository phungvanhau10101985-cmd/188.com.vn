from app.crud.product import normalize_search_query, _normalize_search_key
from app.utils.vietnamese import strip_search_chat_filler


def test_vay_hoa_nhi_co_khong_ban_keeps_product_words():
    raw = "Váy hoa nhí có không bạn"
    assert strip_search_chat_filler(raw) == "váy hoa nhí"
    assert normalize_search_query(raw) == "Váy hoa nhí"
    assert _normalize_search_key(raw) == "váy hoa nhí"
    words = [w.strip() for w in normalize_search_query(raw).split() if w.strip()]
    assert [w.lower() for w in words] == ["váy", "hoa", "nhí"]


def test_ao_khong_tay_keeps_khong():
    assert normalize_search_query("áo không tay") == "Áo không tay"
    assert "không" in normalize_search_query("áo không tay").lower()


def test_vay_hoa_nhi_unchanged():
    assert normalize_search_query("váy hoa nhí") == "Váy hoa nhí"
