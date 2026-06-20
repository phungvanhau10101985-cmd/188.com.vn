"""Unit tests — email thông báo phản hồi câu hỏi / đánh giá."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.product_reply_notify import (
    _is_real_customer_review,
    _is_real_shop_customer_question,
    _resolve_recipient_email,
    _valid_email,
    build_reply_email_subject,
    collect_new_question_replies,
    collect_new_review_reply,
)


def _question(**kwargs):
    base = dict(
        reply_admin_name="",
        reply_admin_content="",
        reply_user_one_name="",
        reply_user_one_content="",
        reply_user_two_name="",
        reply_user_two_content="",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _review(**kwargs):
    base = dict(reply_name="", reply_content="")
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_collect_new_question_replies_admin_only():
    before = _question(reply_admin_content="")
    updates = {"reply_admin_name": "188.COM.VN", "reply_admin_content": "Shop trả lời"}
    out = collect_new_question_replies(before, updates)
    assert out == [("admin", "188.COM.VN", "Shop trả lời")]


def test_collect_new_question_replies_waits_for_name():
    before = _question(reply_admin_name="", reply_admin_content="")
    assert collect_new_question_replies(before, {"reply_admin_content": "Chỉ có nội dung"}) == []
    assert collect_new_question_replies(
        before,
        {"reply_admin_name": "188.COM.VN", "reply_admin_content": "Chỉ có nội dung"},
    ) == [("admin", "188.COM.VN", "Chỉ có nội dung")]


def test_collect_new_question_replies_name_after_content():
    before = _question(reply_admin_name="", reply_admin_content="Nội dung sẵn")
    assert collect_new_question_replies(before, {"reply_admin_content": "Nội dung sẵn"}) == []
    assert collect_new_question_replies(
        before,
        {"reply_admin_name": "188.COM.VN"},
    ) == [("admin", "188.COM.VN", "Nội dung sẵn")]


def test_collect_new_question_replies_skips_unchanged():
    before = _question(reply_admin_content="Giữ nguyên")
    updates = {"reply_admin_content": "Giữ nguyên", "useful": 3}
    assert collect_new_question_replies(before, updates) == []


def test_collect_new_question_replies_multiple_slots():
    before = _question(
        reply_admin_content="Cũ",
        reply_user_one_content="",
    )
    updates = {
        "reply_user_one_name": "An",
        "reply_user_one_content": "Mình đã mua ok",
    }
    out = collect_new_question_replies(before, updates)
    assert out == [("user_one", "An", "Mình đã mua ok")]


def test_collect_new_review_reply():
    before = _review(reply_content="")
    out = collect_new_review_reply(
        before,
        {"reply_name": "188.COM.VN", "reply_content": "Cảm ơn bạn"},
    )
    assert out == ("188.COM.VN", "Cảm ơn bạn")


def test_collect_new_review_reply_waits_for_name():
    before = _review(reply_name="", reply_content="")
    assert collect_new_review_reply(before, {"reply_content": "Chỉ nội dung"}) is None
    assert collect_new_review_reply(
        before,
        {"reply_name": "188.COM.VN", "reply_content": "Chỉ nội dung"},
    ) == ("188.COM.VN", "Chỉ nội dung")


def test_collect_new_review_reply_skips_empty():
    before = _review(reply_content="")
    assert collect_new_review_reply(before, {"reply_content": "   "}) is None


def test_valid_email():
    assert _valid_email("a@b.com") == "a@b.com"
    assert _valid_email("bad") is None
    assert _valid_email("") is None


def test_is_real_shop_customer_question():
    real = SimpleNamespace(is_imported=False, product_id=10, group=0)
    imported = SimpleNamespace(is_imported=True, product_id=10, group=0)
    group_only = SimpleNamespace(is_imported=False, product_id=None, group=3)
    assert _is_real_shop_customer_question(real) is True
    assert _is_real_shop_customer_question(imported) is False
    assert _is_real_shop_customer_question(group_only) is False


def test_is_real_customer_review():
    assert _is_real_customer_review(SimpleNamespace(is_imported=False)) is True
    assert _is_real_customer_review(SimpleNamespace(is_imported=True)) is False


def test_resolve_recipient_email_prefers_profile():
    db = MagicMock()
    user = SimpleNamespace(id=5, email="profile@example.com")
    assert _resolve_recipient_email(db, user) == "profile@example.com"
    db.query.assert_not_called()


def test_product_thumbnail_url_from_main_image():
    from app.services.product_reply_notify import _product_thumbnail_url

    product = SimpleNamespace(main_image="/uploads/sp.jpg", images=[])
    url = _product_thumbnail_url(product)
    assert url.endswith("/uploads/sp.jpg")


def test_product_thumbnail_url_from_gallery():
    from app.services.product_reply_notify import _product_thumbnail_url

    product = SimpleNamespace(main_image="", images=["https://cdn.example.com/a.jpg"])
    assert _product_thumbnail_url(product) == "https://cdn.example.com/a.jpg"


def test_build_reply_email_subject_unique_per_reply():
    s1 = build_reply_email_subject(
        kind="question",
        replier_name="188.COM.VN",
        product_name="Sandal da nam",
        reply_content="8 đến 12 ngày anh nhé",
        stamp="20/06 12:00:01.000",
    )
    s2 = build_reply_email_subject(
        kind="question",
        replier_name="188.COM.VN",
        product_name="Sandal da nam",
        reply_content="10 ngày nhận hàng",
        stamp="20/06 12:12:05.000",
    )
    assert s1 != s2
    assert "188.COM.VN" in s1
    assert "8 đến 12 ngày" in s1
    assert s1.startswith("20/06 12:00:01.000")


def test_build_reply_email_subject_review():
    subject = build_reply_email_subject(
        kind="review",
        replier_name="188.COM.VN",
        product_name="Áo thun",
        reply_content="Cảm ơn bạn",
        stamp="20/06 12:15:00.000",
    )
    assert "Phản hồi đánh giá" in subject
    assert "Cảm ơn bạn" in subject


def test_resolve_recipient_email_falls_back_to_order():
    db = MagicMock()
    user = SimpleNamespace(id=5, email=None)
    order = SimpleNamespace(customer_email="order@example.com", created_at=1)
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = [order]
    db.query.return_value = query
    assert _resolve_recipient_email(db, user, product_id=99) == "order@example.com"
