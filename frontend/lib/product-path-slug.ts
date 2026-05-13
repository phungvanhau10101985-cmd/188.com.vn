/**
 * Backend có thể trả `slug` là URL HTTPS đầy đủ (https://…/products/segment) hoặc chỉ segment.
 * Dùng hàm này trước khi ghép `/products/[slug]` trên Next.js.
 */
export function productPathSlugFromApi(slug: string | null | undefined, fallback?: string | null): string {
  const raw = (slug ?? '').trim() || (fallback ?? '').trim();
  if (!raw) return '';
  if (/^https?:\/\//i.test(raw)) {
    try {
      const u = new URL(raw);
      const segs = u.pathname.split('/').filter(Boolean);
      const i = segs.indexOf('products');
      if (i >= 0 && segs[i + 1]) return decodeURIComponent(segs[i + 1]);
      if (segs.length) return decodeURIComponent(segs[segs.length - 1]);
    } catch {
      return raw;
    }
  }
  return raw;
}

/** URL PDP công khai — nếu slug đã là URL thì dùng luôn, không ghép SITE_URL thêm lần. */
export function productPublicPdpUrl(
  slug: string | null | undefined,
  siteOrigin: string,
  fallbackSlug?: string | null,
): string {
  const s = (slug ?? '').trim();
  if (s && /^https?:\/\//i.test(s)) return s;
  const seg = productPathSlugFromApi(slug, fallbackSlug);
  const base = siteOrigin.replace(/\/$/, '');
  return seg ? `${base}/products/${encodeURIComponent(seg)}` : base;
}
