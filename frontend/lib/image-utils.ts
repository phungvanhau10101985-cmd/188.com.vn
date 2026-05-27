// frontend/lib/image-utils.ts - OPTIMAL LONG-TERM SOLUTION
/**
 * Image Utility for Long-term Management
 * Features:
 * - Display-size URLs (alicdn suffix / Bunny Optimizer) — giữ chất lượng cao, giảm payload
 * - Multiple fallback strategies
 * - Local placeholder generation
 */

import { cdnUrl } from '@/lib/cdn-url';
import { getCdnPublicBase } from '@/lib/site-config';

const CDN_CONFIG = {
  baseUrl: getCdnPublicBase(),
  placeholderService: 'https://images.unsplash.com',
  fallbackService: 'https://picsum.photos',
};

/** Giới hạn pixel tải về — ~2× mật độ hiển thị, không vượt ngưỡng hợp lý cho card/listing. */
const MAX_DISPLAY_PIXELS = 960;

function displayPixelSize(width: number, height: number): { w: number; h: number } {
  return {
    w: Math.min(Math.max(1, Math.ceil(width * 2)), MAX_DISPLAY_PIXELS),
    h: Math.min(Math.max(1, Math.ceil(height * 2)), MAX_DISPLAY_PIXELS),
  };
}

function truncateAlicdnToFirstJpg(url: string): string {
  const m = /\.jpg/i.exec(url);
  if (!m) return url;
  return url.slice(0, m.index! + 4);
}

function hasAlicdnResizeSuffix(url: string): boolean {
  return /\.jpg_\d+x\d+q\d+\.jpg/i.test(url);
}

/** Alibaba CDN: …-cib.jpg → …-cib.jpg_400x400q90.jpg (q90 — chất lượng cao, không nén mạnh). */
function applyAlicdnDisplaySize(
  url: string,
  width: number,
  height: number,
  quality = 90
): string {
  const lower = url.toLowerCase();
  if (!lower.includes('alicdn')) return url;
  if (lower.includes('gw.alicdn.com/mt/')) return url;
  if (hasAlicdnResizeSuffix(url)) return url;

  const base = truncateAlicdnToFirstJpg(url);
  if (!/\.jpg$/i.test(base)) return url;

  const w = Math.max(1, Math.round(width));
  const h = Math.max(1, Math.round(height));
  const q = Math.min(100, Math.max(75, Math.round(quality)));
  return `${base}_${w}x${h}q${q}.jpg`;
}

function isBunnyCdnUrl(url: string): boolean {
  try {
    const host = new URL(url).hostname.toLowerCase();
    const baseHost = new URL(CDN_CONFIG.baseUrl).hostname.toLowerCase();
    return host === baseHost || host.endsWith('.b-cdn.net');
  } catch {
    return url.includes(CDN_CONFIG.baseUrl);
  }
}

/** Bunny Optimizer: ?width=&quality=95 — resize edge, không ép WebP/AVIF nếu chất lượng giữ cao. */
function applyBunnyDisplaySize(url: string, width: number, quality = 95): string {
  if (!isBunnyCdnUrl(url)) return url;
  try {
    const u = new URL(url);
    if (u.searchParams.has('width')) return url;
    u.searchParams.set('width', String(Math.max(1, Math.round(width))));
    u.searchParams.set('quality', String(Math.min(100, Math.max(85, Math.round(quality)))));
    return u.toString();
  } catch {
    return url;
  }
}

const generateLocalPlaceholder = (
  width: number = 200,
  height: number = 200,
  text: string = 'No Image'
): string => {
  return `data:image/svg+xml;base64,${btoa(`
    <svg width="${width}" height="${height}" xmlns="http://www.w3.org/2000/svg">
      <rect width="100%" height="100%" fill="#f8f9fa"/>
      <text x="50%" y="50%" font-family="Arial, sans-serif" font-size="14" 
            fill="#6c757d" text-anchor="middle" dy=".3em">${text}</text>
    </svg>
  `)}`;
};

const getOptimizedImageUrl = (
  url: string,
  width: number = 400,
  height: number = 400,
  quality = 90
): string => {
  if (!url) return generateLocalPlaceholder(width, height);

  const { w, h } = displayPixelSize(width, height);

  if (url.toLowerCase().includes('alicdn')) {
    return applyAlicdnDisplaySize(url, w, h, quality);
  }
  if (isBunnyCdnUrl(url)) {
    return applyBunnyDisplaySize(url, Math.max(w, h), quality);
  }

  return url;
};

export const getOptimizedImage = (
  url: string | undefined,
  options: {
    width?: number;
    height?: number;
    quality?: number;
    fallbackStrategy?: 'local' | 'cdn' | 'external';
  } = {}
): string => {
  const { width = 400, height = 400, quality = 90, fallbackStrategy = 'local' } = options;

  if (!url) {
    return getFallbackImage(fallbackStrategy, width, height);
  }

  let processedUrl = url.trim();
  if (processedUrl.startsWith('//')) {
    processedUrl = 'https:' + processedUrl;
  } else if (processedUrl.startsWith('/') && processedUrl.length > 1) {
    const firstSegment = processedUrl.slice(1).split('/')[0] || '';
    if (firstSegment.includes('.')) {
      processedUrl = 'https:' + processedUrl;
    } else {
      processedUrl = cdnUrl(processedUrl);
    }
  }

  if (!isValidUrl(processedUrl)) {
    console.warn('Invalid image URL:', url);
    return getFallbackImage(fallbackStrategy, width, height);
  }

  try {
    return getOptimizedImageUrl(processedUrl, width, height, quality);
  } catch (error) {
    console.error('Error processing image URL:', error);
    return getFallbackImage(fallbackStrategy, width, height);
  }
};

const getFallbackImage = (strategy: string, width: number, height: number): string => {
  switch (strategy) {
    case 'cdn':
      return `${CDN_CONFIG.placeholderService}/photo-${width}x${height}/?fashion`;

    case 'external':
      return `${CDN_CONFIG.fallbackService}/${width}/${height}?grayscale&blur=2`;

    case 'local':
    default:
      return generateLocalPlaceholder(width, height, '188.com.vn');
  }
};

const isValidUrl = (url: string): boolean => {
  try {
    const parsedUrl = new URL(url);
    return parsedUrl.protocol === 'http:' || parsedUrl.protocol === 'https:';
  } catch {
    return false;
  }
};

export const getProductImages = (product: any) => {
  const mainImage = getOptimizedImage(product.main_image, {
    width: 600,
    height: 600,
    quality: 92,
    fallbackStrategy: 'local',
  });

  const galleryImages = (product.images || product.gallery || [])
    .slice(0, 5)
    .map((img: string, index: number) =>
      getOptimizedImage(img, {
        width: 300,
        height: 300,
        quality: 90,
        fallbackStrategy: index === 0 ? 'local' : 'external',
      })
    );

  return {
    main: mainImage,
    gallery: galleryImages.length > 0 ? galleryImages : [mainImage],
    thumbnails: galleryImages.map((img: string) =>
      getOptimizedImage(img, { width: 100, height: 100, quality: 88 })
    ),
  };
};

export const preloadImages = (urls: string[]): void => {
  if (typeof window !== 'undefined') {
    urls.forEach((url) => {
      const link = document.createElement('link');
      link.rel = 'preload';
      link.as = 'image';
      link.href = url;
      document.head.appendChild(link);
    });
  }
};
