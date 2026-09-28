"""Link hộp thư NanoAI (inbox_link) không được chèn ra HTML storefront."""

from app.models.site_embed_code import SiteEmbedCode
from app.services.site_embed_templates import collect_expanded_fragments


def test_nanoai_inbox_link_is_not_injected_into_public_html():
    row = SiteEmbedCode(
        platform="nanoai",
        category="inbox_link",
        title="NanoAI — Link hộp thư shop",
        placement="body_close",
        content="https://nanoai.vn/dashboard/messaging/inbox?partner=abc",
        is_active=True,
    )
    head, body_open, body_close = collect_expanded_fragments([row])
    assert head == []
    assert body_open == []
    assert body_close == []
