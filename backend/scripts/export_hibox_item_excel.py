"""
Xuất một trang sản phẩm hi-box (Nuxt SPA) ra Excel một dòng.

Trang ví dụ: https://hibox.mn/v/abb-922386436529 (1688) hoặc …/v/797317200783 (Taobao).

  cd backend && set PYTHONPATH=. && python scripts/export_hibox_item_excel.py [url]

  • Cuộn tới và bấm «Барааны үзүүлэлт» (details/summary) để mở bảng thông tin sản phẩm; cột specs_text, specs_images_json.
  • Ảnh gallery: swiper gắn chỉ báo «1 / N»; slideTo/slideNext gom đủ slide; có cột gallery_swiper_slide_count (N) và gallery_images_json (URL unique, gộp variant _50/_570 cùng O1CN).
  • Ảnh khác: description_images_json, other_images_json (og_image riêng).
  • Chặn request Jivo chat (hay che nút); bấm nút «САГСЛАХ» / fallback «ШУУД АВАХ» (force) để mở sheet chọn ӨНГӨ / ХЭМЖЭЕ (màu / cỡ).
  • Ảnh chọn màu (thumbnail dưới nhãn «ӨНГӨ» trong sheet cố định): color_variant_images_json, color_variant_labels_json (cùng độ dài thứ tự), color_variant_image_count.
  • Cột colors_json, sizes_json, variant_color_size_json: sheet kiểu «Мөнгө###34» hoặc DOM modal (title swatch + hàng flex-wrap cỡ áo).
  • Modal chỉ 1 màu (flex-row gap-2 flex-wrap một chip + ảnh `justify-between items-start gap-4 p-6`…): lấy tên trong `div.p-2` của chip, ảnh màu = img hero hàng đó (//img.alicdn.com…).
  • video_url: MP4 Taobao (cloud.video.taobao.com) từ <video>/<source>, og:video hoặc HTML trang.

Cần Playwright JS render (SPA); requests chỉ được shell HTML khô.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
try:
    from app.services.alicdn_urls import truncate_alicdn_url_to_first_jpg
except ImportError:

    def truncate_alicdn_url_to_first_jpg(url: str) -> str:
        u = (url or "").strip()
        if not u or "alicdn" not in u.lower():
            return u
        m = re.search(r"\.jpg", u, flags=re.I)
        return u[: m.end()] if m else u


def _hibox_scheme_and_trunc(u: str) -> str:
    s = (u or "").strip()
    if not s:
        return ""
    if s.startswith("//"):
        s = f"https:{s}"
    if s.startswith("http://"):
        s = "https://" + s[len("http://") :]
    return truncate_alicdn_url_to_first_jpg(s)



def _extract_primary_price(nums: List[str]) -> str:
    """Ưu tiên giá trong vùng hợp lý catalogue (sau Khod: có 78,900)."""
    for n in nums:
        s = str(n).replace(",", "")
        if s.isdigit() and 40000 <= int(s) <= 500000:
            return n
    return nums[0] if nums else ""


def parse_hibox_variant_block(text: str) -> tuple[List[str], List[str], List[Dict[str, str]]]:
    """Từ nội dung sheet cố định: «Мөнгө###34», «Цагаан###39», ..."""
    pairs: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for m in re.finditer(r"([^\n#]+?)###(\d{2})", text):
        col, sz = m.group(1).strip(), m.group(2)
        if len(col) > 48 or len(col) < 1:
            continue
        if "," in col:
            continue
        if col.replace(" ", "").isdigit():
            continue
        if not sz.isdigit() or not (30 <= int(sz) <= 50):
            continue
        key = (col, sz)
        if key in seen:
            continue
        seen.add(key)
        pairs.append({"color": col, "size": sz})
    color_order: List[str] = []
    seen_c: set[str] = set()
    for p in pairs:
        c = p["color"]
        if c not in seen_c:
            seen_c.add(c)
            color_order.append(c)
    colors = color_order
    sizes = sorted({p["size"] for p in pairs}, key=lambda x: int(x))
    return colors, sizes, pairs


# Modal Hibox một màu kiểu «Зургийн өнгө» (màu như ảnh) — chuẩn hoá sang tiếng Việt cho Variant / Excel.
_HIBOX_PICTURE_COLOR_LABEL_RE = re.compile(
    r"picture\s*color|图\s*片\s*色|图色|如图所示|按图片|同色|as\s+shown",
    re.IGNORECASE,
)


def _hibox_variant_sheet_is_picture_color_mode(text: str) -> bool:
    if not (text or "").strip():
        return False
    t = text
    if "Зургийн" in t and "өнгө" in t:
        return True
    return bool(_HIBOX_PICTURE_COLOR_LABEL_RE.search(t))


