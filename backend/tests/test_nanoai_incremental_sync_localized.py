"""Cổng đồng bộ NanoAI chỉ upsert sản phẩm đã bản địa hóa."""
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.endpoints.products import _read_products_incremental_sync
from app.crud.product import get_products_for_incremental_sync
from app.db.base import Base
from app.models.product import Product
from app.models.product_deletion import ProductDeletion


def test_incremental_sync_upserts_only_localized_and_drops_the_rest():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    since = datetime(2026, 8, 1, tzinfo=timezone.utc)
    recent = datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc)
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def row(product_id: str, status: str | None, stamp: datetime) -> Product:
        return Product(
            product_id=product_id,
            name=product_id,
            image_localization_status=status,
            created_at=stamp,
            updated_at=stamp,
            is_active=True,
        )

    db.add_all(
        [
            row("LOC", "localized", recent),
            row("PEND", "pending", recent),
            row("FAIL", "failed", recent),
            row("SKIP", "skipped", recent),
            row("NONE", None, recent),
            row("PROC", "processing", recent),
            row("OLD", "localized", old),
            row("OLD_PEND", "pending", old),
        ]
    )
    db.add(ProductDeletion(product_id="GONE", deleted_at=recent))
    db.commit()

    total, items = get_products_for_incremental_sync(
        db, updated_since=since, page=1, limit=50
    )
    kinds: dict[str, set[str]] = {}
    for kind, item in items:
        kinds.setdefault(kind, set()).add(item.product_id)

    assert total == 6
    assert kinds["product"] == {"LOC"}
    assert kinds["excluded"] == {"PEND", "FAIL", "SKIP", "NONE"}
    assert kinds["deleted"] == {"GONE"}
    assert "PROC" not in {pid for group in kinds.values() for pid in group}
    assert "OLD" not in {pid for group in kinds.values() for pid in group}
    assert "OLD_PEND" not in {pid for group in kinds.values() for pid in group}

    payload = _read_products_incremental_sync(db, updated_since=since, page=1, limit=50)
    by_id = {row["id"]: row for row in payload["data"]}
    assert by_id["LOC"]["is_deleted"] is False
    assert by_id["LOC"]["product_id"] == "LOC"
    assert by_id["LOC"]["image_localization_status"] == "localized"
    for pid in ("PEND", "FAIL", "SKIP", "NONE", "GONE"):
        assert by_id[pid]["is_deleted"] is True
        assert "name" not in by_id[pid]
    assert "PROC" not in by_id
    assert payload["pagination"]["total_records"] == 6
    db.close()
