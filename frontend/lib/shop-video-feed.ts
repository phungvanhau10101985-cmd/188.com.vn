/** Đường dẫn feed lướt video (pathname, không kèm query). */
export const SHOP_VIDEO_FEED_PATH = '/luot-video-cung-shop';

/** Query khi mở feed từ trang chi tiết — client đọc và gắn clip đó lên đầu nếu có video. */
export const SHOP_VIDEO_START_SLUG_PARAM = 'start_slug';

/**
 * Slug sản phẩm nếu pathname là `/products/[slug]` (đã decode segment).
 */
export function productDetailSlugFromPathname(pathname: string | null | undefined): string | undefined {
  if (!pathname) return undefined;
  const m = pathname.match(/^\/products\/([^/]+)\/?$/);
  const seg = m?.[1];
  if (!seg) return undefined;
  try {
    return decodeURIComponent(seg);
  } catch {
    return seg;
  }
}

export function shopVideoFeedHrefFromPathname(pathname: string | null | undefined): string {
  const slug = productDetailSlugFromPathname(pathname);
  if (!slug) return SHOP_VIDEO_FEED_PATH;
  const q = new URLSearchParams({ [SHOP_VIDEO_START_SLUG_PARAM]: slug });
  return `${SHOP_VIDEO_FEED_PATH}?${q}`;
}
