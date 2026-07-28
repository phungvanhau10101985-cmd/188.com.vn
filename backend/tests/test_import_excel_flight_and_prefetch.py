"""Single-flight Excel import + prefetch helpers."""

from unittest.mock import MagicMock

from app.crud.product import _bulk_import_prefetch_products_by_ids


def test_try_acquire_excel_import_flight_blocks_second():
    from app.api.endpoints import import_export as mod

    # Reset in case other tests left the lock held.
    mod._release_excel_import_flight()

    assert mod._try_acquire_excel_import_flight(job_id="job-a", mode="async") is None
    busy = mod._try_acquire_excel_import_flight(job_id="job-b", mode="async")
    assert busy == "job-a"
    mod._release_excel_import_flight()
    assert mod._try_acquire_excel_import_flight(job_id="job-c", mode="sync") is None
    mod._release_excel_import_flight()


def test_bulk_import_prefetch_products_by_ids_chunks():
    db = MagicMock()
    p1 = MagicMock()
    p1.product_id = "A123"
    p2 = MagicMock()
    p2.product_id = "T456"

    calls = {"n": 0}

    def _query_side_effect(*_a, **_k):
        calls["n"] += 1
        q = MagicMock()
        filt = MagicMock()
        # First chunk → p1, second → p2 (chunk_size=1)
        if calls["n"] == 1:
            filt.all.return_value = [p1]
        else:
            filt.all.return_value = [p2]
        q.filter.return_value = filt
        return q

    db.query.side_effect = _query_side_effect
    out = _bulk_import_prefetch_products_by_ids(db, {"A123", "T456"}, chunk_size=1)
    assert set(out.keys()) == {"A123", "T456"}
    assert calls["n"] == 2
