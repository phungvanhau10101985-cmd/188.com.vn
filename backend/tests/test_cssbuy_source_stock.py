"""CSSBuy / Vipomall / PandaMall source-stock: nút giỏ/mua, CF fallback."""
from app.services.import_batch_url_coercion import (
    FETCH_TARGET_CSSBUY,
    FETCH_TARGET_PANDAMALL,
    FETCH_TARGET_VIPOMALL,
    coerce_url_for_excel_batch_import,
)
from app.services.import_cssbuy_client import (
    classify_cssbuy_add_to_cart_cta,
    cssbuy_html_shows_add_to_cart_button,
    cssbuy_html_suggests_security_block,
    cssbuy_item_page_to_item_slug,
    cssbuy_playwright_pdp_url,
    notice_from_stock_zone,
    parse_cssbuy_goods_detail,
    product_zone_looks_loaded,
    visible_text_out_of_stock_notice,
)
from app.services.pandamall_source_stock import pandamall_html_shows_cart_or_buy_cta
from app.services.source_stock_checker import (
    SourceStockCheckResult,
    _link_eligible_for_source_stock_check,
    _merge_all_platforms_blocked_or_error,
    _result_is_conclusive_stock,
    _result_should_fallback_next_platform,
)
from app.services.vipomall_source_stock import (
    resolve_numeric_1688_offer_id_from_source_url,
    vipomall_html_shows_add_to_cart_cta,
)

GD = "https://www.cssbuy.com/shop/goodsDetail?type=1688&id=1006188186694"
ITEM = "https://www.cssbuy.com/item-1688-1006188186694.html"

CSS_BTN = (
    '<div data-v-95356fef="" class="btn pointer ty_button_btn6">'
    '<span data-v-95356fef="" style="margin-left: 5px;"></span>Add to Cart</div>'
)
VIPO_BTN = (
    '<button _ngcontent-fky-c194="" class="button">'
    '<img _ngcontent-fky-c194="" src="assets/images/os-image/cart_detail.svg" alt="" class="ng-star-inserted">'
    '<span _ngcontent-fky-c194="" class="spn-color text-[16px]">Thêm giỏ hàng</span></button>'
)
PANDA_BTNS = (
    '<div class="group-btn">'
    '<button type="button" class="ant-btn ant-btn-default btn-addcart me-2" disabled="" '
    'style="pointer-events: none;"><span>Thêm vào giỏ</span></button>'
    '<button type="button" class="ant-btn ant-btn-default btn-buynow button-s1" disabled="" '
    'style="pointer-events: none;"><span>Mua ngay</span></button></div>'
)


def test_parse_cssbuy_goods_detail_1688():
    assert parse_cssbuy_goods_detail(GD) == ("1688", "1006188186694")


def test_cssbuy_item_slug_from_goods_detail():
    assert cssbuy_item_page_to_item_slug(GD) == "abb-1006188186694"
    assert cssbuy_item_page_to_item_slug(ITEM) == "abb-1006188186694"


def test_coerce_goods_detail_to_item_1688():
    url, err = coerce_url_for_excel_batch_import(GD, FETCH_TARGET_CSSBUY)
    assert err is None
    assert url == ITEM


def test_coerce_goods_detail_vipomall_and_panda():
    vm, vm_err = coerce_url_for_excel_batch_import(GD, FETCH_TARGET_VIPOMALL)
    assert vm_err is None
    assert "1006188186694" in vm
    pd, pd_err = coerce_url_for_excel_batch_import(GD, FETCH_TARGET_PANDAMALL)
    assert pd_err is None
    assert pd == "https://pandamall.vn/1688/detail/1006188186694"


def test_playwright_pdp_url_is_goods_detail():
    assert cssbuy_playwright_pdp_url(GD) == GD
    assert cssbuy_playwright_pdp_url(ITEM) == GD


def test_goods_detail_link_eligible():
    assert _link_eligible_for_source_stock_check(GD) is True
    assert _link_eligible_for_source_stock_check("https://pandamall.vn/1688/detail/1") is True


def test_resolve_1688_offer_from_goods_detail():
    assert resolve_numeric_1688_offer_id_from_source_url(GD) == "1006188186694"


def test_classify_add_to_cart_cta_ignores_disabled():
    assert classify_cssbuy_add_to_cart_cta(found=True, disabled=False) == "in_stock"
    assert classify_cssbuy_add_to_cart_cta(found=True, disabled=True) == "in_stock"
    assert classify_cssbuy_add_to_cart_cta(found=False, disabled=False) == "out_of_stock"


