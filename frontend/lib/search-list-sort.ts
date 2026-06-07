import type { Product } from '@/types/api';

/** Sort tìm kiếm mặc định — luôn id giảm dần để F5 không nhảy thứ tự (cache cũ / race). */
export function sortSearchResultProducts(
  products: Product[],
  sort: string | undefined,
): Product[] {
  const s = (sort || 'id_desc').trim().toLowerCase().replace(/-/g, '_');
  if (
    s === 'views_desc' ||
    s === 'newest' ||
    s === 'oldest' ||
    s === 'purchases_desc' ||
    s === 'available_desc' ||
    s === 'available_asc' ||
    s === 'id_asc'
  ) {
    return products;
  }
  return [...products].sort((a, b) => b.id - a.id);
}

/** F5 / reload — bỏ sessionStorage để luôn đồng bộ API (tránh cache chunk cũ 12+36). */
export function shouldBypassSearchSessionCache(): boolean {
  if (typeof window === 'undefined') return false;
  const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
  return nav?.type === 'reload';
}
