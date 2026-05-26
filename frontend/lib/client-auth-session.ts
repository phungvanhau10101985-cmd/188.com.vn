import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';

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

/** Có user/token trong LS, hoặc đang hydrate — tránh redirect đăng nhập nhầm. */
export function isClientAuthLikelyLoggedIn(isAuthenticated: boolean, authLoading: boolean): boolean {
  if (isAuthenticated) return true;
  if (hasClientAuthUser()) return true;
  if (hasClientBearerToken()) return true;
  return authLoading;
}

/** Đọc user đã lưu (nếu có). */
export function readClientAuthUser<T = unknown>(): T | null {
  if (typeof window === 'undefined') return null;
  try {
    const userRaw = localStorage.getItem('user');
    if (!userRaw) return null;
    return JSON.parse(userRaw) as T;
  } catch {
    return null;
  }
}

/**
 * Khôi phục phiên từ cookie httpOnly (/auth/me) khi LS chưa có user —
 * thường gặp khi mở /cart/add từ NanoAI (full navigation) dù tab shop vẫn đăng nhập.
 */
export async function probeCookieAuthSession(): Promise<{ user: unknown } | null> {
  if (typeof window === 'undefined') return null;

  const existing = readClientAuthUser();
  if (existing) return { user: existing };

  const token = localStorage.getItem('access_token')?.trim();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...ngrokFetchHeaders(),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  try {
    const res = await fetch(`${getApiBaseUrl()}/auth/me`, {
      method: 'GET',
      credentials: 'include',
      headers,
    });
    if (!res.ok) return null;
    const user = await res.json();
    if (!user || typeof user !== 'object') return null;
    localStorage.setItem('user', JSON.stringify(user));
    return { user };
  } catch {
    return null;
  }
}
