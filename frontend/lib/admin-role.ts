/** Role JWT admin + danh sách mục (modules) — lưu khi /admin/login hoặc đổi phiên từ Cá nhân. */

import {
  ADMIN_MODULE_NAV,
  ADMIN_MODULE_ORDER,
} from '@/lib/admin-modules';

export const ADMIN_ROLE_STORAGE_KEY = 'admin_role';
export const ADMIN_MODULES_STORAGE_KEY = 'admin_modules';

export function getStoredAdminRole(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(ADMIN_ROLE_STORAGE_KEY);
}

export function setStoredAdminRole(role: string | null) {
  if (typeof window === 'undefined') return;
  if (role) localStorage.setItem(ADMIN_ROLE_STORAGE_KEY, role);
  else localStorage.removeItem(ADMIN_ROLE_STORAGE_KEY);
}

/** Danh sách khóa mục từ token (JSON array). null = chưa lưu / phiên cũ. */
export function getStoredAdminModules(): string[] | null {
  if (typeof window === 'undefined') return null;
  const raw = localStorage.getItem(ADMIN_MODULES_STORAGE_KEY);
  if (!raw || !raw.trim()) return null;
  try {
    const arr = JSON.parse(raw) as unknown;
    if (!Array.isArray(arr)) return null;
    return arr.map((x) => String(x).trim()).filter(Boolean);
  } catch {
    return null;
  }
}

export function setStoredAdminModules(modules: string[] | null | undefined) {
  if (typeof window === 'undefined') return;
  if (modules && modules.length > 0) {
    localStorage.setItem(ADMIN_MODULES_STORAGE_KEY, JSON.stringify(modules));
  } else {
    localStorage.removeItem(ADMIN_MODULES_STORAGE_KEY);
  }
}

/** Quản trị chính — được gán quyền quản trị web cho thành viên & toàn trang nhạy cảm. */
export function isPrivilegedAdminRole(role: string | null | undefined): boolean {
  const r = (role || '').toLowerCase();
  return r === 'super_admin' || r === 'admin';
}

/**
 * Danh sách href được phép (sidebar) chỉ theo role — preset cũ.
 * null = toàn bộ (super/admin).
 */
export function adminNavPrefixesForRole(role: string | null): string[] | null {
  if (!role) return null;
  const r = role.toLowerCase();
  if (r === 'super_admin' || r === 'admin') return null;
  if (r === 'order_manager') return ['/admin/orders'];
  if (r === 'product_manager')
    return [
      '/admin/products',
      '/admin/taxonomy',
      '/admin/search-mappings',
      '/admin/search-cache',
      '/admin/danh-muc-seo',
      '/admin/bunny-cdn',
    ];
  if (r === 'content_manager')
    return [
      '/admin/product-questions',
      '/admin/product-reviews',
      '/admin/danh-muc-seo',
      '/admin/embed-codes',
      '/admin/chat-embeds',
    ];
  return ['/admin/orders'];
}

export function getEffectiveNavPrefixesFor(role: string | null, modules: string[] | null): string[] | null {
  if (modules && modules.length > 0) {
    const hrefs = [...new Set(modules.map((k) => ADMIN_MODULE_NAV[k]).filter(Boolean))];
    if (hrefs.length > 0) return hrefs;
  }
  return adminNavPrefixesForRole(role);
}

/** href được phép: ưu tiên modules lưu trong localStorage, không có thì theo role. */
export function getEffectiveNavPrefixesFromStorage(): string[] | null {
  return getEffectiveNavPrefixesFor(getStoredAdminRole(), getStoredAdminModules());
}

/** Trang admin đầu tiên sau đăng nhập — đọc role + modules đã lưu. */
export function defaultAdminHomeFromState(role: string | null, modules: string[] | null): string {
  const prefixes = getEffectiveNavPrefixesFor(role, modules);
  if (!prefixes) return '/admin/orders';
  for (const key of ADMIN_MODULE_ORDER) {
    const href = ADMIN_MODULE_NAV[key];
    if (href && prefixes.includes(href)) return href;
  }
  return prefixes[0];
}

export function defaultAdminHome(): string {
  return defaultAdminHomeFromState(getStoredAdminRole(), getStoredAdminModules());
}

export function isAdminPathAllowedForState(pathname: string, role: string | null, modules: string[] | null): boolean {
  const prefixes = getEffectiveNavPrefixesFor(role, modules);
  if (!prefixes) return true;
  return prefixes.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export function isAdminPathAllowed(pathname: string): boolean {
  return isAdminPathAllowedForState(pathname, getStoredAdminRole(), getStoredAdminModules());
}
