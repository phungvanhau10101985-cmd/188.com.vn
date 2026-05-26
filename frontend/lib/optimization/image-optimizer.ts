import { getOptimizedImage } from '@/lib/image-utils';
import { cdnUrl } from '@/lib/cdn-url';

/** CDN nội bộ + alicdn: resize theo kích thước hiển thị, chất lượng cao. */
export function optimizeImageUrl(
  url: string,
  options?: { width?: number; height?: number; quality?: number }
): string {
  if (!url) return cdnUrl('/images/placeholder-product.jpg');
  return getOptimizedImage(url, {
    width: options?.width ?? 400,
    height: options?.height ?? 400,
    quality: options?.quality ?? 90,
    fallbackStrategy: 'local',
  });
}
