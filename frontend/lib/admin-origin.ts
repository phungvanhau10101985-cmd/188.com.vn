/**
 * Admin host DNS-only (bypass Cloudflare). Khi mở quản trị từ 188.com.vn
 * cần handoff token qua hash — localStorage không chia sẻ giữa hai origin.
 */

export function getAdminOrigin(): string {
  const fromEnv = (process.env.NEXT_PUBLIC_ADMIN_ORIGIN || '').trim().replace(/\/$/, '');
  if (typeof window !== 'undefined') {
    const host = window.location.hostname.toLowerCase();
    if (host === 'localhost' || host === '127.0.0.1') {
      return window.location.origin;
    }
    if (host === 'admin.188.com.vn') {
      return window.location.origin;
    }
  }
  return fromEnv || 'https://admin.188.com.vn';
}

/** Đang ở shop apex/www → cần chuyển sang admin host kèm token. */
export function shouldHandoffAdminSession(): boolean {
  if (typeof window === 'undefined') return false;
  const host = window.location.hostname.toLowerCase();
  if (host === 'localhost' || host === '127.0.0.1') return false;
  if (host === 'admin.188.com.vn') return false;
  return true;
}

export function buildAdminSessionHandoffUrl(data: {
  access_token: string;
  role?: string | null;
  modules?: string[] | null;
  next?: string;
}): string {
  const params = new URLSearchParams();
  params.set('access_token', data.access_token);
  if (data.role) params.set('role', data.role);
  if (data.modules != null) params.set('modules', JSON.stringify(data.modules));
  const next = (data.next || '/admin').trim() || '/admin';
  params.set('next', next.startsWith('/') ? next : `/${next}`);
  return `${getAdminOrigin()}/admin/auth/handoff#${params.toString()}`;
}
