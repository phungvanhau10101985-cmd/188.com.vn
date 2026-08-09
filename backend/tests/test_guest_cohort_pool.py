"""Pool cohort cho khách chưa đăng nhập theo bucket giới tính (+ năm sinh tùy chọn)."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.crud.guest_cohort_pool import (
    COHORT_VIEW_POOL_CACHE_TTL_HOURS,
    _cache_is_stale,
    guest_cohort_bucket_key,
    sample_guest_cohort_products_from_pool,
)


def test_bucket_key_with_birth_year():
    assert guest_cohort_bucket_key("Female", 1998) == "female:1998"


def test_bucket_key_without_birth_year():
    assert guest_cohort_bucket_key("male", None) == "male:_any"


def test_bucket_key_normalizes_case_and_whitespace():
    assert guest_cohort_bucket_key("  MALE  ", None) == "male:_any"


def test_cache_not_stale_when_recent():
    assert _cache_is_stale(datetime.now(timezone.utc)) is False


def test_cache_stale_when_old():
    old = datetime.now(timezone.utc) - timedelta(hours=COHORT_VIEW_POOL_CACHE_TTL_HOURS + 1)
    assert _cache_is_stale(old) is True


def test_cache_stale_when_none():
    assert _cache_is_stale(None) is True


def test_sample_guest_cohort_rejects_invalid_gender_without_touching_db():
    db = MagicMock()
    products, mode = sample_guest_cohort_products_from_pool(
        db, session_id="s1", gender="other", birth_year=None, limit=10
    )
    assert products == []
    assert mode == "profile_incomplete"
    db.query.assert_not_called()


def test_sample_guest_cohort_rejects_empty_gender_without_touching_db():
    db = MagicMock()
    products, mode = sample_guest_cohort_products_from_pool(
        db, session_id="s1", gender="", birth_year=None, limit=10
    )
    assert products == []
    assert mode == "profile_incomplete"
    db.query.assert_not_called()
