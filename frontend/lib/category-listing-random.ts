import type { CategoryListingFilters } from '@/lib/category-seo';

/** Query param giữ thứ tự random khi phân trang (không hiện trên trang 1 nếu chưa có). */
export const CATEGORY_LISTING_REFRESH_PARAM = 'r';

export function categoryListingHasDeterministicFilters(
  filters?: CategoryListingFilters | null,
): boolean {
  const f = filters || {};
  return (
    (f.minPrice != null && !Number.isNaN(f.minPrice)) ||
    (f.maxPrice != null && !Number.isNaN(f.maxPrice)) ||
    Boolean(f.size?.trim()) ||
    Boolean(f.color?.trim()) ||
    Boolean(f.styleTag?.trim()) ||
    Boolean(f.sort?.trim())
  );
}

export function categoryListingUsesRandomSort(filters?: CategoryListingFilters | null): boolean {
  return !categoryListingHasDeterministicFilters(filters);
}

export function createCategoryListingRefreshToken(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID().replace(/-/g, '').slice(0, 16);
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

/** Seed cho một lượt xem danh mục — tái dùng từ URL khi phân trang, tạo mới mỗi lần vào/F5 trang 1. */
export function resolveCategoryListingRefresh(
  rawFromUrl: string | undefined,
  filters?: CategoryListingFilters | null,
): string | undefined {
  if (!categoryListingUsesRandomSort(filters)) return undefined;
  const trimmed = (rawFromUrl || '').trim();
  return trimmed || createCategoryListingRefreshToken();
}
