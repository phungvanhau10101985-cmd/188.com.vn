from __future__ import annotations

from typing import Optional


def matches_feature_test_target(
    *,
    configured_test_email: Optional[str],
    linked_user_id: Optional[int],
    current_user_email: Optional[str],
    current_user_id: Optional[int],
) -> bool:
    """Email test được nhập rõ ràng luôn ưu tiên; linked user chỉ là fallback."""
    target_email = (configured_test_email or "").strip().lower()
    user_email = (current_user_email or "").strip().lower()
    if target_email:
        return bool(user_email and user_email == target_email)
    return bool(
        linked_user_id
        and current_user_id
        and int(linked_user_id) == int(current_user_id)
    )
