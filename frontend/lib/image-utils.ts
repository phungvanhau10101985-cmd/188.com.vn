/**
 * Image Utility for Long-term Management
 * Features:
 * - Alibaba CDN: URL gốc (không gắn _800x800q90…)
 * - Bunny CDN: optional width/quality query params
 * - Placeholder / fallback strategies
 */

import { cdnUrl, rewriteLegacyBunnyCdnUrl } from '@/lib/cdn-url';
import { getCdnPublicBase } from '@/lib/site-config';

const CDN_CONFIG = {
  baseUrl: getCdnPublicBase(),
  placeholderService: 'https://images.unsplash.com',
  fallbackService: 'https://picsum.photos',
};

/** PNG branding / QR — không ẩn trên web. */
const WEB_PNG_ALLOWLIST = [
  /logo.*188/i,
  /logo188/i,
  /favicon\.png/i,
  /logo_1x1_/i,
  /vietqr\.io/i,
  /\/icon\.png$/i,
  /\/app\/icon/i,
];

/** URL ảnh có đuôi .png (kể cả alicdn …-80-80.png, %2F…png). */
export function isPngImageUrl(url: string | undefined | null): boolean {
  const raw = (url || '').trim();
  if (!raw) return false;
  const lower = raw.toLowerCase();
  const pathOnly = lower.split('?')[0]?.split('#')[0] ?? lower;
  if (pathOnly.endsWith('.png')) return true;
  if (/\.png(?:[?&#]|_|%|$)/i.test(lower)) return true;
  try {
    const pathname = new URL(raw.startsWith('//') ? `https:${raw}` : raw).pathname.toLowerCase();
    return pathname.endsWith('.png') || /\.png_/i.test(pathname);
  } catch {
    return /\.png/i.test(pathOnly);
  }
}

/** PNG ảnh SP (gallery / mô tả PDP) — không dùng cho logo, cài đặt web, VietQR. */
export function isHiddenWebPngImageUrl(url: string | undefined | null): boolean {
  const raw = (url || '').trim();
  if (!raw || !isPngImageUrl(raw)) return false;
  const lower = raw.toLowerCase();
  return !WEB_PNG_ALLOWLIST.some((re) => re.test(lower));
}

/** Lọc URL gallery PDP — bỏ PNG ảnh sản phẩm. */
export function filterVisibleWebImageUrls(urls: Iterable<string | null | undefined>): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const raw of urls) {
    const u = (raw || '').trim();
    if (!u || isHiddenWebPngImageUrl(u)) continue;
    if (seen.has(u)) continue;
    seen.add(u);
    out.push(u);
  }
  return out;
}

/** Giới hạn pixel tải về — Bunny optimizer. */
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

export function isAlibabaCdnImageUrl(url: string): boolean {
  const lower = (url || '').trim().toLowerCase();
  if (!lower) return false;
  return (
    lower.includes('alicdn.com') ||
    lower.includes('alicdn.net') ||
    lower.includes('tbcdn.cn')
  );
}

/** Bỏ hậu tố nén sau cụm .jpg đầu tiên (vd. …cib.jpg_800x800q90.jpg → …cib.jpg). */
export function stripAlicdnToBaseJpg(url: string): string {
  const u = (url || '').trim();
  if (!u) return u;
  return truncateAlicdnToFirstJpg(u);
}

/** Alibaba CDN: dùng URL gốc — không gắn _800x800q90.jpg. */
function applyAlicdnDisplaySize(url: string): string {
  if (!isAlibabaCdnImageUrl(url)) return url;
  const lower = url.toLowerCase();
  if (lower.includes('gw.alicdn.com/mt/')) return url;

  let base = stripAlicdnToBaseJpg(url);
  base = base.replace(/\.webp\.jpg$/i, '.webp');
  base = base.replace(/\.png\.jpg$/i, '.png');
  base = base.replace(/(_\d+x\d+q?\d*|\.sum)\.(jpg|jpeg|png|webp)$/i, '');
  return base || url;
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

/** Bunny Optimizer: ?width=&quality=95 */
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

  let processed = url.trim();
  if (processed.startsWith('//')) processed = `https:${processed}`;

  const { w, h } = displayPixelSize(width, height);

  if (isAlibabaCdnImageUrl(processed)) {
    return applyAlicdnDisplaySize(processed);
  }
  if (isBunnyCdnUrl(processed)) {
    return applyBunnyDisplaySize(processed, Math.max(w, h), quality);
  }

  return processed;
};

export const getOptimizedImage = (
  url: string | undefined,
  options: {
    width?: number;
    height?: number;
    quality?: number;
    fallbackStrategy?: 'local' | 'cdn' | 'external';
    /** Chỉ bật trên PDP / ảnh thông tin SP — không ảnh hưởng logo, cài đặt web, listing. */
    hideProductPng?: boolean;
  } = {}
): string => {
  const {
    width = 400,
    height = 400,
    quality = 90,
    fallbackStrategy = 'local',
    hideProductPng = false,
  } = options;

  if (!url) {
    return getFallbackImage(fallbackStrategy, width, height);
  }

  let processedUrl = rewriteLegacyBunnyCdnUrl(url.trim());
  if (processedUrl.startsWith('//')) {
    processedUrl = `https:${processedUrl}`;
  } else if (processedUrl.startsWith('/') && processedUrl.length > 1) {
    const firstSegment = processedUrl.slice(1).split('/')[0] || '';
    if (firstSegment.includes('.')) {
      processedUrl = `https:${processedUrl}`;
    } else {
      processedUrl = cdnUrl(processedUrl);
    }
  }

  if (!isValidUrl(processedUrl)) {
    console.warn('Invalid image URL:', url);
    return getFallbackImage(fallbackStrategy, width, height);
  }

  if (hideProductPng && isHiddenWebPngImageUrl(processedUrl)) {
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

/** Ảnh đại diện SP đủ điều kiện hiển thị trên lưới (không placeholder / domain trống). */
export function hasValidProductImageUrl(url: string | undefined | null): boolean {
  const raw = (url || '').trim();
  if (!raw) return false;
  const lower = raw.toLowerCase();
  if (['null', 'none', 'nan', 'undefined', 'n/a', '-', '0'].includes(lower)) return false;
  if (/^(?:https?:\/\/)?(?:www\.)?188\.com\.vn\/?$/i.test(raw)) return false;
  if (lower.startsWith('data:image')) return raw.length > 16;
  if (raw.startsWith('//')) return raw.length > 4 && raw.includes('.');
  if (raw.startsWith('/')) return raw.length > 2;
  return isValidUrl(raw.startsWith('//') ? `https:${raw}` : raw);
}

export const getProductImages = (product: any, opts?: { hideProductPng?: boolean }) => {
  const hideProductPng = Boolean(opts?.hideProductPng);
  const rawGallery = hideProductPng
    ? filterVisibleWebImageUrls(product.images || product.gallery || [])
    : (product.images || product.gallery || []).filter(Boolean);

  const mainImage = getOptimizedImage(product.main_image, {
    width: 600,
    height: 600,
    quality: 92,
    fallbackStrategy: 'local',
    hideProductPng,
  });

  const galleryImages = rawGallery
    .slice(0, 5)
    .map((img: string, index: number) =>
      getOptimizedImage(img, {
        width: 300,
        height: 300,
        quality: 90,
        fallbackStrategy: index === 0 ? 'local' : 'external',
        hideProductPng,
      })
    );

  return {
    main: mainImage,
    gallery: galleryImages.length > 0 ? galleryImages : [mainImage],
    thumbnails: galleryImages.map((img: string) =>
      getOptimizedImage(img, { width: 100, height: 100, quality: 88, hideProductPng })
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
