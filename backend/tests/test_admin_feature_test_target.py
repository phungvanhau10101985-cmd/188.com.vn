from app.services.admin_feature_test_target import matches_feature_test_target


def test_explicit_test_email_excludes_linked_admin_account():
    assert (
        matches_feature_test_target(
            configured_test_email="customer@example.com",
            linked_user_id=10,
            current_user_email="admin@example.com",
            current_user_id=10,
        )
        is False
    )


def test_explicit_test_email_only_matches_that_customer():
    assert (
        matches_feature_test_target(
            configured_test_email="Customer@Example.com",
            linked_user_id=10,
            current_user_email="customer@example.com",
            current_user_id=20,
        )
        is True
    )


def test_linked_admin_account_is_fallback_when_test_email_empty():
    assert (
        matches_feature_test_target(
            configured_test_email=None,
            linked_user_id=10,
            current_user_email="admin@example.com",
            current_user_id=10,
        )
        is True
    )
