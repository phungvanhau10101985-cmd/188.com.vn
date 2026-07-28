from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.linked_admin_staff import display_email_for_admin


def _query_chain(db, mapping):
    """mapping: model class -> filter results dict or list for .first()"""

    def query(model):
        m = MagicMock()

        def filter(*args, **kwargs):
            f = MagicMock()
            key = model
            rows = mapping.get(key, [])
            if isinstance(rows, dict):
                f.first.side_effect = lambda: rows.get("first")
            else:
                f.first.side_effect = lambda: rows[0] if rows else None
            f.all.side_effect = lambda: rows if isinstance(rows, list) else []
            return f

        m.filter.side_effect = filter
        return m

    db.query.side_effect = query


def test_display_email_for_admin_prefers_linked_user():
    admin = SimpleNamespace(linked_user_id=7, email="linked-admin-2@188.com.vn")
    user = SimpleNamespace(email="phungvanhau10101985@gmail.com")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    assert display_email_for_admin(db, admin) == "phungvanhau10101985@gmail.com"
