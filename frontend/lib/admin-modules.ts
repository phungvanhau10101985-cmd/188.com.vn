/**
 * Khóa mục quyền admin — đồng bộ với backend app/core/admin_permissions.py ALLOWED_MODULE_KEYS
 * và frontend/lib/admin-nav-config.ts (sidebar).
 */
import {
  ADMIN_NAV_EXTRA_MODULES,
  ADMIN_NAV_GROUPS,
  getAdminNavHrefsForModuleKeys,
} from '@/lib/admin-nav-config';

function buildModuleCatalog() {
  const labels: Record<string, string> = {};
  const order: string[] = [];
  const nav: Record<string, string> = {};

  for (const g of ADMIN_NAV_GROUPS) {
    for (const it of g.items) {
      if (!order.includes(it.moduleKey)) order.push(it.moduleKey);
      labels[it.moduleKey] = it.label;
      nav[it.moduleKey] = it.href;
    }
  }
  for (const extra of ADMIN_NAV_EXTRA_MODULES) {
    if (!order.includes(extra.moduleKey)) order.push(extra.moduleKey);
    labels[extra.moduleKey] = extra.label;
    nav[extra.moduleKey] = extra.href;
  }

  return { labels, order, nav };
}

function isPrivilegedOnlyModuleKey(moduleKey: string): boolean {
  for (const g of ADMIN_NAV_GROUPS) {
    for (const it of g.items) {
      if (it.moduleKey === moduleKey && it.privilegedOnly) return true;
    }
  }
  return false;
}

const catalog = buildModuleCatalog();

export const ADMIN_MODULE_NAV: Record<string, string> = catalog.nav;

/** Thứ tự checkbox + ưu tiên trang mặc định sau đăng nhập. */
export const ADMIN_MODULE_ORDER: string[] = catalog.order;

/** Checkbox gán quyền NV — loại trừ staff_access và mục privilegedOnly. */
export const ADMIN_MODULE_KEYS_ASSIGNABLE = ADMIN_MODULE_ORDER.filter(
  (k) => k !== 'staff_access' && !isPrivilegedOnlyModuleKey(k),
);

export const ADMIN_MODULE_LABELS: Record<string, string> = catalog.labels;

export { getAdminNavHrefsForModuleKeys };

/** Preset khi gán NV theo vai trò (null = không áp dụng). */
export function presetModuleKeysForStaffRole(
  staffRole: 'none' | 'order_manager' | 'admin' | 'product_manager' | 'content_manager',
): string[] {
  switch (staffRole) {
    case 'order_manager':
      return ['orders', 'ems_shipping'];
    case 'product_manager':
      return [
        'products',
        'import_1688',
        'source_stock_check',
        'taobao_cards_parse',
        'taxonomy',
        'search_mappings',
        'search_cache',
        'listing_facet_cache',
        'category_seo',
        'bunny_cdn',
      ];
    case 'content_manager':
      return ['product_questions', 'product_reviews', 'category_seo', 'embed_codes', 'chat_embeds'];
    case 'admin':
    case 'none':
    default:
      return [];
  }
}
