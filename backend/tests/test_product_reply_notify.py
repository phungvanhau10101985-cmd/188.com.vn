"""Unit tests — email thông báo phản hồi câu hỏi / đánh giá."""

from types import SimpleNamespace

from app.services.product_reply_notify import (
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
    assert out == [("188.COM.VN", "Shop trả lời")]


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
    assert out == [("An", "Mình đã mua ok")]


def test_collect_new_review_reply():
    before = _review(reply_content="")
    out = collect_new_review_reply(
        before,
        {"reply_name": "188.COM.VN", "reply_content": "Cảm ơn bạn"},
    )
    assert out == ("188.COM.VN", "Cảm ơn bạn")


def test_collect_new_review_reply_skips_empty():
    before = _review(reply_content="")
    assert collect_new_review_reply(before, {"reply_content": "   "}) is None
