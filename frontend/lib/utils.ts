// frontend/lib/utils.ts - UPDATED TO USE IMAGE UTILS
import { Product } from '@/types/api';
import { getOptimizedImage, getProductImages } from './image-utils';

export const formatPrice = (price: number | undefined): string => {
  if (!price && price !== 0) return 'Liên hệ';
  return new Intl.NumberFormat('vi-VN', {
    style: 'currency',
    currency: 'VND'
  }).format(price);
};

export const getDiscountPercentage = (originalPrice: number, currentPrice: number): number => {
  if (!originalPrice || originalPrice <= currentPrice) return 0;
  return Math.round(((originalPrice - currentPrice) / originalPrice) * 100);
};

export const truncateText = (text: string, maxLength: number): string => {
  if (!text) return '';
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength) + '...';
};

/** Giá trị rỗng từ Excel/API (nan, NaN, null, undefined, ''). Không hiển thị lên UI. */
export function isDisplayableValue(value: string | null | undefined): value is string {
  if (value == null || value === '') return false;
  const s = String(value).trim().toLowerCase();
  return s !== 'nan' && s !== 'undefined';
}

/** Trả về chuỗi nếu có ý nghĩa, ngược lại undefined (ẩn trường Thương hiệu/Xuất xứ). */
export function displayableBrandOrOrigin(value: string | null | undefined): string | undefined {
  return isDisplayableValue(value) ? String(value).trim() : undefined;
}

/**
 * Trả về thương hiệu hiển thị cho SEO trang chi tiết sản phẩm.
 * - Có dữ liệu chuẩn, thương hiệu rõ ràng: hiển thị bình thường.
 * - null, rỗng "", hoặc chuỗi 'nan': gán mặc định '188.com.vn'.
 */
export function displayableBrandWithDefault(value: string | null | undefined): string {
  if (isDisplayableValue(value)) return String(value).trim();
  return '188.com.vn';
}

// DEPRECATED: Sử dụng getOptimizedImage từ image-utils thay thế
export const validateImageUrl = (url: string | undefined): string => {
  return getOptimizedImage(url, { fallbackStrategy: 'local' });
};

// DEPRECATED: Sử dụng getProductImages từ image-utils thay thế
export const getProductMainImage = (product: Product): string => {
  const images = getProductImages(product);
  return images.main;
};

export const formatDate = (dateString: string): string => {
  try {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric'
    }).format(date);
  } catch {
    return dateString;
  }
};

export const generateSlug = (text: string): string => {
  return text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9 -]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .trim();
};