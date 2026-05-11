import type { Product } from '@/types/api';

/** Same storefront origin semantics as PDP layout `absoluteImage`. */
function storefrontOrigin(): string {
  const fromSite =
    (typeof process !== 'undefined' ? process.env.NEXT_PUBLIC_SITE_URL : '')
      ?.trim()
      .replace(/\/$/, '') ?? '';
  const fromDomain =
    (typeof process !== 'undefined' ? process.env.NEXT_PUBLIC_DOMAIN : '')?.trim().replace(/\/$/, '') ??
    '';
  return fromSite || fromDomain || 'https://188.com.vn';
}

function toAbsoluteGalleryUrl(raw: string): string | null {
  const img = raw.trim();
  if (!img) return null;
  if (/^https?:\/\//i.test(img)) return img;
  if (img.startsWith('//')) return `https:${img}`;
  const base = storefrontOrigin();
  if (img.startsWith('/')) return `${base}${img}`;
  return `${base}/${img}`;
}

/** Same absolute URL as PDP gallery / layout (including `/uploads/...`). */
export function normalizeProductImageUrl(raw: string | undefined | null): string | null {
  if (typeof raw !== 'string') return null;
  return toAbsoluteGalleryUrl(raw);
}

/** Thư viện ảnh PDP: main_image + cột P (images) — không gộp gallery (ảnh chi tiết / Q) để tránh strip ảnh dài trong carousel. */
export function mergeProductGalleryPhotoUrls(product: Product): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  const add = (raw?: string | null) => {
    const u = typeof raw === 'string' ? toAbsoluteGalleryUrl(raw) : null;
    if (!u || !/^https?:\/\//i.test(u)) return;
    if (seen.has(u)) return;
    seen.add(u);
    out.push(u);
  };
  add(product.main_image);
  for (const img of product.images || []) add(img);
  return out;
}

/** Mọi URL ảnh (gồm gallery chi tiết) — dùng khi cần quét đầy đủ, không dùng cho carousel PDP. */
export function mergeProductPhotoUrlsIncludingDetail(product: Product): string[] {
  const base = mergeProductGalleryPhotoUrls(product);
  const seen = new Set(base);
  const out = [...base];
  const add = (raw?: string | null) => {
    const u = typeof raw === 'string' ? toAbsoluteGalleryUrl(raw) : null;
    if (!u || !/^https?:\/\//i.test(u)) return;
    if (seen.has(u)) return;
    seen.add(u);
    out.push(u);
  };
  for (const img of product.gallery || []) add(img);
  return out;
}
