/**
 * Cấu hình một chỗ — khớp backend `BUNNY_CDN_PUBLIC_BASE` / Bunny Pull Zone.
 * Đặt NEXT_PUBLIC_CDN_URL trong frontend/.env.local (vd: https://188comvn.b-cdn.net).
 */
export const CDN_PUBLIC_FALLBACK = 'https://188comvn.b-cdn.net';

export function getCdnPublicBase(): string {
  const fromEnv = (process.env.NEXT_PUBLIC_CDN_URL || '').trim().replace(/\/$/, '');
  return fromEnv || CDN_PUBLIC_FALLBACK;
}
