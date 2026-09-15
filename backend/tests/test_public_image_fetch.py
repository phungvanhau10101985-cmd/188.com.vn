"""Tải ảnh public cho dán link tìm theo ảnh."""

from app.services.public_image_fetch import (
    PublicImageFetchError,
    assert_public_http_url,
    sniff_image_mime,
)


def test_assert_public_http_url_rejects_localhost():
    try:
        assert_public_http_url("http://127.0.0.1/secret.png")
        assert False, "expected block"
    except PublicImageFetchError as exc:
        assert "nội bộ" in str(exc)


def test_assert_public_http_url_rejects_file_scheme():
    try:
        assert_public_http_url("file:///etc/passwd")
        assert False, "expected block"
    except PublicImageFetchError as exc:
        assert "http" in str(exc).lower()


def test_sniff_image_mime_jpeg_png_webp():
    assert sniff_image_mime(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    png = b"\x89PNG\r\n\x1a\n" + b"xxxx"
    assert sniff_image_mime(png) == "image/png"
    webp = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"xxxx"
    assert sniff_image_mime(webp) == "image/webp"
    assert sniff_image_mime(b"<html>not image</html>") is None
    assert sniff_image_mime(b"<svg></svg>", "image/svg+xml") is None
