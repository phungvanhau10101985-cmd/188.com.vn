// frontend/lib/image-utils.ts - OPTIMAL LONG-TERM SOLUTION
/**
 * Image Utility for Long-term Management
 * Features:
 * - CDN URLs: serve originals (no edge w/h/q/fit params)
 * - Multiple fallback strategies
 * - Local placeholder generation
 */

import { getCdnPublicBase } from '@/lib/site-config';

// CDN — trùng BUNNY_CDN_PUBLIC_BASE (backend) khi deploy
const CDN_CONFIG = {
  baseUrl: getCdnPublicBase(),
  placeholderService: 'https://images.unsplash.com',
  fallbackService: 'https://picsum.photos'
};

// Local placeholder SVG (không cần request external)
const generateLocalPlaceholder = (width: number = 200, height: number = 200, text: string = 'No Image'): string => {
  return `data:image/svg+xml;base64,${btoa(`
    <svg width="${width}" height="${height}" xmlns="http://www.w3.org/2000/svg">
      <rect width="100%" height="100%" fill="#f8f9fa"/>
      <text x="50%" y="50%" font-family="Arial, sans-serif" font-size="14" 
            fill="#6c757d" text-anchor="middle" dy=".3em">${text}</text>
    </svg>
  `)}`;
};

// CDN: trả về URL gốc (không w/h/q/fit/auto=format) để không resize/nén ở edge.
const getOptimizedImageUrl = (url: string, width: number = 400, height: number = 400, _quality?: number): string => {
  if (!url) return generateLocalPlaceholder(width, height);

  if (url.includes(CDN_CONFIG.baseUrl)) {
    return url;
  }

  return url;
};

// Main image validation and optimization function
export const getOptimizedImage = (
  url: string | undefined, 
  options: {
    width?: number;
    height?: number;
    quality?: number;
    fallbackStrategy?: 'local' | 'cdn' | 'external';
  } = {}
): string => {
  const { 
    width = 400, 
    height = 400, 
    fallbackStrategy = 'local'
  } = options;

  // Case 1: No URL provided
  if (!url) {
    return getFallbackImage(fallbackStrategy, width, height);
  }

  // Case 2: Fix protocol-relative and path-like external URLs (never prepend API base)
  let processedUrl = url.trim();
  if (processedUrl.startsWith('//')) {
    processedUrl = 'https:' + processedUrl;
  } else if (processedUrl.startsWith('/') && processedUrl.length > 1) {
    const firstSegment = processedUrl.slice(1).split('/')[0] || '';
    if (firstSegment.includes('.')) {
      processedUrl = 'https:' + processedUrl;
    }
  }

  // Case 3: Validate URL format
  if (!isValidUrl(processedUrl)) {
    console.warn('Invalid image URL:', url);
    return getFallbackImage(fallbackStrategy, width, height);
  }

  // Case 4: Return optimized URL
  try {
    return getOptimizedImageUrl(processedUrl, width, height);
  } catch (error) {
    console.error('Error processing image URL:', error);
    return getFallbackImage(fallbackStrategy, width, height);
  }
};

// Fallback strategies
const getFallbackImage = (strategy: string, width: number, height: number): string => {
  switch (strategy) {
    case 'cdn':
      // Sử dụng CDN placeholder service (nếu có)
      return `${CDN_CONFIG.placeholderService}/photo-${width}x${height}/?fashion`;
    
    case 'external':
      // Sử dụng external service như picsum
      return `${CDN_CONFIG.fallbackService}/${width}/${height}?grayscale&blur=2`;
    
    case 'local':
    default:
      // Sử dụng local SVG placeholder - KHÔNG CÓ REQUEST
      return generateLocalPlaceholder(width, height, '188.com.vn');
  }
};

// URL validation
const isValidUrl = (url: string): boolean => {
  try {
    const parsedUrl = new URL(url);
    return parsedUrl.protocol === 'http:' || parsedUrl.protocol === 'https:';
  } catch {
    return false;
  }
};

// Product-specific image helpers
export const getProductImages = (product: any) => {
  const mainImage = getOptimizedImage(product.main_image, { 
    width: 600, 
    height: 600,
    fallbackStrategy: 'local'
  });

  const galleryImages = (product.images || product.gallery || [])
    .slice(0, 5) // Limit to 5 images for performance
    .map((img: string, index: number) => 
      getOptimizedImage(img, { 
        width: 300, 
        height: 300,
        fallbackStrategy: index === 0 ? 'local' : 'external'
      })
    );

  return {
    main: mainImage,
    gallery: galleryImages.length > 0 ? galleryImages : [mainImage],
    thumbnails: galleryImages.map((img: string) => 
      getOptimizedImage(img, { width: 100, height: 100 })
    )
  };
};

// Preload critical images
export const preloadImages = (urls: string[]): void => {
  if (typeof window !== 'undefined') {
    urls.forEach(url => {
      const link = document.createElement('link');
      link.rel = 'preload';
      link.as = 'image';
      link.href = url;
      document.head.appendChild(link);
    });
  }
};