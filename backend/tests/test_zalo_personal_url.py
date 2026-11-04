from types import SimpleNamespace

from app.crud.site_embed_code import normalize_zalo_personal_url
from app.services.site_embed_templates import collect_expanded_fragments


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


def _row(**kwargs):
    base = dict(platform="zalo", category="personal", content="", hint="", is_active=True, placement="body_close")
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_saved_personal_number_replaces_oa_widget():
    rows = [
        _row(content="https://zalo.me/0968659836"),
        _row(category="chat", content="1714121106420519241"),
    ]
    _head, _open, body_close = collect_expanded_fragments(rows)
    html = "\n".join(body_close)
    assert 'data-zalo-open="personal"' in html
    assert "https://zalo.me/0968659836" in html
    assert "zalo-chat-widget" not in html


def test_oa_mode_keeps_official_widget():
    rows = [
        _row(content="https://zalo.me/0968659836", hint="zalo_open:oa"),
        _row(category="chat", content="1714121106420519241"),
    ]
    _head, _open, body_close = collect_expanded_fragments(rows)
    html = "\n".join(body_close)
    assert "zalo-chat-widget" in html
    assert "0968659836" not in html