def _hibox_normalize_color_label_for_catalog(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return s
    if "Зургийн" in s and "өнгө" in s:
        return "Màu như ảnh"
    if _HIBOX_PICTURE_COLOR_LABEL_RE.search(s):
        return "Màu như ảnh"
    return s


def _dedupe_urls(urls: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for u in urls:
        if not u or not isinstance(u, str):
            continue
        k = u.split("?")[0]
        if k in seen:
            continue
        seen.add(k)
        out.append(u)
    return out


def _dedupe_urls_lockstep(urls: List[str], labels: List[str]) -> tuple[List[str], List[str]]:
    """Giữ cặp url–label khi bỏ URL trùng path (thumbnail lặp)."""
    seen: set[str] = set()
    ou: List[str] = []
    ol: List[str] = []
    for i, u in enumerate(urls):
        if not u or not isinstance(u, str):
            continue
        k = u.split("?")[0]
        if k in seen:
            continue
        seen.add(k)
        ou.append(u)
        lab = str(labels[i]).strip() if i < len(labels) and labels[i] is not None else ""
        ol.append(lab)
    return ou, ol


def _hibox_alicdn_image_key(url: str) -> str:
    """Gom các URL trùng ảnh (khác đuôi _50x/_570x/)."""
    if not url:
        return ""
    base = url.split("?")[0]
    m = re.search(r"(O1CN[0-9A-Za-z]+)", base)
    if m:
        return m.group(1)
    return base


def _collapse_gallery_resolution_variants(urls: List[str]) -> List[str]:
    """Giữ một URL cho mỗi ảnh nguồn, ưu tiên phiên bản độ phân giải lớn hơn."""

    def score(url: str) -> tuple[int, int]:
        m = re.search(r"_(\d+)x(\d+)", url)
        if not m:
            return (0, 0)
        return (int(m.group(1)), int(m.group(2)))

    buckets: Dict[str, List[str]] = {}
    order_keys: List[str] = []
    for u in urls:
        k = _hibox_alicdn_image_key(u)
        if k not in buckets:
            order_keys.append(k)
            buckets[k] = []
        buckets[k].append(u)
    return [max(buckets[k], key=score) for k in order_keys]


# Quét swiper sản phẩm (slide chờ lazy-load chỉ có data-src hoặc phải next mới vào viewport).
_GALLERY_ESTIMATE_STEPS_JS = r"""() => {
  const t = document.body.innerText || "";
  const rx = /\b(\d{1,2})\s*\/\s*(\d{1,2})\b/g;
  let hint = 0;
  let m;
  while ((m = rx.exec(t)) !== null) {
    const a = parseInt(m[1], 10),
      b = parseInt(m[2], 10);
    if (b <= 48 && b >= 1 && a <= b && b > hint) hint = b;
  }
  return hint > 0 ? Math.min(hint + 10, 36) : 16;
}"""

_GALLERY_COLLECT_JS = r"""() => {
  const mainEl = document.querySelector("main") || document.body;
  const frac = mainEl.querySelector(
    ".swiper-pagination-fraction, [class*='gallery-fraction']",
  );
  let swRoot = frac?.closest(".swiper") || null;
  if (!swRoot) {
    let best = null,
      scoreBest = -1;
    for (const el of mainEl.querySelectorAll(".swiper")) {
      if (/(thumb|thumbnail)/i.test(String(el.className || ""))) continue;
      const imgs = [...el.querySelectorAll("img")];
      const big = imgs.filter(
        (im) =>
          (im.naturalWidth || im.width || 0) >= 350 ||
          /_790x|\d{3}x10000|_570x/i.test(
            `${im.currentSrc || ""}${im.src || ""}`,
          ),
      ).length;
      const s = big * 30 + imgs.length;
      if (s > scoreBest) {
        scoreBest = s;
        best = el;
      }
    }
    swRoot = best;
  }
  if (!swRoot) return [];

  const out = [];
  const seen = new Set();
  const push = (u) => {
    const s = (u || "").trim();
    if (!s.startsWith("http")) return;
    const k = s.split("?")[0];
    if (seen.has(k)) return;
    seen.add(k);
    out.push(s);
  };
  const grabImg = (img) => {
    push(img.currentSrc || img.src);
    push(img.getAttribute("data-src"));
    push(img.getAttribute("data-original"));
    push(img.getAttribute("data-lazy-src"));
    push(img.getAttribute("data-zoom"));
    const ss = img.getAttribute("srcset");
    if (ss) ss.split(",").forEach((p) => push(p.trim().split(/\s+/)[0]));
  };

  swRoot
    .querySelectorAll(".swiper-slide img, [class*='swiper-slide'] img")
    .forEach(grabImg);
  swRoot
    .querySelectorAll(
      ".swiper-slide picture source, [class*='swiper-slide'] picture source",
    )
    .forEach((s) => {
      const ss = s.getAttribute("srcset");
      if (ss) ss.split(",").forEach((p) => push(p.trim().split(/\s+/)[0]));
      push(s.getAttribute("src"));
    });
  swRoot
    .querySelectorAll(".swiper-slide .slide-item, [class*='slide-item']")
    .forEach((sl) => {
      sl.querySelectorAll("img").forEach(grabImg);
    });
  swRoot.querySelectorAll(".swiper-slide, [class*='swiper-slide']").forEach((sl) => {
      const bg = getComputedStyle(sl).backgroundImage;
      const bm =
        bg && /\surl\s*\(\s*["']?([^"'()]+)["']?\s*\)/i.exec(bg);
      if (bm) push(bm[1].trim());
    });
  return out;
}"""

_GALLERY_COLLECT_FOR_INDEX_JS = r"""([i]) => {
  const mainEl = document.querySelector("main") || document.body;
  const frac = mainEl.querySelector(
    ".swiper-pagination-fraction, [class*='gallery-fraction']",
  );
  let swRoot = frac?.closest(".swiper") || null;
  if (!swRoot) {
    let best = null,
      scoreBest = -1;
    for (const el of mainEl.querySelectorAll(".swiper")) {
      if (/(thumb|thumbnail)/i.test(String(el.className || ""))) continue;
      const imgs = [...el.querySelectorAll("img")];
      const big = imgs.filter(
        (im) =>
          (im.naturalWidth || im.width || 0) >= 350 ||
          /_790x|\d{3}x10000|_570x/i.test(
            `${im.currentSrc || ""}${im.src || ""}`,
          ),
      ).length;
      const s = big * 30 + imgs.length;
      if (s > scoreBest) {
        scoreBest = s;
        best = el;
      }
    }
    swRoot = best;
  }
  if (!swRoot) return [];
  const inst = swRoot.swiper || swRoot.__swiper__ || swRoot._swiper;
  if (!inst || !inst.slides) return [];
  let real = [...inst.slides].filter(
    (s) => !s.classList.contains("swiper-slide-duplicate"),
  );
  real.sort((a, b) => {
    const ia = parseInt(a.getAttribute("data-swiper-slide-index") ?? "-1", 10);
    const ib = parseInt(b.getAttribute("data-swiper-slide-index") ?? "-1", 10);
    if (ia >= 0 && ib >= 0 && ia !== ib) return ia - ib;
    return 0;
  });
  const want = Math.max(0, parseInt(String(i), 10) || 0);
  const slide = real[want];
  if (!slide) return [];

  const out = [];
  const seen = new Set();
  const push = (u) => {
    const s = (u || "").trim();
    if (!s.startsWith("http")) return;
    const k = s.split("?")[0];
    if (seen.has(k)) return;
    seen.add(k);
    out.push(s);
  };
  const grabImg = (img) => {
    push(img.currentSrc || img.src);
    push(img.getAttribute("data-src"));
    push(img.getAttribute("data-original"));
    push(img.getAttribute("data-lazy-src"));
    const ss = img.getAttribute("srcset");
    if (ss) ss.split(",").forEach((p) => push(p.trim().split(/\s+/)[0]));
  };

  slide.querySelectorAll("img").forEach(grabImg);
  slide.querySelectorAll("picture source").forEach((s) => {
    const ss = s.getAttribute("srcset");
    if (ss) ss.split(",").forEach((p) => push(p.trim().split(/\s+/)[0]));
    push(s.getAttribute("src"));
  });
  slide.querySelectorAll("[class*='slide-item']").forEach((sl) => {
    sl.querySelectorAll("img").forEach(grabImg);
  });
  const bg0 = getComputedStyle(slide).backgroundImage;
  const m0 = bg0 && /\surl\s*\(\s*["']?([^"'()]+)["']?\s*\)/i.exec(bg0);
  if (m0) push(m0[1].trim());
  slide.querySelectorAll("*").forEach((node) => {
    const bg = getComputedStyle(node).backgroundImage;
    const m = bg && /\surl\s*\(\s*["']?([^"'()]+)["']?\s*\)/i.exec(bg);
    if (m) push(m[1].trim());
  });
  return out;
}"""

_GALLERY_COLLECT_ALL_SLIDES_JS = r"""() => {
  const mainEl = document.querySelector("main") || document.body;
  const frac = mainEl.querySelector(
    ".swiper-pagination-fraction, [class*='gallery-fraction']",
  );
  let swRoot = frac?.closest(".swiper") || null;
  if (!swRoot) {
    let best = null,
      scoreBest = -1;
    for (const el of mainEl.querySelectorAll(".swiper")) {
      if (/(thumb|thumbnail)/i.test(String(el.className || ""))) continue;
      const imgs = [...el.querySelectorAll("img")];
      const big = imgs.filter(
        (im) =>
          (im.naturalWidth || im.width || 0) >= 350 ||
          /_790x|\d{3}x10000|_570x/i.test(
            `${im.currentSrc || ""}${im.src || ""}`,
          ),
      ).length;
      const s = big * 30 + imgs.length;
      if (s > scoreBest) {
        scoreBest = s;
        best = el;
      }
    }
    swRoot = best;
  }
  if (!swRoot) return [];

  const out = [];
  const seen = new Set();
  const push = (u) => {
    const s = (u || "").trim();
    if (!s.startsWith("http")) return;
    const k = s.split("?")[0];
    if (seen.has(k)) return;
    seen.add(k);
    out.push(s);
  };
  const grabImg = (img) => {
    push(img.currentSrc || img.src);
    push(img.getAttribute("data-src"));
    push(img.getAttribute("data-lazy-src"));
    const ss = img.getAttribute("srcset");
    if (ss) ss.split(",").forEach((p) => push(p.trim().split(/\s+/)[0]));
  };

  swRoot.querySelectorAll(".swiper-slide").forEach((slide) => {
    slide.querySelectorAll("img").forEach(grabImg);
    slide.querySelectorAll("picture source").forEach((s) => {
      const ss = s.getAttribute("srcset");
      if (ss) ss.split(",").forEach((p) => push(p.trim().split(/\s+/)[0]));
    });
  });
  return out;
}"""

_GALLERY_THUMB_LARGE_URLS_JS = r"""() => {
  const mainEl = document.querySelector("main") || document.body;
  const swipers = [...mainEl.querySelectorAll(".swiper")];
  const mainFrac = mainEl.querySelector(
    ".swiper-pagination-fraction, [class*='gallery-fraction']",
  );
  const mainSw = mainFrac?.closest(".swiper") || null;
  const thumbCandidates = swipers.filter((s) => s && s !== mainSw);
  thumbCandidates.sort((a, b) => {
    const cnt = (root) =>
      [...root.querySelectorAll("img")].filter((img) =>
        `${img.currentSrc || ""}${img.src || ""}`.includes("220x220"),
      ).length;
    return cnt(b) - cnt(a);
  });
  const thumbSw = thumbCandidates[0];
  if (!thumbSw) return [];

  const out = [];
  const seen = new Set();
  const push = (u) => {
    const s = (u || "").trim();
    if (!s.startsWith("http")) return;
    const k = s.split("?")[0];
    if (seen.has(k)) return;
    seen.add(k);
    out.push(s);
  };
  const up = (raw) => {
    let u = (raw || "").trim();
    if (!u || !u.toLowerCase().includes("alicdn")) return u;
    const low = u.toLowerCase();
    const j = low.indexOf(".jpg");
    if (j >= 0) u = u.slice(0, j + 4);
    if (!u.includes("alicdn.com")) return u;
    u = u.replace(/_220x220Q80\.jpg_\.webp/gi, "_570x10000Q80.jpg_.webp");
    u = u.replace(/_220x220/gi, "_570x10000");
    return u;
  };

  thumbSw.querySelectorAll(".swiper-slide img, img").forEach((img) => {
    const raw = (img.currentSrc || img.src || "").trim();
    if (!raw.startsWith("http")) return;
    push(up(raw));
  });
  return out;
}"""

_GALLERY_ADVANCE_JS = r"""() => {
  const mainEl = document.querySelector("main") || document.body;
  const frac = mainEl.querySelector(
    ".swiper-pagination-fraction, [class*='gallery-fraction']",
  );
  let swRoot = frac?.closest(".swiper") || null;
  if (!swRoot) {
    let best = null,
      scoreBest = -1;
    for (const el of mainEl.querySelectorAll(".swiper")) {
      if (/(thumb|thumbnail)/i.test(String(el.className || ""))) continue;
      const imgs = [...el.querySelectorAll("img")];
      const big = imgs.filter(
        (im) =>
          (im.naturalWidth || im.width || 0) >= 350 ||
          /_790x|\d{3}x10000|_570x/i.test(
            `${im.currentSrc || ""}${im.src || ""}`,
          ),
      ).length;
      const s = big * 30 + imgs.length;
      if (s > scoreBest) {
        scoreBest = s;
        best = el;
      }
    }
    swRoot = best;
  }
  if (!swRoot) return false;

  const inst = swRoot.swiper || swRoot.__swiper__ || swRoot._swiper;
  try {
    if (inst && typeof inst.slideNext === "function") {
      inst.slideNext(400);
      return true;
    }
  } catch (e) {}

  const nextBtn =
    swRoot.querySelector(
      ".swiper-button-next:not(.swiper-button-lock):not(.swiper-button-disabled)",
    ) ||
    swRoot.querySelector("button[class*='swiper-button-next']");
  const parentNext = swRoot.parentElement?.querySelector(".swiper-button-next");
  for (const b of [nextBtn, parentNext]) {
    if (b && b.offsetParent !== null && !b.classList.contains("swiper-button-disabled")) {
      b.click();
      return true;
    }
  }
  return false;
}"""

_GALLERY_SLIDE_COUNT_JS = r"""() => {
  const mainEl = document.querySelector("main") || document.body;
  const frac = mainEl.querySelector(
    ".swiper-pagination-fraction, [class*='gallery-fraction']",
  );
  let swRoot = frac?.closest(".swiper") || null;
  if (!swRoot) {
    let best = null,
      scoreBest = -1;
    for (const el of mainEl.querySelectorAll(".swiper")) {
      if (/(thumb|thumbnail)/i.test(String(el.className || ""))) continue;
      const imgs = [...el.querySelectorAll("img")];
      const big = imgs.filter(
        (im) =>
          (im.naturalWidth || im.width || 0) >= 350 ||
          /_790x|\d{3}x10000|_570x/i.test(
            `${im.currentSrc || ""}${im.src || ""}`,
          ),
      ).length;
      const s = big * 30 + imgs.length;
      if (s > scoreBest) {
        scoreBest = s;
        best = el;
      }
    }
    swRoot = best;
  }
  if (!swRoot) return { slideCount: 0 };
  const inst = swRoot.swiper || swRoot.__swiper__ || swRoot._swiper;
  if (!inst || !inst.slides || !inst.slides.length) return { slideCount: 0 };
  let real = [...inst.slides].filter(
    (s) => !s.classList.contains("swiper-slide-duplicate"),
  );
  real.sort((a, b) => {
    const ia = parseInt(a.getAttribute("data-swiper-slide-index") ?? "-1", 10);
    const ib = parseInt(b.getAttribute("data-swiper-slide-index") ?? "-1", 10);
    if (ia >= 0 && ib >= 0 && ia !== ib) return ia - ib;
    return 0;
  });
  const n = real.length;
  return { slideCount: n };
}"""

_GALLERY_SLIDE_TO_JS = r"""([i]) => {
  const mainEl = document.querySelector("main") || document.body;
  const frac = mainEl.querySelector(
    ".swiper-pagination-fraction, [class*='gallery-fraction']",
  );
  let swRoot = frac?.closest(".swiper") || null;
  if (!swRoot) {
    let best = null,
      scoreBest = -1;
    for (const el of mainEl.querySelectorAll(".swiper")) {
      if (/(thumb|thumbnail)/i.test(String(el.className || ""))) continue;
      const imgs = [...el.querySelectorAll("img")];
      const big = imgs.filter(
        (im) =>
          (im.naturalWidth || im.width || 0) >= 350 ||
          /_790x|\d{3}x10000|_570x/i.test(
            `${im.currentSrc || ""}${im.src || ""}`,
          ),
      ).length;
      const s = big * 30 + imgs.length;
      if (s > scoreBest) {
        scoreBest = s;
        best = el;
      }
    }
    swRoot = best;
  }
  if (!swRoot) return false;
  const inst = swRoot.swiper || swRoot.__swiper__ || swRoot._swiper;
  if (!inst || !inst.slides || !inst.slides.length) return false;
  let real = [...inst.slides].filter(
    (s) => !s.classList.contains("swiper-slide-duplicate"),
  );
  real.sort((a, b) => {
    const ia = parseInt(a.getAttribute("data-swiper-slide-index") ?? "-1", 10);
    const ib = parseInt(b.getAttribute("data-swiper-slide-index") ?? "-1", 10);
    if (ia >= 0 && ib >= 0 && ia !== ib) return ia - ib;
    return 0;
  });
  const want = Math.max(0, parseInt(String(i), 10) || 0);
  const slide = real[want];
  if (!slide) return false;
  const domIdx = [...inst.slides].indexOf(slide);
  if (domIdx < 0) return false;
  try {
    if (inst.params && inst.params.loop && typeof inst.slideToLoop === "function") {
      inst.slideToLoop(want, 0);
    } else {
      inst.slideTo(domIdx, 0);
    }
  } catch (e) {
    try {
      if (inst.params && inst.params.loop && typeof inst.slideToLoop === "function") {
        inst.slideToLoop(want, 0);
      } else {
        return false;
      }
    } catch (e2) {
      return false;
    }
  }
  return true;
}"""


def _hibox_sweep_product_gallery(page: Any) -> tuple[List[str], int]:
    """Thu thập URL swiper chính: ưu tiên slideTo(0..n-1); fallback slideNext + phím.
    Trả về (danh_sách_url, swiper_slide_count đọc được)."""

    acc: List[str] = []

    slide_n = 0
    try:
        sc = page.evaluate(_GALLERY_SLIDE_COUNT_JS)
        slide_n = int((sc or {}).get("slideCount") or 0)
    except Exception:
        slide_n = 0

    if slide_n >= 2:
        for i in range(slide_n):
            try:
                page.evaluate(_GALLERY_SLIDE_TO_JS, [i])
            except Exception:
                pass
            page.wait_for_timeout(600)
            try:
                batch = page.evaluate(_GALLERY_COLLECT_FOR_INDEX_JS, [i])
            except Exception:
                batch = []
            if isinstance(batch, list):
                acc = _dedupe_urls(acc + [str(x) for x in batch if x])

    try:
        thumbs = page.evaluate(_GALLERY_THUMB_LARGE_URLS_JS)
        if isinstance(thumbs, list) and thumbs:
            acc = _dedupe_urls(acc + [str(x) for x in thumbs if x])
    except Exception:
        pass

    try:
        sweep_all = page.evaluate(_GALLERY_COLLECT_ALL_SLIDES_JS)
        if isinstance(sweep_all, list) and sweep_all:
            acc = _dedupe_urls(acc + [str(x) for x in sweep_all if x])
    except Exception:
        pass

    try:
        max_steps = int(page.evaluate(_GALLERY_ESTIMATE_STEPS_JS))
    except Exception:
        max_steps = 14
    max_steps = max(12, min(max_steps, 40))

    acc_fb: List[str] = list(acc)
    stable = 0
    prev_len = -1
    for _ in range(max_steps):
        try:
            batch = page.evaluate(_GALLERY_COLLECT_JS)
        except Exception:
            batch = []
        if isinstance(batch, list):
            acc_fb = _dedupe_urls(acc_fb + [str(x) for x in batch if x])

        if len(acc_fb) == prev_len:
            stable += 1
            if stable >= 7:
                break
        else:
            stable = 0
            prev_len = len(acc_fb)

        progressed = False
        try:
            progressed = bool(page.evaluate(_GALLERY_ADVANCE_JS))
        except Exception:
            progressed = False
        if not progressed:
            try:
                page.keyboard.press("ArrowRight")
            except Exception:
                pass
        page.wait_for_timeout(480 if progressed else 280)

    return acc_fb, slide_n


def scrape_hibox_item(url: str) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright

    def _route_block_jivo(route) -> None:
        u = route.request.url
        if "jivosite" in u or "jivo" in u.lower():
            route.abort()
        else:
            route.continue_()

    js = """() => {
      const og = (p) =>
        document.querySelector(`meta[property="og:${p}"]`)?.getAttribute("content") || "";
      const ogImg = (og("image") || "").trim();

      const specsRoot = (() => {
        const sums = [...document.querySelectorAll("summary")];
        const hit = sums.find((s) => (s.innerText || "").includes("Барааны үзүүлэлт"));
        return hit?.closest("details") || null;
      })();
      const inSpecs = (el) => specsRoot && specsRoot.contains(el);

      const push = (arr, seen, u) => {
        const s = (u || "").trim();
        if (!s.startsWith("http")) return;
        const k = s.split("?")[0];
        if (seen.has(k)) return;
        seen.add(k);
        arr.push(s);
      };
      const imgUrl = (img) =>
        (img.currentSrc || img.src || img.getAttribute("data-src") || "").trim();

      const gallery = [];
      const description = [];
      const other = [];
      const seenG = new Set();
      const seenD = new Set();
      const seenO = new Set();

      const mainEl = document.querySelector("main") || document.body;
      const firstDetails = mainEl.querySelector("details");

      [...mainEl.querySelectorAll("img")].forEach((img) => {
        if (inSpecs(img)) return;
        const url = imgUrl(img);
        if (!url.startsWith("http")) return;
        const rect = img.getBoundingClientRect();
        const w = rect.width || img.naturalWidth || 0;
        const h = rect.height || img.naturalHeight || 0;
        if (w > 0 && h > 0 && w < 40 && h < 40) return;

        let zone = "other";
        let p = img;
        for (let i = 0; i < 14 && p; i++, p = p.parentElement) {
          const cls = (p.className || "").toString();
          if (
            /swiper|carousel|zoom|magnifier|product[_-]?image|gallery|Gallery|thumb|lightbox/i.test(
              cls,
            )
          ) {
            zone = "gallery";
            break;
          }
        }
        if (zone === "other") {
          p = img;
          for (let i = 0; i < 14 && p; i++, p = p.parentElement) {
            const cls = (p.className || "").toString();
            if (
              /prose|description|detail-content|article|content-body|editor|richtext/i.test(cls)
            ) {
              zone = "description";
              break;
            }
          }
        }
        if (zone === "gallery") push(gallery, seenG, url);
        else if (zone === "description") push(description, seenD, url);
        else push(other, seenO, url);
      });

      const demoteUrl = (arr, u) => {
        const k = u.split("?")[0];
        for (let i = arr.length - 1; i >= 0; i--) {
          if (arr[i].split("?")[0] === k) arr.splice(i, 1);
        }
      };

      if (gallery.length === 0 && firstDetails) {
        [...mainEl.querySelectorAll("img")].forEach((img) => {
          if (inSpecs(img)) return;
          const url = imgUrl(img);
          if (!url.startsWith("http")) return;
          const before =
            firstDetails.compareDocumentPosition(img) & Node.DOCUMENT_POSITION_PRECEDING;
          if (!before) return;
          const rect = img.getBoundingClientRect();
          const w = rect.width || img.naturalWidth || 0;
          if (w < 100) return;
          push(gallery, seenG, url);
          demoteUrl(other, url);
          demoteUrl(description, url);
        });
      }

      const ogKey = ogImg.split("?")[0];
      if (ogKey) {
        [other, description, gallery].forEach((arr) => {
          for (let i = arr.length - 1; i >= 0; i--) {
            if (arr[i].split("?")[0] === ogKey) arr.splice(i, 1);
          }
        });
      }

      let codeEl = null;
      document.querySelectorAll("*").forEach((e) => {
        const t = (e.innerText || "").trim();
        if (t.startsWith("Код:")) codeEl = e;
      });
      const codeLine = codeEl ? (codeEl.innerText || "").trim() : "";
      const codes = [];
      (document.body.innerText || "").replace(/Код:\\s*([-\\w]+)/g, (_, c) => {
        codes.push(c);
        return _;
      });
      const nums = [];
      (document.body.innerText || "").replace(/\\d{2,3}(?:,\\d{3})+|\\d{5,7}/g, (m) => {
        nums.push(m);
        return m;
      });
      const main = (document.body.innerText || "").match(
        /Код:\\s*([-\\w]+)\\s*\\n\\s*(\\d{2,3}(?:,\\d{3})+|\\d{5,7})/m,
      );

      const pickVideoUrl = () => {
        const candidates = [];
        const tryPush = (u) => {
          let s = (u || "").trim();
          if (!s) return;
          if (s.startsWith("//")) s = "https:" + s;
          if (!s.startsWith("http")) return;
          candidates.push(s);
        };
        document.querySelectorAll("video source[src]").forEach((el) =>
          tryPush(el.getAttribute("src")),
        );
        document.querySelectorAll("video[src]").forEach((el) => tryPush(el.getAttribute("src")));
        tryPush(
          document.querySelector('meta[property="og:video"]')?.getAttribute("content"),
        );
        tryPush(
          document.querySelector('meta[property="og:video:url"]')?.getAttribute("content"),
        );
        for (const u of candidates) {
          const low = u.toLowerCase();
          if (low.includes("cloud.video.taobao.com") && low.includes(".mp4")) return u;
          if (/\\.mp4(\\?|$)/i.test(u)) return u;
        }
        const html = document.documentElement?.innerHTML || "";
        const m = html.match(
          /https?:\\/\\/cloud\\.video\\.taobao\\.com\\/[^"'\\s<>]+\\.mp4/i,
        );
        if (m) return m[0];
        return "";
      };

      return {
        page_url: window.location.href,
        title: document.title || "",
        og_title: og("title"),
        og_description: og("description"),
        og_image: og("image"),
        video_url: pickVideoUrl(),
        h1:
          [...document.querySelectorAll("h1")]
            .map((e) => (e.innerText || "").trim())
            .filter(Boolean)[0] || "",
        code_line: codeLine,
        sku_candidates: [...new Set(codes)],
        main_sku: main ? main[1] : "",
        main_price: main ? main[2] : "",
        number_tokens_sample: [...new Set(nums)].slice(0, 48),
        gallery_images: gallery,
        description_images: description,
        other_images: other,
      };
    }"""

    sheet_js = """() => {
      let best = "";
      let bestZ = -1;
      const scan = (needCombo) => {
        document.querySelectorAll("div").forEach((d) => {
          const cs = window.getComputedStyle(d);
          if (cs.position !== "fixed") return;
          if (cs.display === "none" || cs.visibility === "hidden") return;
          const z = parseInt(cs.zIndex || "0", 10);
          const t = (d.innerText || "").trim();
          if (t.length < (needCombo ? 40 : 28)) return;
          if (needCombo && !/###\\d{2}/.test(t)) return;
          if (!needCombo) {
            if (!/Өнгө|ӨНГӨ/i.test(t)) return;
            if (!/Хэмжээ|ХЭМЖЭЭ/i.test(t)) return;
          }
          if (z > bestZ || (z === bestZ && t.length > best.length)) {
            bestZ = z;
            best = t;
          }
        });
      };
      scan(true);
      if (!best.trim()) {
        bestZ = -1;
        scan(false);
      }
      return best.slice(0, 12000);
    }"""

    _COLOR_VARIANT_IMAGES_JS = r"""() => {
      const cand = [];
      const colorWord = /Өнгө|ӨНГӨ/i;
      const sizeWord = /Хэмжээ|ХЭМЖЭЭ/i;
      const sheetCombo = /###[\s\S]*?\d{2}/;
      [...document.body.querySelectorAll("*")].forEach((el) => {
        try {
          const cs = window.getComputedStyle(el);
          if (cs.position !== "fixed") return;
          if (cs.display === "none" || cs.visibility === "hidden") return;
          const txt = el.innerText || "";
          if (!colorWord.test(txt)) return;
          if (!sizeWord.test(txt) && !sheetCombo.test(txt)) return;
          const z = parseInt(cs.zIndex || "0", 10) || 0;
          const rect = el.getBoundingClientRect();
          const area = Math.max(rect.width * rect.height, 0);
          cand.push({ el, z, area });
        } catch (_) {}
      });
      cand.sort((a, b) => {
        if (b.z !== a.z) return b.z - a.z;
        return b.area - a.area;
      });
      let pane = cand[0]?.el;
      if (!pane && sheetCombo) {
        const fb = [];
        [...document.body.querySelectorAll("*")].forEach((el) => {
          try {
            const cs = window.getComputedStyle(el);
            if (cs.position !== "fixed") return;
            if (cs.display === "none" || cs.visibility === "hidden") return;
            const txt = el.innerText || "";
            if (!sheetCombo.test(txt)) return;
            const z = parseInt(cs.zIndex || "0", 10) || 0;
            const rect = el.getBoundingClientRect();
            const area = Math.max(rect.width * rect.height, 0);
            fb.push({ el, z, area });
          } catch (_) {}
        });
        fb.sort((a, b) => {
          if (b.z !== a.z) return b.z - a.z;
          return b.area - a.area;
        });
        pane = fb[0]?.el;
      }
      if (!pane || !pane.querySelectorAll) return { urls: [], labels: [], sizes: [] };

      const extractSizes = () => {
        let yMarker = pane.getBoundingClientRect().top;
        for (const e of pane.querySelectorAll("*")) {
          const t = (e.textContent || "").replace(/[\u00a0\s]+/g, " ").trim();
          if (
            (/^Хэмжээ\s*:?$/i.test(t) || /^ХЭМЖЭЭ\b/i.test(t)) &&
            t.length < 56
          ) {
            const bot = e.getBoundingClientRect().bottom;
            if (bot > yMarker) yMarker = bot;
          }
        }
        const out = [];
        const seen = new Set();
        const wraps = [...pane.querySelectorAll("div[class*='flex-wrap']")];
        wraps.sort(
          (a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top,
        );
        for (const wrap of wraps) {
          const r = wrap.getBoundingClientRect();
          if (r.top + 8 < yMarker) continue;
          if (r.height < 16 || r.width < 40) continue;
          for (const tile of wrap.querySelectorAll(":scope > div")) {
            if (tile.querySelector("img")) continue;
            let txt = "";
            const p2 = tile.querySelector(":scope > div.p-2");
            if (p2) txt = (p2.textContent || "").trim();
            if (!txt)
              txt = ((tile.innerText || "").trim().split(/\n/)[0] || "").trim();
            txt = txt.replace(/\s+/g, " ");
            if (!txt || txt.length > 64) continue;
            if (/^Хэмжээ|^ХЭМЖЭЭ|^өнгө|^ӨНГӨ|^Сонгосон$/i.test(txt))
              continue;
            if (/Үлдэгдэл/i.test(txt)) continue;
            const k = txt.toLowerCase();
            if (seen.has(k)) continue;
            seen.add(k);
            out.push(txt);
          }
          if (out.length) break;
        }
        return out;
      };

      const sizesList = extractSizes();

      let yBelow = pane.getBoundingClientRect().top + 90;
      for (const e of pane.querySelectorAll("*")) {
        const t = (e.textContent || "").replace(/[\u00a0\s]+/g, " ").trim();
        if (
          (/^Өнгө\s*:/i.test(t) || /^ӨНГӨ\b/.test(t)) &&
          t.length < 84
        ) {
          yBelow = Math.max(yBelow, e.getBoundingClientRect().bottom);
        }
      }

      let yCap = pane.getBoundingClientRect().bottom;
      for (const e of pane.querySelectorAll("*")) {
        const t = (e.textContent || "").replace(/[\u00a0\s]+/g, " ").trim();
        if ((/\bХэмжээ\b|\bХЭМЖЭЭ\b/i.test(t)) && t.length < 84) {
          yCap = Math.min(yCap, e.getBoundingClientRect().top);
        }
      }

      const bandTop = yBelow + 10;
      const bandBot = Math.min(yCap - 32, yBelow + 260);
      const pw = Math.max(pane.getBoundingClientRect().width, 1);
      const blobs = [];

      const normImgUrl = (raw) => {
        let u = (raw || "").trim();
        if (!u) return "";
        if (u.startsWith("//")) u = "https:" + u;
        const low = u.toLowerCase();
        if (low.includes("alicdn")) {
          const j = low.indexOf(".jpg");
          if (j >= 0) u = u.slice(0, j + 4);
        }
        return u;
      };

      const labelFromTileTitle = (tit) => {
        if (!tit || !String(tit).trim()) return "";
        const s = String(tit);
        const beforeStock = s.split(/Үлдэгдэл/i)[0].replace(/\r/g, "\n");
        let line = beforeStock.split(/\n/)[0].trim();
        if (!line) line = beforeStock.replace(/\n/g, " ").trim();
        line = line.replace(/\s+/g, " ").trim();
        line = line.replace(/\s+\d+\s+Models\b/gi, "").trim();
        if (!line || line.length > 120) return "";
        if (/^өнгө\s*:?$/i.test(line)) return "";
        return line;
      };

      const labelForImg = (img) => {
        if (!img) return "";
        let n = img;
        for (let step = 0; step < 16 && n; step++) {
          if (n.nodeType === 1 && n.getAttribute) {
            const tit = n.getAttribute("title");
            const lab = labelFromTileTitle(tit);
            if (lab) return lab;
          }
          n = n.parentElement;
        }
        const alt = (img.getAttribute("alt") || "").trim();
        if (alt && alt.length > 1 && alt.length < 120) return alt.slice(0, 120);
        n = img.parentElement;
        for (let step = 0; step < 7 && n; step++) {
          const aria = (n.getAttribute && (n.getAttribute("aria-label") || n.getAttribute("title"))) || "";
          const fromAria = labelFromTileTitle(aria);
          if (fromAria) return fromAria;
          const role = n.getAttribute && n.getAttribute("role");
          if (role === "radio" || role === "button" || n.tagName === "BUTTON" || n.tagName === "LABEL") {
            let t = (n.textContent || "").replace(/[\u00a0\s]+/g, " ").trim();
            if (t.includes("\n")) t = t.split("\n").find((x) => x.trim().length) || t;
            t = t.slice(0, 120);
            if (t.length > 1 && !/^Өнгө\s*:/i.test(t) && !/^ӨНГӨ\b/i.test(t) && !/Хэмжээ|ХЭМЖЭЭ/i.test(t)) return t;
          }
          n = n.parentElement;
        }
        return "";
      };

      /** Modal Hibox 1 màu: ảnh vuông trên cùng + một chip «cursor-pointer» chứa tên trong div.p-2. */
      const trySingleColorModalHero = () => {
        const wraps = [...pane.querySelectorAll("div.flex.flex-row.gap-2.flex-wrap")];
        let tiles = [];
        let label = "";
        for (const w of wraps) {
          const row = [...w.querySelectorAll(":scope > div")].filter((t) => {
            const c = (t.getAttribute("class") || "").toString();
            return (
              /cursor-pointer/.test(c) &&
              /rounded-md|rounded-lg/.test(c) &&
              t.querySelector(":scope > div.p-2")
            );
          });
          if (row.length !== 1) continue;
          const tile = row[0];
          let tit = (tile.getAttribute("title") || "").trim();
          tit = tit.split(/Үлдэгдэл/i)[0].trim();
          const p2 = tile.querySelector(":scope > div.p-2");
          let txt = (p2 && (p2.textContent || "").trim()) || "";
          txt = txt.replace(/\s+/g, " ").trim();
          if (!txt || txt.length > 160) continue;
          if (/^Хэмжээ|^ХЭМЖЭЭ|^өнгө|^ӨНГӨ|^Сонгосон$/i.test(txt)) continue;
          label = labelFromTileTitle(txt) || labelFromTileTitle(tit) || txt;
          if (!label) continue;
          tiles = row;
          break;
        }
        if (!label || tiles.length !== 1) return null;

        const heroRows = [...pane.querySelectorAll("div.flex.justify-between.items-start")];
        let heroUrl = "";
        for (const hb of heroRows) {
          const c = (hb.getAttribute("class") || "").toString();
          if (!c.includes("gap-4")) continue;
          if (!c.includes("p-6") && !c.includes("pb-3")) continue;
          const img = hb.querySelector(":scope > img");
          if (!img) continue;
          let u =
            img.currentSrc ||
            img.src ||
            img.getAttribute("data-src") ||
            img.getAttribute("data-lazy-src") ||
            "";
          u = normImgUrl(u);
          if (u.startsWith("http")) {
            heroUrl = u;
            break;
          }
        }
        if (!heroUrl) return null;
        return { urls: [heroUrl], labels: [label], sizes: sizesList };
      };

      const monoHero = trySingleColorModalHero();
      if (monoHero && monoHero.urls && monoHero.urls.length) {
        return monoHero;
      }

      const collectFromSwatchTitleTiles = () => {
        const row = [];
        const picColorLine = /Зургийн\s+өнгө|picture\s+color|图色|如图所示|按图片/i;
        const pickFromImgRelaxed = (img, lab) => {
          const rect = img.getBoundingClientRect();
          if (!rect.width || !rect.height) return null;
          if (rect.width < 28 || rect.height < 28) return null;
          if (rect.width > 520 || rect.height > 520) return null;
          let u =
            img.currentSrc ||
            img.src ||
            img.getAttribute("data-src") ||
            img.getAttribute("data-lazy-src") ||
            "";
          if (typeof u !== "string") return null;
          u = normImgUrl(u);
          if (!u.startsWith("http")) return null;
          return { u, left: rect.left + rect.width / 2, top: rect.top + rect.height / 2, lab };
        };
        const pickFromImg = (img, lab) => {
          const rect = img.getBoundingClientRect();
          if (!rect.width || !rect.height) return null;
          if (rect.width < 28 || rect.height < 28) return null;
          if (rect.width > 480 || rect.height > 480) return null;
          let u =
            img.currentSrc ||
            img.src ||
            img.getAttribute("data-src") ||
            img.getAttribute("data-lazy-src") ||
            "";
          if (typeof u !== "string") return null;
          u = normImgUrl(u);
          if (!u.startsWith("http")) return null;
          if (!u.includes("alicdn.com") && !u.includes("gw.alicdn.com")) return null;
          return { u, left: rect.left + rect.width / 2, top: rect.top + rect.height / 2, lab };
        };
        for (const holder of pane.querySelectorAll("[title]")) {
          const tit = holder.getAttribute("title") || "";
          if (!/Үлдэгдэл|үлдэгдэл/i.test(tit)) continue;
          const lab = labelFromTileTitle(tit);
          if (!lab) continue;
          let picked = null;
          if (holder.tagName === "IMG")
            picked = pickFromImg(holder, lab);
          if (!picked) {
            for (const img of holder.querySelectorAll("img")) {
              picked = pickFromImg(img, lab);
              if (picked) break;
            }
          }
          if (picked) row.push(picked);
        }
        for (const holder of pane.querySelectorAll("[title], button, [role='radio'], label")) {
          const tit = (holder.getAttribute("title") || "").trim();
          const txt0 = (holder.innerText || "").trim().split(/\n/)[0] || "";
          if (!picColorLine.test(tit) && !picColorLine.test(txt0)) continue;
          const lab = labelFromTileTitle(txt0 || tit) || txt0 || tit;
          let picked = null;
          if (holder.tagName === "IMG")
            picked = pickFromImg(holder, lab) || pickFromImgRelaxed(holder, lab);
          if (!picked) {
            for (const img of holder.querySelectorAll("img")) {
              picked = pickFromImg(img, lab) || pickFromImgRelaxed(img, lab);
              if (picked) break;
            }
          }
          if (!picked) {
            const paneRect = pane.getBoundingClientRect();
            for (const img of pane.querySelectorAll("img")) {
              const r = img.getBoundingClientRect();
              if (r.top > paneRect.top + 260) continue;
              picked = pickFromImg(img, lab) || pickFromImgRelaxed(img, lab);
              if (picked) break;
            }
          }
          if (picked) row.push(picked);
        }
        row.sort((a, b) => {
          const dy = a.top - b.top;
          if (Math.abs(dy) > 58) return dy;
          return a.left - b.left;
        });
        const urls = [];
        const labels = [];
        const seen = new Set();
        for (const b of row) {
          const k = b.u.split("?")[0];
          if (seen.has(k)) continue;
          seen.add(k);
          urls.push(b.u);
          labels.push(b.lab);
        }
        return { urls, labels, sizes: sizesList };
      };

      const fromTitles = collectFromSwatchTitleTiles();
      if (fromTitles.urls.length > 0) {
        return fromTitles;
      }

      [...pane.querySelectorAll("img")].forEach((img) => {
        const rect = img.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        if (rect.width < 40 || rect.height < 40) return;
        if (rect.bottom < bandTop - 6) return;
        if (rect.top > bandBot + 6) return;
        if (rect.width > pw * 0.74) return;
        let u =
          img.currentSrc ||
          img.src ||
          img.getAttribute("data-src") ||
          img.getAttribute("data-lazy-src") ||
          "";
        if (typeof u !== "string") return;
        u = normImgUrl(u);
        if (!u.startsWith("http")) return;

        blobs.push({
          u,
          left: rect.left + rect.width / 2,
          top: rect.top + rect.height / 2,
          img,
        });
        const ss = img.getAttribute("srcset") || img.getAttribute("data-srcset");
        if (ss) {
          ss.split(",").forEach((p) => {
            const part = normImgUrl((p.trim().split(/\s+/)[0] || "").trim());
            if (part.startsWith("http"))
              blobs.push({
                u: part,
                left: rect.left + rect.width / 2,
                top: rect.top + rect.height / 2,
                img,
              });
          });
        }
      });

      blobs.sort((a, b) => {
        const dy = a.top - b.top;
        if (Math.abs(dy) > 58) return dy;
        return a.left - b.left;
      });

      const urls = [];
      const labels = [];
      const seen = new Set();
      for (const b of blobs) {
        const k = b.u.split("?")[0];
        if (seen.has(k)) continue;
        seen.add(k);
        urls.push(b.u);
        labels.push(labelForImg(b.img));
      }
      return { urls, labels, sizes: sizesList };
    }"""

    variant_sheet = ""
    raw: Dict[str, Any] = {}
    specs_data: Dict[str, Any] = {}
    gallery_sweep_urls: List[str] = []
    gallery_swiper_slide_count = 0
    color_variant_urls: List[str] = []
    color_variant_labels: List[str] = []
    variant_sheet_sizes_dom: List[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        ctx = browser.new_context(
            viewport={"width": 1366, "height": 900},
            locale="mn-MN",
            timezone_id="Asia/Ulaanbaatar",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        ctx.route("**/*", _route_block_jivo)
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        page = ctx.new_page()

        def _grab_variant_sheet_visual() -> tuple[List[str], List[str], List[str]]:
            try:
                out_ev = page.evaluate(_COLOR_VARIANT_IMAGES_JS)
            except Exception:
                return [], [], []
            if isinstance(out_ev, list):
                uu = _dedupe_urls([str(x) for x in out_ev if x])
                return uu, [""] * len(uu), []
            if isinstance(out_ev, dict):
                urls_raw = out_ev.get("urls") or []
                labels_raw = list(out_ev.get("labels") or [])
                sizes_raw = list(out_ev.get("sizes") or [])
                urls_in = [str(x).strip() for x in urls_raw if str(x).strip()]
                labels_in: List[str] = []
                for i in range(len(urls_in)):
                    if i < len(labels_raw) and labels_raw[i] is not None:
                        labels_in.append(str(labels_raw[i]).strip())
                    else:
                        labels_in.append("")
                sz_clean: List[str] = []
                seen_sz: set[str] = set()
                for x in sizes_raw:
                    s = str(x).strip()
                    if not s:
                        continue
                    k = s.casefold()
                    if k in seen_sz:
                        continue
                    seen_sz.add(k)
                    sz_clean.append(s)
                uu, ll = _dedupe_urls_lockstep(urls_in, labels_in)
                return uu, ll, sz_clean
            return [], [], []

        try:
            try:
                page.goto(
                    "https://www.google.com/",
                    wait_until="domcontentloaded",
                    timeout=45_000,
                )
            except Exception:
                pass
            page.wait_for_timeout(520 + random.randint(0, 380))
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=90_000,
                referer="https://www.google.com/",
            )
            try:
                page.wait_for_load_state("networkidle", timeout=45_000)
            except Exception:
                pass
            page.wait_for_timeout(1900 + random.randint(0, 450))
            try:
                gallery_sweep_urls, gallery_swiper_slide_count = _hibox_sweep_product_gallery(page)
            except Exception:
                gallery_sweep_urls = []
                gallery_swiper_slide_count = 0
            try:
                loc = page.locator("summary").filter(has_text=re.compile(r"Барааны\s*үзүүлэлт", re.I))
                if loc.count():
                    loc.first.scroll_into_view_if_needed(timeout=8000)
                    page.wait_for_timeout(500)
                    loc.first.click(force=True, timeout=6000)
                    page.wait_for_timeout(2600)
                    page.evaluate(
                        """() => {
                      const sums = [...document.querySelectorAll("summary")];
                      const hit = sums.find((s) => (s.innerText || "").includes("Барааны үзүүлэлт"));
                      const det = hit?.closest("details");
                      if (det) {
                        det.scrollIntoView({ block: "nearest", behavior: "instant" });
                        const inner = det.querySelector(".prose, [class*='prose'], .detail, [class*='detail']") || det;
                        try {
                          inner.scrollBy(0, 1200);
                        } catch (e) {}
                      }
                    }"""
                    )
                    page.wait_for_timeout(1200)
            except Exception:
                pass
            specs_data = page.evaluate(
                """() => {
              const sums = [...document.querySelectorAll("summary")];
              const hit = sums.find((s) => (s.innerText || "").includes("Барааны үзүүлэлт"));
              if (!hit) return { specs_text: "", specs_images: [] };
              const det = hit.closest("details");
              const root = det || hit.parentElement;
              if (!root) return { specs_text: "", specs_images: [] };
              const imgs = [];
              const seen = new Set();
              const push = (u) => {
                const s = typeof u === "string" ? u.trim() : "";
                if (!s || !s.startsWith("http")) return;
                const k = s.split("?")[0];
                if (seen.has(k)) return;
                seen.add(k);
                imgs.push(s);
              };
              const grabSrcSet = (ss) => {
                if (!ss) return;
                ss.split(",").forEach((p) => push(p.trim().split(/\\s+/)[0]));
              };
              root.querySelectorAll("img").forEach((img) => {
                push(img.currentSrc || img.src || img.getAttribute("data-src") ||
                  img.getAttribute("data-original") || img.getAttribute("data-lazy-src"));
                grabSrcSet(img.getAttribute("srcset"));
              });
              root.querySelectorAll("picture source[srcset]").forEach((s) =>
                grabSrcSet(s.getAttribute("srcset")));
              [...root.querySelectorAll("*")].forEach((node) => {
                const bg =
                  typeof window !== "undefined" &&
                  window.getComputedStyle(node).backgroundImage;
                const m =
                  bg && /url\\s*\\(\\s*["']?([^"')]+)["']?\\s*\\)/i.exec(bg);
                if (m && m[1]) push(m[1]);
              });
              return {
                specs_text: (root.innerText || "").trim().slice(0, 62000),
                specs_images: imgs,
              };
            }"""
            )
            if not isinstance(specs_data, dict):
                specs_data = {}
            raw = page.evaluate(js)
            page.evaluate("() => window.scrollTo(0, Math.max(0, document.body.scrollHeight - 400))")
            page.wait_for_timeout(400)
            cart_opened = False
            for label in ("САГСЛАХ", "ШУУД АВАХ"):
                try:
                    page.get_by_role("button", name=label).first.click(force=True, timeout=6000)
                    page.wait_for_timeout(3200)
                    cart_opened = True
                    break
                except Exception:
                    continue
            variant_sheet = page.evaluate(sheet_js) if cart_opened else ""
            if cart_opened:
                page.wait_for_timeout(450)
                color_variant_urls, color_variant_labels, variant_sheet_sizes_dom = (
                    _grab_variant_sheet_visual()
                )
            if not variant_sheet.strip():
                try:
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(450)
                except Exception:
                    pass
                for label in ("ШУУД АВАХ", "САГСЛАХ"):
                    try:
                        page.get_by_role("button", name=label).first.click(force=True, timeout=6000)
                        page.wait_for_timeout(3200)
                        variant_sheet = page.evaluate(sheet_js)
                        if variant_sheet.strip():
                            page.wait_for_timeout(450)
                            (
                                color_variant_urls,
                                color_variant_labels,
                                variant_sheet_sizes_dom,
                            ) = _grab_variant_sheet_visual()
                            break
                    except Exception:
                        continue
        finally:
            ctx.close()
            browser.close()

    if not isinstance(raw, dict):
        raise RuntimeError("Không đọc được dữ liệu từ trang.")

    nums = raw.get("number_tokens_sample") or []
    sku = ""
    cand = raw.get("sku_candidates") or []
    if raw.get("main_sku"):
        sku = str(raw["main_sku"]).strip()
    elif cand:
        sku = str(cand[0])
    elif raw.get("code_line"):
        m = re.search(r"Код:\s*([-\w]+)", str(raw["code_line"]))
        sku = m.group(1).strip() if m else ""
    gal = raw.get("gallery_images") or []
    desc_imgs = raw.get("description_images") or []
    oth = raw.get("other_images") or []
    if not isinstance(gal, list):
        gal = []
    if not isinstance(desc_imgs, list):
        desc_imgs = []
    if not isinstance(oth, list):
        oth = []
    gal_u = _collapse_gallery_resolution_variants(_dedupe_urls([str(x) for x in gallery_sweep_urls]))
    if not gal_u:
        gal_u = _collapse_gallery_resolution_variants(_dedupe_urls([str(x) for x in gal]))
    desc_u = _dedupe_urls([str(x) for x in desc_imgs])
    oth_u = _dedupe_urls([str(x) for x in oth])
    gal_u = _dedupe_urls([_hibox_scheme_and_trunc(u) for u in gal_u])
    og_image_out = _hibox_scheme_and_trunc(str(raw.get("og_image") or "").strip())
    thumb_fallback = og_image_out or (gal_u[0] if gal_u else "")
    color_variant_urls, color_variant_labels = _dedupe_urls_lockstep(
        [_hibox_scheme_and_trunc(u) for u in color_variant_urls],
        color_variant_labels,
    )
    desc_u = _dedupe_urls([_hibox_scheme_and_trunc(u) for u in desc_u])
    oth_u = _dedupe_urls([_hibox_scheme_and_trunc(u) for u in oth_u])
    if gal_u and color_variant_urls:
        gkeys = {_hibox_alicdn_image_key(u) for u in gal_u}
        cv_f = [u for u in color_variant_urls if _hibox_alicdn_image_key(u) in gkeys]
        # Chỉ lọc khi không làm mất ô màu: thumbnail ӨНГӨ có thể khác O1CN so với ảnh slide gallery.
        if cv_f and len(cv_f) == len(color_variant_urls):
            u_to_lab = {
                color_variant_urls[i]: (
                    color_variant_labels[i] if i < len(color_variant_labels) else ""
                )
                for i in range(len(color_variant_urls))
            }
            color_variant_urls = cv_f
            color_variant_labels = [str(u_to_lab.get(u, "") or "") for u in cv_f]
    main_price = str(raw.get("main_price") or "").strip()
    colors_parse_order, sizes_from_sheet, pairs_from_sheet = parse_hibox_variant_block(
        variant_sheet or "",
    )
    sizes = sizes_from_sheet or variant_sheet_sizes_dom
    pairs = list(pairs_from_sheet)
    n_img = len(color_variant_urls)

    pic_mode = _hibox_variant_sheet_is_picture_color_mode(variant_sheet or "")
    if n_img == 0 and sizes and pic_mode and thumb_fallback:
        color_variant_urls = [thumb_fallback]
        color_variant_labels = ["Màu như ảnh"]
        n_img = 1

    for i in range(len(color_variant_labels)):
        color_variant_labels[i] = _hibox_normalize_color_label_for_catalog(str(color_variant_labels[i]))

    if n_img == 1 and thumb_fallback and color_variant_urls:
        lab0 = (color_variant_labels[0] if color_variant_labels else "").strip()
        u0 = str(color_variant_urls[0] or "").lower()
        has_modal_thumb = "alicdn.com" in u0 or "gw.alicdn.com" in u0
        # Giữ ảnh chip/modal (thường alicdn) — chỉ fallback OG/gallery khi chưa có hoặc nhãn «Màu như ảnh».
        if not has_modal_thumb and (lab0 == "Màu như ảnh" or pic_mode):
            color_variant_urls[0] = thumb_fallback

    if n_img > 0:
        colors = []
        for i in range(n_img):
            dom_lab = (
                color_variant_labels[i].strip()
                if i < len(color_variant_labels) and (color_variant_labels[i] or "").strip()
                else ""
            )
            parse_lab = (
                str(colors_parse_order[i]).strip()
                if i < len(colors_parse_order) and colors_parse_order[i]
                else ""
            )
            lab = dom_lab or parse_lab or f"Màu {i + 1}"
            lab = _hibox_normalize_color_label_for_catalog(lab)
            colors.append(lab)
    else:
        colors = [_hibox_normalize_color_label_for_catalog(str(c)) for c in colors_parse_order]
    if not pairs and colors and sizes:
        pairs = [{"color": str(c), "size": str(s)} for c in colors for s in sizes]
    specs_text = str((specs_data or {}).get("specs_text") or "")[:32000]
    spec_imgs = _dedupe_urls(list((specs_data or {}).get("specs_images") or []))
    spec_imgs = _dedupe_urls([_hibox_scheme_and_trunc(u) for u in spec_imgs])

    link_slug = ""
    try:
        from app.services.import_hibox_scraper import extract_hibox_slug

        link_slug = (extract_hibox_slug(url) or "").strip()
    except Exception:
        link_slug = ""

    row = {
        "url": raw.get("page_url") or url,
        "title": raw.get("og_title") or raw.get("title") or "",
        "h1": raw.get("h1") or "",
        "description": raw.get("og_description") or "",
        "og_image": og_image_out,
        "supplier_sku_scraped": sku,
        "sku": link_slug or sku,
        "code_ui": raw.get("code_line") or "",
        "price_listed": main_price or _extract_primary_price(nums if isinstance(nums, list) else []),
        "price_estimate": _extract_primary_price(nums if isinstance(nums, list) else []),
        "colors_json": json.dumps(colors, ensure_ascii=False),
        "sizes_json": json.dumps(sizes, ensure_ascii=False),
        "variant_color_size_json": json.dumps(pairs, ensure_ascii=False),
        "color_variant_images_json": json.dumps(color_variant_urls[:40], ensure_ascii=False),
        "color_variant_labels_json": json.dumps(color_variant_labels[:40], ensure_ascii=False),
        "color_variant_image_count": len(color_variant_urls),
        "specs_text": specs_text,
        "specs_images_json": json.dumps(spec_imgs, ensure_ascii=False),
        "specs_image_count": len(spec_imgs),
        "video_url": (str(raw.get("video_url") or "").strip()),
        "gallery_images_json": json.dumps(gal_u[:80], ensure_ascii=False),
        "gallery_image_count": len(gal_u),
        "gallery_swiper_slide_count": gallery_swiper_slide_count,
        "description_images_json": json.dumps(desc_u[:80], ensure_ascii=False),
        "description_image_count": len(desc_u),
        "other_images_json": json.dumps(oth_u[:80], ensure_ascii=False),
        "other_image_count": len(oth_u),
    }
    return row


def write_excel(row: Dict[str, Any]) -> str:
    export_dir = os.path.join("app", "static", "uploads")
    os.makedirs(export_dir, exist_ok=True)
    fn = f"hibox_item_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    path = os.path.join(export_dir, fn)
    df = pd.DataFrame([row])
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Product", index=False)
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?", default="https://hibox.mn/v/abb-922386436529")
    args = ap.parse_args()
    try:
        row = scrape_hibox_item(args.url.strip())
    except Exception as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        sys.exit(1)
    out = write_excel(row)
    print("Đã xuất:", os.path.abspath(out))
    print("sku:", row.get("sku"))
    print("price_listed:", row.get("price_listed"))
    print("title:", (row.get("title") or "")[:100])
    print("video_url:", (row.get("video_url") or "").strip() or "(trống)")
    print("colors:", row.get("colors_json"))
    print("sizes:", row.get("sizes_json"))
    print("cặp màu×size:", len(json.loads(row.get("variant_color_size_json") or "[]")))
    print(
        "ảnh màu (ӨНГӨ):",
        row.get("color_variant_image_count"),
        "| gallery:",
        row.get("gallery_image_count"),
        "(slides swiper:",
        row.get("gallery_swiper_slide_count"),
        ")",
        "| mô tả:",
        row.get("description_image_count"),
        "| khác:",
        row.get("other_image_count"),
        "| specs:",
        row.get("specs_image_count"),
    )
    print("specs_text:", len(row.get("specs_text") or ""), "chars")


if __name__ == "__main__":
    main()
