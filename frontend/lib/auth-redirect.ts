/** Đọc ?redirect= từ URL trang đăng nhập (chỉ đường dẫn tương đối an toàn). */
export function getLoginRedirectFromUrl(): string {
  if (typeof window === 'undefined') return '/';
  const r = new URLSearchParams(window.location.search).get('redirect');
  if (r && r.startsWith('/') && !r.startsWith('//')) return r.slice(0, 512);
  return '/';
}