def test_oos_notice_beats_cart_button():
    assert classify_cssbuy_add_to_cart_cta(found=True, out_of_stock_notice="Out of stock") == "out_of_stock"
    assert visible_text_out_of_stock_notice("Price\nOut of stock\nAdd to Cart") == "Out of stock"
    assert visible_text_out_of_stock_notice("该商品已下架") == "下架"
    assert visible_text_out_of_stock_notice("Sản phẩm hết hàng") == "hết hàng"
    assert visible_text_out_of_stock_notice("Sold out") == "Sold out"
    assert (
        visible_text_out_of_stock_notice(
            "Không tìm thấy thông tin sản phẩm, vui lòng thử lại sau. Xin cảm ơn"
        )
        == "Không tìm thấy thông tin sản phẩm"
    )
    disclaimer = (
        "All products available for shopping agent service displayed on CSSBuy "
        "are from third-party shopping platforms. Add to Cart Buy now"
    )
    assert visible_text_out_of_stock_notice(disclaimer) is None
    footer = "Câu hỏi thường gặp Hết hàng Chính sách bảo mật"
    assert notice_from_stock_zone({"zoneText": "Add to Cart\n$12.00", "missingProduct": False}) is None
    assert notice_from_stock_zone({"zoneText": footer, "missingProduct": False}) == "Hết hàng"
    assert (
        notice_from_stock_zone({"zoneText": "Trang chủ", "missingProduct": True})
        == "Không tìm thấy thông tin sản phẩm"
    )
    assert product_zone_looks_loaded({"risksOpen": True, "productImage": True, "title": "Áo khoác bomber nam"}) is False
    assert product_zone_looks_loaded({"risksOpen": False, "productImage": False, "title": "CSSBuy: Taobao Agent"}) is False
    assert product_zone_looks_loaded({"risksOpen": False, "productImage": True, "title": ""}) is True


def test_platform_button_html_snippets():
    assert cssbuy_html_shows_add_to_cart_button(CSS_BTN)
    assert vipomall_html_shows_add_to_cart_cta(VIPO_BTN)
    assert pandamall_html_shows_cart_or_buy_cta(PANDA_BTNS)
    assert not pandamall_html_shows_cart_or_buy_cta(
        '<div class="box-title fm-500">Tìm kiếm &amp; Thêm vào giỏ</div>'
    )
    assert not vipomall_html_shows_add_to_cart_cta("<div>Thêm giỏ hàng</div>")


def test_security_block_html():
    assert cssbuy_html_suggests_security_block(
        "<html>Checking if the site connection is secure</html>",
        title="Just a moment...",
    )
    assert not cssbuy_html_suggests_security_block(
        "<html><script src='https://challenges.cloudflare.com/turnstile/v0/api.js'></script>"
        "<div class='shop_detail'>Add to Cart I accept the risks</div></html>"
    )


def test_fallback_only_when_cloudflare_blocked():
    assert _result_should_fallback_next_platform(SourceStockCheckResult(status="blocked")) is True
    assert _result_should_fallback_next_platform(SourceStockCheckResult(status="error")) is False
    assert _result_should_fallback_next_platform(SourceStockCheckResult(status="out_of_stock")) is False
    assert _result_should_fallback_next_platform(SourceStockCheckResult(status="in_stock")) is False
    assert _result_is_conclusive_stock(SourceStockCheckResult(status="in_stock")) is True


def test_all_platforms_blocked_emails_admin_once_per_window(monkeypatch):
    import app.services.source_stock_block_alert as alert

    alert._last_sent_mono = 0.0
    sent = []

    def _capture(**kwargs):
        sent.append(kwargs)

    class _Now:
        def __init__(self, target, kwargs=None, **_ignored):
            self.target = target
            self.kwargs = kwargs or {}

        def start(self):
            self.target(**self.kwargs)

    monkeypatch.setattr(alert.threading, "Thread", _Now)
    monkeypatch.setattr(alert, "_send", _capture)
    assert alert.maybe_notify_admin_all_platforms_blocked(product_id=1, link="https://detail.1688.com/offer/1.html") is True
    assert alert.maybe_notify_admin_all_platforms_blocked(product_id=2) is False
    assert len(sent) == 1
    assert sent[0]["product_id"] == 1
    alert._last_sent_mono = 0.0


def test_all_platforms_blocked_stops():
    css = SourceStockCheckResult(status="blocked", error="cf css", checked_via="cssbuy")
    vm = SourceStockCheckResult(status="blocked", error="cf vipo", checked_via="vipomall")
    panda = SourceStockCheckResult(status="blocked", error="cf panda", checked_via="pandamall")
    merged = _merge_all_platforms_blocked_or_error(css, vm, panda)
    assert merged.status == "blocked"
    assert "đều bị Cloudflare" in (merged.error or "")


def test_in_progress_stale_only_for_abandoned_checking_or_queued():
    from datetime import datetime, timedelta, timezone

    from app.services.source_stock_checker import source_stock_in_progress_is_stale

    now = datetime(2026, 10, 4, tzinfo=timezone.utc)
    old = now - timedelta(minutes=31)
    fresh = now - timedelta(minutes=2)
    assert source_stock_in_progress_is_stale("checking", old, now=now) is True
    assert source_stock_in_progress_is_stale("queued", None, now=now) is True
    assert source_stock_in_progress_is_stale("checking", fresh, now=now) is False
    assert source_stock_in_progress_is_stale("in_stock", old, now=now) is False
    assert source_stock_in_progress_is_stale("out_of_stock", None, now=now) is False


def test_bulk_clear_oos_empty_ids_is_noop():
    from app.services.admin_source_stock_batch import admin_clear_false_source_oos_flags_bulk

    out = admin_clear_false_source_oos_flags_bulk(None, db_ids=[])  # type: ignore[arg-type]
    assert out["ok"] is True
    assert out["cleared"] == 0
