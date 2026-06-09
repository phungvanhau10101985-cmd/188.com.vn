import type { Product } from '@/types/api';

const CACHE_PREFIX = '188-category-listing-v1';
const CACHE_MAX_AGE_MS = 15 * 60 * 1000;

export interface CategoryListingClientCacheEntry {
  products: Product[];
  total: number;
  totalPages: number;
  currentPage: number;
  pageSize: number;
  savedAt: number;
}

export function buildCategoryListingClientCacheKey(pathKey: string, listingQueryString: string): string {
  const normalizedQuery = new URLSearchParams(listingQueryString || '');
  normalizedQuery.sort();
  const qs = normalizedQuery.toString();
  return `${CACHE_PREFIX}:${pathKey || 'root'}:${qs}`;
}

export function readCategoryListingClientCache(
  key: string
): CategoryListingClientCacheEntry | null {
  if (typeof window === 'undefined' || !key) return null;
  try {
    const raw = window.sessionStorage.getItem(key) || window.localStorage.getItem(key);
    if (!raw) return null;
    const data = JSON.parse(raw) as Partial<CategoryListingClientCacheEntry>;
    if (!Array.isArray(data.products) || typeof data.savedAt !== 'number') return null;
    if (Date.now() - data.savedAt > CACHE_MAX_AGE_MS) {
      window.sessionStorage.removeItem(key);
      window.localStorage.removeItem(key);
      return null;
    }
    return {
      products: data.products,
      total: typeof data.total === 'number' ? data.total : data.products.length,
      totalPages: typeof data.totalPages === 'number' ? data.totalPages : 1,
      currentPage: typeof data.currentPage === 'number' ? data.currentPage : 1,
      pageSize: typeof data.pageSize === 'number' ? data.pageSize : data.products.length,
      savedAt: data.savedAt,
    };
  } catch {
    return null;
  }
}

export function writeCategoryListingClientCache(
  key: string,
  entry: Omit<CategoryListingClientCacheEntry, 'savedAt'>
): void {
  if (typeof window === 'undefined' || !key || entry.products.length === 0) return;
  const payload: CategoryListingClientCacheEntry = {
    ...entry,
    savedAt: Date.now(),
  };
  const raw = JSON.stringify(payload);
  try {
    window.sessionStorage.setItem(key, raw);
  } catch {
    // Ignore quota/privacy failures; DB cache remains the source of truth.
  }
  try {
    window.localStorage.setItem(key, raw);
  } catch {
    // localStorage only helps reopened tabs, so it is optional.
  }
}
