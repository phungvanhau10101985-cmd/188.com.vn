"""replace_studio_images cho phép bỏ qua ảnh chi tiết (urls rỗng)."""

from app.services import manual_product_create_service as svc


def test_replace_studio_images_allows_empty_detail(monkeypatch):
    job_id = "job-skip-detail"
    state = {
        "status": "awaiting_input",
        "payload": {"mode": "ai"},
        "studio": {
            "ref_pool": [{"url": "https://cdn.example/a.jpg", "kind": "gallery"}],
            "colors": [],
            "images": ["https://cdn.example/a.jpg", "https://cdn.example/b.jpg"],
            "gallery": ["https://cdn.example/old-detail.jpg"],
            "material_image": "https://cdn.example/mat.jpg",
        },
    }
    saved = {}

    def _load(_job_id):
        assert _job_id == job_id
        return dict(state)

    def _persist(_job_id, new_state):
        saved["state"] = new_state

    monkeypatch.setattr(svc, "load_job", _load)
    monkeypatch.setattr(svc, "persist_job", _persist)
    monkeypatch.setattr(svc, "_refresh_studio_hints", lambda _s, _st: None)

    out = svc.replace_studio_images(job_id, kind="detail", urls=[])

    assert out["studio"]["gallery"] == []
    assert "bỏ qua" in (out.get("message") or "").lower()
    assert saved["state"]["studio"]["gallery"] == []
