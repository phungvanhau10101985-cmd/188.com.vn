/** Trang soạn tìm kiếm mobile (kiểu Shopee) — kết quả vẫn ở `/?q=`. */

export const MOBILE_SEARCH_HREF = '/tim-kiem';

export function isMobileSearchComposePath(pathname: string | null | undefined): boolean {
  if (pathname == null || pathname === '') return false;
  const p = pathname.replace(/\/$/, '') || '/';
  return p === MOBILE_SEARCH_HREF;
}

export function buildMobileSearchHref(q?: string | null): string {
  const term = (q || '').trim();
  if (!term) return MOBILE_SEARCH_HREF;
  return `${MOBILE_SEARCH_HREF}?q=${encodeURIComponent(term)}`;
}
