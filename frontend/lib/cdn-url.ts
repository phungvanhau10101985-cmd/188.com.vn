import { getCdnPublicBase } from '@/lib/site-config';

/**
 * Chuẩn hoá ảnh từ Taobao/1688 (thường là `//img.alicdn.com/...`).
 * Trường hợp hiếm: `/img.alicdn.com/...` (thiếu một dấu /) → vẫn coi là host tuyệt đối.
 */
export function normalizeRemoteImageUrlForDisplay(raw: string): string {
  const s = raw.trim();
  if (s.startsWith('//')) {
    return `https:${s}`;
  }
  if (s.startsWith('/') && s.length > 1) {
    const firstSegment = s.slice(1).split('/')[0] || '';
    if (firstSegment.includes('.')) {
      return `https:${s}`;
    }
  }
  return s;
}

/**
 * Ảnh trong `frontend/public/` khi đã đẩy Bunny — base từ NEXT_PUBLIC_CDN_URL hoặc fallback site-config.
 * Custom hostname: sau CNAME → *.b-cdn.net và SSL trên Bunny, đặt NEXT_PUBLIC_CDN_URL = https://cdn.domain.com
 *
 * Lưu ý: URL từ Taobao/1688 thường là protocol-relative (`//img.alicdn.com/...`).
 * Không được ghép base CDN vào những URL đó — trả về `https:` + path.
 */
export function cdnUrl(path: string): string {
  const raw = path.trim();
  if (raw.startsWith('//')) {
    return `https:${raw}`;
  }
  const base = getCdnPublicBase();
  const p = raw.startsWith('/') ? raw : `/${raw}`;
  return `${base}${p}`;
}

/** OG / JSON-LD: cùng base với CDN (env hoặc fallback trong site-config) */
export function absolutePublicAssetUrl(path: string): string {
  return cdnUrl(path);
}
