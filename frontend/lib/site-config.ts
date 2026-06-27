/**
 * Cấu hình một chỗ — khớp backend `BUNNY_CDN_PUBLIC_BASE` / Bunny Pull Zone.
 *
 * Production (khách ISP chặn *.b-cdn.net): dùng custom hostname cùng domain site, vd.
 *   NEXT_PUBLIC_CDN_URL=https://cdn.188.com.vn
 * Hoặc proxy Nginx: https://188.com.vn/cdn-media (xem deploy/nginx-cdn-proxy.conf.example).
 */
export const CDN_PUBLIC_FALLBACK = 'https://188comvn.b-cdn.net';

export function getCdnPublicBase(): string {
  const fromEnv = (process.env.NEXT_PUBLIC_CDN_URL || '').trim().replace(/\/$/, '');
  return fromEnv || CDN_PUBLIC_FALLBACK;
}
