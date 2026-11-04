from app.crud.site_embed_code import normalize_zalo_personal_url


def test_phone_with_spaces_becomes_zalo_me():
    assert normalize_zalo_personal_url("0968 659 836") == "https://zalo.me/0968659836"


def test_country_code_becomes_local_phone():
    assert normalize_zalo_personal_url("+84968659836") == "https://zalo.me/0968659836"


def test_existing_zalo_link_is_kept():
    assert (
        normalize_zalo_personal_url("https://zalo.me/1714121106420519241")
        == "https://zalo.me/1714121106420519241"
    )


def test_rejects_text_that_is_not_a_zalo_target():
    assert normalize_zalo_personal_url("hello") is None
    assert normalize_zalo_personal_url("<script>") is None
    assert normalize_zalo_personal_url("") is None
