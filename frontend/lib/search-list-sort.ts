import type { Product } from '@/types/api';

/** Sort mặc định trang `/?q=` — ngẫu nhiên mỗi lần tải / F5. */
export function resolveSearchListingSort(sortFromUrl: string | undefined): string {
  const userSort = (sortFromUrl || '').trim().toLowerCase();
  // URL cũ từ bản fix id_desc — coi như ngẫu nhiên.
  if (!userSort || userSort === 'id_desc' || userSort === 'default') return 'random';
  return userSort;
}

export function isSearchRandomSort(sort: string | undefined): boolean {
  return resolveSearchListingSort(sort) === 'random';
}

/** Xáo lưới sau khi nhận API — hoạt động kể cả backend/cache trả cùng thứ tự. */
export function shuffleSearchProducts(products: Product[]): Product[] {
  const out = products.slice();
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/** Luôn bỏ sessionStorage với sort ngẫu nhiên / F5 / tìm lại. */
export function shouldBypassSearchSessionCache(sortFromUrl: string | undefined): boolean {
  if (isSearchRandomSort(sortFromUrl)) return true;
  if (typeof window === 'undefined') return false;
  const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
  return nav?.type === 'reload' || nav?.type === 'navigate';
}

/** URL legacy `sort=id_desc` trên trang tìm — xóa để dùng ngẫu nhiên. */
export function isLegacySearchStableSortParam(sortFromUrl: string | undefined): boolean {
  const s = (sortFromUrl || '').trim().toLowerCase();
  return s === 'id_desc' || s === 'default';
}
