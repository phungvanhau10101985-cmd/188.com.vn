/** Redirect sau đăng nhập — chỉ đường dẫn nội bộ (pathname + ?query + #hash). */

export function isSafeRelativeRedirectPath(loc: string): boolean {
  const t = (loc || '').trim();
  if (!t.startsWith('/') || t.startsWith('//')) return false;
  if (t.includes('://')) return false;
  if (t.length > 2048) return false;
  return true;
}

/**
 * @param pathname ví dụ `/products/abc`
 * @param search chuỗi query có hoặc không có `?` (vd `shop_id=1` hoặc `?shop_id=1`)
 * @param hash có hoặc không có `#`
 */
export function composeReturnLocation(
  pathname: string | null | undefined,
  search: string | null | undefined,
  hash: string | null | undefined
): string {
  let p =
    pathname == null || pathname === ''
      ? '/'
      : pathname.startsWith('/')
        ? pathname
        : `/${pathname}`;
  if (p !== '/' && p.endsWith('/')) p = p.slice(0, -1) || '/';

  let qs = '';
  if (search != null && search !== '') {
    qs = search.startsWith('?') ? search : `?${search}`;
  }

  let h = '';
  if (hash != null && hash !== '') {
    h = hash.startsWith('#') ? hash : `#${hash}`;
  }

  const full = `${p}${qs}${h}`;
  return isSafeRelativeRedirectPath(full) ? full : '/';
}

/** Full path đã đúng định dạng — bọc vào `/auth/login?redirect=` */
export function buildAuthLoginHrefFromFullPath(fullPath: string): string {
  const safe = isSafeRelativeRedirectPath(fullPath) ? fullPath : '/';
  return `/auth/login?redirect=${encodeURIComponent(safe)}`;
}

/** Tiện ích với `usePathname` + `useSearchParams()` (+ hash tuỳ chọn, ví dụ `#qa`). */
export function buildAuthLoginHrefFromParts(
  pathname: string | null | undefined,
  searchParams: { toString(): string } | null | undefined,
  hash?: string | null
): string {
  const qs = searchParams?.toString();
  const searchPart = qs ? qs : '';
  const full = composeReturnLocation(pathname, searchPart, hash ?? '');
  return buildAuthLoginHrefFromFullPath(full);
}

/** Trình duyệt hiện tại — dùng trong handler (client). */
export function getBrowserReturnLocation(): string {
  if (typeof window === 'undefined') return '/';
  return composeReturnLocation(
    window.location.pathname,
    window.location.search?.replace(/^\?/, '') ?? '',
    window.location.hash || ''
  );
}

/** Đọc ?redirect= trên URL trang đăng nhập (chỉ đường dẫn tương đối an toàn). */
export function getLoginRedirectFromUrl(): string {
  if (typeof window === 'undefined') return '/';
  const raw = new URLSearchParams(window.location.search).get('redirect');
  if (!raw) return '/';
  try {
    const decoded = decodeURIComponent(raw);
    return isSafeRelativeRedirectPath(decoded) ? decoded.slice(0, 2048) : '/';
  } catch {
    return '/';
  }
}
