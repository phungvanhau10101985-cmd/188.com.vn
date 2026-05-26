/** Đọc phiên đăng nhập lưu trên client (đồng bộ, không phụ thuộc hydrate React). */
export function hasClientAuthUser(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const userRaw = localStorage.getItem('user');
    if (!userRaw) return false;
    JSON.parse(userRaw);
    return true;
  } catch {
    return false;
  }
}

export function hasClientBearerToken(): boolean {
  if (typeof window === 'undefined') return false;
  return Boolean(localStorage.getItem('access_token')?.trim());
}

/** Có user trong LS hoặc đang hydrate — tránh redirect đăng nhập nhầm trên /cart/add. */
export function isClientAuthLikelyLoggedIn(isAuthenticated: boolean, authLoading: boolean): boolean {
  if (isAuthenticated) return true;
  if (hasClientAuthUser()) return true;
  return authLoading && hasClientBearerToken();
}
