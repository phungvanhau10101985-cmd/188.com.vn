"""Unit tests for locked studio shoot context in prompts."""

from app.services.manual_product_create_service import (
    _ensure_studio_shoot_context_in_prompt,
    _shot_style_session_label,
    _studio_commercial_look_from_state,
)


def _state(*, shot_style="outdoor", model_presence="model"):
    return {
        "payload": {
            "product_type": "apparel",
            "model_presence": model_presence,
            "model_gender": "female",
            "model_age_group": "adult",
            "shot_style": shot_style,
        },
        "studio": {
            "plan": {
                "model_presence": model_presence,
                "model_gender": "female",
                "model_age_group": "adult",
                "shot_style": shot_style,
            }
        },
    }


def test_shot_style_labels():
    assert "ngoài trời" in _shot_style_session_label("outdoor")
    assert "trong nhà" in _shot_style_session_label("lifestyle")


def test_commercial_look_reflects_outdoor():
    look = _studio_commercial_look_from_state(_state(shot_style="outdoor"))
    assert "Outdoor" in look or "outdoor" in look.lower()


def test_ensure_shoot_context_appended_once():
    look = "Outdoor commercial product photography"
    out = _ensure_studio_shoot_context_in_prompt("Create gallery photo.", look)
    assert "LOCKED SHOOT SETTINGS" in out
    again = _ensure_studio_shoot_context_in_prompt(out, look)
    assert again.count("LOCKED SHOOT SETTINGS") == 1
