"""Chỉ số tương tác mô phỏng khi import SP (theo quy tắc Excel nghiệp vụ).

- likes ∈ [96, 138]
- question_total = likes - RANDBETWEEN(5, 15)
- purchases = question_total - RANDBETWEEN(5, 12)
- rating_total (lượt đánh giá) = purchases - RANDBETWEEN(5, 15)
- rating_point (rating_score / điểm sao): ngẫu nhiên từ 4.80 đến 5.00 (bước 0.01)

Dùng secrets để phân bố đều; nếu trừ âm thì kẹp 0.
"""
from __future__ import annotations

import secrets
from typing import Any, Dict


def _rand_between(lo: int, hi: int) -> int:
    return secrets.randbelow(hi - lo + 1) + lo


def synthetic_engagement_counts() -> Dict[str, Any]:
    likes = _rand_between(96, 138)
    question_total = max(0, likes - _rand_between(5, 15))
    purchases = max(0, question_total - _rand_between(5, 12))
    rating_total = max(0, purchases - _rand_between(5, 15))
    # Trăm phần: 480..500 → 4.80 … 5.00
    cents = secrets.randbelow(500 - 480 + 1) + 480
    rating_point = round(cents / 100.0, 2)
    return {
        "likes": likes,
        "question_total": question_total,
        "purchases": purchases,
        "rating_total": rating_total,
        "rating_point": rating_point,
    }
