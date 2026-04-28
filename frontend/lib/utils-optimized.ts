// frontend/lib/utils-optimized.ts
import { cdnUrl } from '@/lib/cdn-url';
import { optimizeImageUrl } from './optimization/image-optimizer';

// Enhanced formatPrice với caching
const priceCache = new Map<string, string>();
export const formatPrice = (price: number | null | undefined): string => {
  const priceValue = price || 0;
  const cacheKey = `price-${priceValue}`;
  
  if (priceCache.has(cacheKey)) {
    return priceCache.get(cacheKey)!;
  }

  if (!priceValue || isNaN(priceValue) || priceValue === 0) {
    const result = 'Liên hệ';
    priceCache.set(cacheKey, result);
    return result;
  }

  const result = new Intl.NumberFormat('vi-VN', {
    style: 'currency',
    currency: 'VND'
  }).format(priceValue);
  
  priceCache.set(cacheKey, result);
  return result;
};

// Enhanced image validation với optimization
export const validateAndOptimizeImageUrl = (
  url: string | undefined, 
  options?: { width?: number; quality?: number }
): string => {
  if (!url) return cdnUrl('/images/placeholder-product.jpg');
  
  return optimizeImageUrl(url, {
    width: options?.width || 600,
    quality: options?.quality || 80,
    ...options
  });
};

// Memory efficient text truncation
export const smartTruncate = (text: string, maxLength: number): string => {
  if (text.length <= maxLength) return text;
  
  // Try to break at word boundary
  const truncated = text.substring(0, maxLength);
  const lastSpace = truncated.lastIndexOf(' ');
  
  if (lastSpace > maxLength * 0.7) {
    return truncated.substring(0, lastSpace) + '...';
  }
  
  return truncated + '...';
};