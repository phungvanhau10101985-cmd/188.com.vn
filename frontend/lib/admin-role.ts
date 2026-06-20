/** Role JWT admin + danh sách mục (modules) — lưu khi /admin/login hoặc đổi phiên từ Cá nhân. */

import { ADMIN_MODULE_NAV, ADMIN_MODULE_ORDER, presetModuleKeysForStaffRole } from '@/lib/admin-modules';
import {
  ADMIN_NAV_GROUPS,
  getAdminNavHrefsForModuleKeys,
  getPrivilegedOnlyAdminHrefs,
} from '@/lib/admin-nav-config';

export const ADMIN_ROLE_STORAGE_KEY = 'admin_role';
export const ADMIN_MODULES_STORAGE_KEY = 'admin_modules';

/** Mục con vẫn hiện menu nếu có quyền mục cha (tương thích cấu hình cũ). */
const MODULE_PARENT_GRANT: Record<string, string[]> = {
  ems_shipping: ['orders'],
  import_1688: ['products'],
  source_stock_check: ['products'],
  taobao_cards_parse: ['products'],
};

function moduleKeyAllowed(allowed: Set<string>, moduleKey: string): boolean {
  if (allowed.has(moduleKey)) return true;
  for (const parent of MODULE_PARENT_GRANT[moduleKey] || []) {
    if (allowed.has(parent)) return true;
  }
  return false;
}

function expandGrantedModuleKeys(keys: string[]): string[] {
  const set = new Set(keys);
  for (const [child, parents] of Object.entries(MODULE_PARENT_GRANT)) {
    if (parents.some((p) => set.has(p))) set.add(child);
  }
  return [...set];
}

function adminNavPathFromHref(href: string): string {
  return href.split('#')[0]?.split('?')[0] || href;
}

function expandAdminNavPrefixes(hrefs: string[]): string[] {
  return [...new Set(hrefs.map(adminNavPathFromHref).filter(Boolean))];
}

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

/** Preset module keys theo role khi chưa có danh sách modules trong token/localStorage. */
export function adminModuleKeysForRole(role: string | null): string[] | null {
  if (!role) return null;
  const r = role.toLowerCase();
  if (r === 'super_admin' || r === 'admin') return null;
  if (r === 'order_manager') return presetModuleKeysForStaffRole('order_manager');
  if (r === 'product_manager') return presetModuleKeysForStaffRole('product_manager');
  if (r === 'content_manager') return presetModuleKeysForStaffRole('content_manager');
  return presetModuleKeysForStaffRole('order_manager');
}

export function getEffectiveNavPrefixesFor(role: string | null, modules: string[] | null): string[] | null {
  if (isPrivilegedAdminRole(role)) return null;
  const keys =
    modules && modules.length > 0 ? modules : adminModuleKeysForRole(role);
  if (!keys || keys.length === 0) return expandAdminNavPrefixes(['/admin/orders']);
  const hrefs = getAdminNavHrefsForModuleKeys(expandGrantedModuleKeys(keys));
  if (hrefs.length === 0) {
    const legacy = keys
      .map((k) => ADMIN_MODULE_NAV[k])
      .filter(Boolean);
    if (legacy.length > 0) return expandAdminNavPrefixes(legacy);
    return expandAdminNavPrefixes(['/admin/orders']);
  }
  return expandAdminNavPrefixes(hrefs);
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
    const hrefPath = href ? adminNavPathFromHref(href) : '';
    if (hrefPath && prefixes.includes(hrefPath)) return href || hrefPath;
  }
  return prefixes[0];
}

export function defaultAdminHome(): string {
  return defaultAdminHomeFromState(getStoredAdminRole(), getStoredAdminModules());
}

export function isAdminPathAllowedForState(pathname: string, role: string | null, modules: string[] | null): boolean {
  if (isPrivilegedAdminRole(role)) {
    const privilegedPaths = getPrivilegedOnlyAdminHrefs();
    if (privilegedPaths.some((h) => pathname === h || pathname.startsWith(`${h}/`))) {
      return true;
    }
  }
  const prefixes = getEffectiveNavPrefixesFor(role, modules);
  if (!prefixes) return true;
  return prefixes.some((p) => {
    const base = adminNavPathFromHref(p);
    return pathname === base || pathname.startsWith(`${base}/`);
  });
}

export function isAdminPathAllowed(pathname: string): boolean {
  return isAdminPathAllowedForState(pathname, getStoredAdminRole(), getStoredAdminModules());
}

/** Module keys được phép xem menu (sidebar) — dùng moduleKey trên từng link. */
export function getEffectiveModuleKeysForNav(role: string | null, modules: string[] | null): Set<string> | null {
  if (isPrivilegedAdminRole(role)) return null;
  const keys = modules && modules.length > 0 ? modules : adminModuleKeysForRole(role);
  return new Set(keys || []);
}

/** Lọc link sidebar theo moduleKey đã gán. */
export function isAdminNavLinkVisible(
  link: (typeof ADMIN_NAV_GROUPS)[number]['items'][number],
  role: string | null,
  modules: string[] | null,
): boolean {
  if (link.privilegedOnly) return isPrivilegedAdminRole(role);
  if (isPrivilegedAdminRole(role)) return true;
  const allowed = getEffectiveModuleKeysForNav(role, modules);
  if (!allowed) return true;
  return moduleKeyAllowed(allowed, link.moduleKey);
}
