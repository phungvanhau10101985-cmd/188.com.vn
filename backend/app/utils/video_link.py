"""Nhận diện link video SP — khớp logic frontend (video-utils): YouTube hoặc URL .mp4."""
from __future__ import annotations

import re
from typing import Optional

_YT_EMBED = re.compile(r"youtube\.com/embed/([^&?/]+)", re.I)
_YT_NOCOOKIE = re.compile(r"youtube-nocookie\.com/embed/([^&?/]+)", re.I)
_YT_WATCH = re.compile(r"youtube\.com/watch\?v=([^&]+)", re.I)
_YT_SHORT_URL = re.compile(r"youtu\.be/([^&?/]+)", re.I)
_MP4 = re.compile(r"\.mp4(\?|$)", re.I)


def is_playable_product_video_link(raw: Optional[str]) -> bool:
    if raw is None:
        return False
    s = str(raw).strip()
    if not s:
        return False
    if _MP4.search(s):
        return True
    if (
        _YT_EMBED.search(s)
        or _YT_NOCOOKIE.search(s)
        or _YT_WATCH.search(s)
        or _YT_SHORT_URL.search(s)
    ):
        return True
    return False
