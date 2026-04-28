import { getCdnPublicBase } from '@/lib/site-config';

/**
 * Ảnh trong `frontend/public/` khi đã đẩy Bunny — base từ NEXT_PUBLIC_CDN_URL hoặc fallback site-config.
 * Custom hostname: sau CNAME → *.b-cdn.net và SSL trên Bunny, đặt NEXT_PUBLIC_CDN_URL = https://cdn.domain.com
 */
export function cdnUrl(path: string): string {
  const base = getCdnPublicBase();
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${base}${p}`;
}

/** OG / JSON-LD: cùng base với CDN (env hoặc fallback trong site-config) */
export function absolutePublicAssetUrl(path: string): string {
  return cdnUrl(path);
}
