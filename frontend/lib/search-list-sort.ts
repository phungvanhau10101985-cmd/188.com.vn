/** F5 / reload / tìm lại — luôn gọi API (không đọc sessionStorage) để lưới làm mới. */
export function shouldBypassSearchSessionCache(): boolean {
  if (typeof window === 'undefined') return false;
  const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
  return nav?.type === 'reload' || nav?.type === 'navigate';
}

/** Sort mặc định trang `/?q=` — ngẫu nhiên mỗi lần tải / F5. */
export function resolveSearchListingSort(sortFromUrl: string | undefined): string {
  const userSort = (sortFromUrl || '').trim();
  return userSort || 'random';
}

export function isSearchRandomSort(sort: string | undefined): boolean {
  return resolveSearchListingSort(sort) === 'random';
}
