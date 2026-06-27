import { getCdnPublicBase } from '@/lib/site-config';

const BUNNY_LEGACY_HOST_SUFFIX = '.b-cdn.net';

/** Host Pull Zone mặc định cũ — một số ISP VN không phân giải được *.b-cdn.net. */
export function isLegacyBunnyCdnHost(hostname: string): boolean {
  return (hostname || '').trim().toLowerCase().endsWith(BUNNY_LEGACY_HOST_SUFFIX);
}

/**
 * URL ảnh lưu trong DB/HTML trỏ `*.b-cdn.net` → base CDN hiện tại (vd. `https://cdn.188.com.vn`).
 * Khách không cần đổi DNS; chỉ cần deploy `NEXT_PUBLIC_CDN_URL` trỏ domain khách truy cập được.
 */
export function rewriteLegacyBunnyCdnUrl(raw: string): string {
  const s = (raw || '').trim();
  if (!s) return s;

  try {
    const withScheme = s.startsWith('//') ? `https:${s}` : s;
    if (!/^https?:\/\//i.test(withScheme)) return s;

    const parsed = new URL(withScheme);
    if (!isLegacyBunnyCdnHost(parsed.hostname)) return s;

    const baseClean = getCdnPublicBase().replace(/\/$/, '');
    const baseHost = new URL(`${baseClean}/`).hostname.toLowerCase();
    if (parsed.hostname.toLowerCase() === baseHost) return s;

    return `${baseClean}${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return s;
  }
}

/**
 * Chuẩn hoá ảnh Taobao/1688: `//img.alicdn.com/...`, `//cbu01.alicdn.com/img/ibank/...`, v.v.
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
  if (!/^https?:\/\//i.test(s) && /alicdn\.com/i.test(s)) {
    return `https://${s.replace(/^\/+/, '')}`;
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
