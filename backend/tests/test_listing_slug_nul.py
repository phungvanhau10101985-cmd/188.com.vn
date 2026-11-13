from app.crud.product import normalize_legacy_source_slug, sanitize_sql_text


def test_sanitize_sql_text_strips_nul_and_controls():
    assert sanitize_sql_text("ao\x00thun\x01nam") == "aothunnam"
    assert sanitize_sql_text("") == ""


def test_normalize_legacy_source_slug_strips_nul_before_query():
    assert normalize_legacy_source_slug("ao-thun\x00nam") == "ao-thunnam"
    assert normalize_legacy_source_slug("\x00") == ""
    assert normalize_legacy_source_slug("index.php/vay-dam-nu") == "vay-dam-nu"
