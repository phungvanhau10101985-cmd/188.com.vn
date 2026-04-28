import { cdnUrl } from '@/lib/cdn-url';
import { getCdnPublicBase } from '@/lib/site-config';

const CDN_BASE = getCdnPublicBase();

/** Tham số tối ưu ảnh cho CDN nội bộ; URL khác giữ nguyên. */
export function optimizeImageUrl(
  url: string,
  options?: { width?: number; height?: number; quality?: number }
): string {
  const width = options?.width ?? 600;
  const height = options?.height ?? width;
  const quality = options?.quality ?? 80;
  if (!url) return cdnUrl('/images/placeholder-product.jpg');
  if (url.includes(CDN_BASE)) {
    return `${url}?w=${width}&h=${height}&q=${quality}&fit=crop&auto=format`;
  }
  return url;
}
