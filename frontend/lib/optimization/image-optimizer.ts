import { cdnUrl } from '@/lib/cdn-url';
import { getCdnPublicBase } from '@/lib/site-config';

const CDN_BASE = getCdnPublicBase();

/** CDN nội bộ: giữ nguyên file gốc, không gắn tham số resize/nén. */
export function optimizeImageUrl(
  url: string,
  _options?: { width?: number; height?: number; quality?: number }
): string {
  if (!url) return cdnUrl('/images/placeholder-product.jpg');
  if (url.includes(CDN_BASE)) {
    return url;
  }
  return url;
}
