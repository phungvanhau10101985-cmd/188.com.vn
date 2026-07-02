"""Tests for image localization runtime admin prefs."""

import json
from pathlib import Path

import pytest

from app.services import image_localization_runtime_prefs as prefs_mod


@pytest.fixture
def isolated_prefs(tmp_path, monkeypatch):
    monkeypatch.setattr(prefs_mod.settings, "IMAGE_LOCALIZATION_RUNTIME_DIR", str(tmp_path))
    prefs_mod._prefs_cache = None
    yield tmp_path
    prefs_mod._prefs_cache = None


def test_effective_uses_env_when_no_runtime_file(isolated_prefs, monkeypatch):
    monkeypatch.setattr(prefs_mod, "deepseek_off_peak_only_env_default", lambda: False)
    assert prefs_mod.deepseek_off_peak_only_effective() is False


def test_set_and_read_runtime_override(isolated_prefs, monkeypatch):
    monkeypatch.setattr(prefs_mod, "deepseek_off_peak_only_env_default", lambda: False)
    assert prefs_mod.set_deepseek_off_peak_only(True) is True
    assert prefs_mod.deepseek_off_peak_only_effective() is True
    assert prefs_mod.deepseek_off_peak_only_runtime_overridden() is True
    path = isolated_prefs / "admin_prefs.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["deepseek_off_peak_only"] is True

    prefs_mod.set_deepseek_off_peak_only(False)
    assert prefs_mod.deepseek_off_peak_only_effective() is False
