"""Bunny delete cron không được giữ transaction DB trong lúc gọi HTTP."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.pending_bunny_delete import PendingBunnyDelete
from app.services import bunny_delete_queue as queue


def _db():
    engine = create_engine("sqlite:///:memory:")
    PendingBunnyDelete.__table__.create(engine)
    return sessionmaker(bind=engine)()


def test_http_delete_runs_outside_db_transaction(monkeypatch):
    db = _db()
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.add(
        PendingBunnyDelete(
            storage_path="products/1.jpg",
            status="pending",
            attempts=0,
            next_attempt_at=past,
        )
    )
    db.commit()

    seen = {}

    def fake_delete(**kwargs):
        seen["in_transaction"] = db.in_transaction()
        seen["path"] = kwargs["remote_path"]
        return True

    monkeypatch.setattr(queue.settings, "IS_POSTGRESQL", False)
    monkeypatch.setattr(queue.settings, "BUNNY_STORAGE_ZONE_NAME", "zone")
    monkeypatch.setattr(queue.settings, "BUNNY_STORAGE_ACCESS_KEY", "key")
    monkeypatch.setattr(queue, "delete_file_from_zone", fake_delete)

    result = queue.process_pending_bunny_deletes(db, limit=10)

    assert seen["in_transaction"] is False
    assert seen["path"] == "products/1.jpg"
    assert result["deleted"] == 1
    assert result["failed"] == 0
    assert db.query(PendingBunnyDelete).count() == 0
    db.close()
