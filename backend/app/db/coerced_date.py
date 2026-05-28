from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.types import Date as SADate, TypeDecorator


class CoercedDate(TypeDecorator):
    """DATE cột DB — chấp nhận str khi migration sync cột TEXT/VARCHAR."""

    impl = SADate
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            return date.fromisoformat(raw[:10])
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                return None
        return value
