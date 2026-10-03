from types import SimpleNamespace

from app.services.notification_links import (
    attach_action_urls,
    clean_action_url,
    destination_for,
    order_action_path,
)


def _notif(**kwargs):
    defaults = {
        "action_url": None,
        "title": "",
        "content": "",
        "type": "general",
        "dedupe_key": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_cart_gift_opens_cart():
    path, code = destination_for(
        _notif(
            title="Bạn nhận quà: Quà nhắc giỏ hàng",
            content="Bạn còn sản phẩm trong giỏ — mã CARTSAVE188. Xem tại mục Khuyến mãi.",
            type="promotion",
        )
    )
    assert path == "/cart"
    assert code is None


def test_deposit_needs_order_lookup_then_order_page():
    notif = _notif(
        title="Đã nhận đặt cọc",
        content="Đơn DH646: xác nhận thanh toán cọc 100.000 VND. Đã đặt cọc.",
        type="order",
    )
    path, code = destination_for(notif)
    assert path is None
    assert code == "DH646"

    class _Db:
        def query(self, *_args):
            return self

        def filter(self, *_args):
            return self

        def all(self):
            return [SimpleNamespace(id=12, order_code="DH646")]

    attach_action_urls(_Db(), [notif])
    assert notif.action_url == "/account/orders/12"
    assert order_action_path(notif.title, notif.content, 12) == "/account/orders/12"


def test_order_events_open_the_matching_page():
    assert destination_for(_notif(dedupe_key="order:9:delivered"))[0] == "/account/orders/9/review"
    assert destination_for(_notif(dedupe_key="order:9:phase_in_transit"))[0] == "/account/orders/9/tracking"
    assert destination_for(_notif(dedupe_key="order:9:shipper_confirmed"))[0] == "/account/orders/9"


def test_other_gifts_and_affiliate():
    welcome = _notif(title="Bạn nhận quà: Quà chào bạn mới", content="Mã WELCOME188.", type="promotion")
    assert destination_for(welcome)[0] == "/account/khuyen-mai"
    affiliate = _notif(title="Hoa hồng đã có thể rút", content="Đơn DH1 đã giao.", type="affiliate")
    assert destination_for(affiliate)[0] == "/vi-dien-tu"


def test_stored_path_wins_and_external_links_are_dropped():
    assert destination_for(_notif(action_url="/cart", title="Đơn DH1"))[0] == "/cart"
    assert clean_action_url("https://evil.example/cart") is None
    assert clean_action_url("/account/notifications") is None
    assert clean_action_url("//evil.example") is None
