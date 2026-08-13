"""Cấp / thu hồi key tra cứu vận chuyển trên file JSON."""
from pathlib import Path

import pytest

from app.services import shipping_lookup_keys as keys_svc


@pytest.fixture
def keys_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "shipping-lookup-keys.json"
    monkeypatch.setattr(keys_svc, "keys_file", lambda: path)
    return path


def test_create_list_reveal_revoke(keys_path: Path):
    created = keys_svc.create_key("NanoAI")
    assert created["label"] == "NanoAI"
    assert len(created["token"]) >= 32
    assert created["last4"] == created["token"][-4:]
    assert keys_path.is_file()

    listed = keys_svc.list_for_admin()
    assert len(listed["keys"]) == 1
    assert listed["keys"][0]["id"] == created["id"]
    assert "token" not in listed["keys"][0]
    assert listed["keys"][0]["last4"] == created["last4"]

    revealed = keys_svc.get_key_token(created["id"])
    assert revealed["token"] == created["token"]

    keys_svc.revoke_key(created["id"])
    assert keys_svc.list_for_admin()["keys"] == []
    assert keys_svc.issued_tokens() == []


def test_create_requires_label(keys_path: Path):
    with pytest.raises(ValueError, match="Nhập tên"):
        keys_svc.create_key("  ")


def test_paste_existing_token_and_reject_duplicate(keys_path: Path):
    token = "a" * 32
    first = keys_svc.create_key("Bot A", token=token)
    assert first["token"] == token
    with pytest.raises(ValueError, match="đã có"):
        keys_svc.create_key("Bot B", token=token)


def test_paste_token_too_short(keys_path: Path):
    with pytest.raises(ValueError, match="16"):
        keys_svc.create_key("Ngắn", token="abc")


def test_revoke_missing_raises(keys_path: Path):
    with pytest.raises(KeyError):
        keys_svc.revoke_key("missing-id")
