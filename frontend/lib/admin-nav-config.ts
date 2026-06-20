/** Menu sidebar quản trị — nhóm + khóa quyền (moduleKey) đồng bộ backend ALLOWED_MODULE_KEYS. */

export type AdminNavLink = {
  href: string;
  label: string;
  moduleKey: string;
  /** Chỉ super_admin / admin — không gán qua granular NV. */
  privilegedOnly?: boolean;
};

export type AdminNavGroup = { title: string; items: AdminNavLink[] };

/** Mục không có trong sidebar nhưng vẫn gán quyền được (vd. sale trong Khuyến mãi). */
export type AdminNavExtraModule = { moduleKey: string; label: string; href: string };

export const ADMIN_NAV_GROUPS: AdminNavGroup[] = [
  {
    title: 'Bán hàng & sản phẩm',
    items: [
      { href: '/admin/orders', label: 'Đơn hàng', moduleKey: 'orders' },
      { href: '/admin/orders/shipping', label: 'Vận chuyển EMS', moduleKey: 'ems_shipping' },
      { href: '/admin/products', label: 'Sản phẩm', moduleKey: 'products' },
      { href: '/admin/test', label: 'Test & thử nghiệm', moduleKey: 'admin_test', privilegedOnly: true },
      { href: '/admin/products/source-stock-check', label: 'Kiểm tra nguồn hàng', moduleKey: 'source_stock_check' },
      { href: '/admin/products/taobao-cards-parse', label: 'Parse HTML listing Taobao', moduleKey: 'taobao_cards_parse' },
      { href: '/admin/products#import-hibox', label: 'Import Hibox', moduleKey: 'import_1688' },
      { href: '/admin/product-questions', label: 'Hỏi đáp sản phẩm', moduleKey: 'product_questions' },
      { href: '/admin/product-reviews', label: 'Đánh giá sản phẩm', moduleKey: 'product_reviews' },
    ],
  },
  {
    title: 'Danh mục & tìm kiếm',
    items: [
      { href: '/admin/danh-muc-seo', label: 'Danh mục SEO', moduleKey: 'category_seo' },
      { href: '/admin/taxonomy', label: 'Cây danh mục', moduleKey: 'taxonomy' },
      { href: '/admin/search-mappings', label: 'Từ khóa mapping', moduleKey: 'search_mappings' },
      { href: '/admin/search-cache', label: 'Cache tìm kiếm', moduleKey: 'search_cache' },
      { href: '/admin/listing-facet-cache', label: 'Cache bộ lọc', moduleKey: 'listing_facet_cache' },
    ],
  },
  {
    title: 'Khách hàng & thanh toán',
    items: [
      { href: '/admin/members', label: 'Thành viên', moduleKey: 'members' },
      { href: '/admin/staff-access', label: 'Quyền nhân viên', moduleKey: 'staff_access', privilegedOnly: true },
      { href: '/admin/loyalty', label: 'Thành viên (điểm)', moduleKey: 'loyalty' },
      { href: '/admin/promotions', label: 'Khuyến mãi', moduleKey: 'promotions' },
      { href: '/admin/affiliate', label: 'Affiliate & ví', moduleKey: 'affiliate' },
      { href: '/admin/bank-accounts', label: 'Nạp tiền / QR', moduleKey: 'bank_accounts' },
    ],
  },
  {
    title: 'Website & nhúng',
    items: [
      { href: '/admin/chat-embeds', label: 'Chat & MXH', moduleKey: 'chat_embeds' },
      { href: '/admin/shop-video-fab', label: 'Nút video', moduleKey: 'shop_video_fab' },
      { href: '/admin/embed-codes', label: 'Mã nhúng analytics', moduleKey: 'embed_codes' },
      { href: '/admin/bunny-cdn', label: 'Ảnh Bunny CDN', moduleKey: 'bunny_cdn' },
      { href: '/admin/api-keys', label: 'API & tích hợp', moduleKey: 'api_keys', privilegedOnly: true },
      { href: '/admin/vps-backup', label: 'Backup VPS', moduleKey: 'vps_backup', privilegedOnly: true },
    ],
  },
  {
    title: 'Khác',
    items: [
      { href: '/admin/notifications', label: 'Thông báo', moduleKey: 'notifications' },
      { href: '/admin/newsletter', label: 'Quản lý gửi email', moduleKey: 'newsletter' },
    ],
  },
];

export const ADMIN_NAV_EXTRA_MODULES: AdminNavExtraModule[] = [
  {
    moduleKey: 'sale_calendar',
    label: 'Sale ngày trùng tháng',
    href: '/admin/promotions#site-sale',
  },
];

/** href thật (bỏ hash/query) của các mục privilegedOnly — dùng kiểm tra quyền vào trang */
export function getPrivilegedOnlyAdminHrefs(): string[] {
  const out: string[] = [];
  for (const g of ADMIN_NAV_GROUPS) {
    for (const it of g.items) {
      if (!it.privilegedOnly) continue;
      out.push(it.href.split('#')[0]?.split('?')[0] || it.href);
    }
  }
  return [...new Set(out)];
}

/** Nhóm checkbox gán quyền NV — khớp sidebar. */
export function getAdminStaffModulePickerGroups(): { title: string; moduleKeys: string[] }[] {
  const groups = ADMIN_NAV_GROUPS.map((g) => ({
    title: g.title,
    moduleKeys: g.items
      .filter((it) => !it.privilegedOnly && it.moduleKey !== 'staff_access')
      .map((it) => it.moduleKey),
  })).filter((g) => g.moduleKeys.length > 0);
  const extraKeys = ADMIN_NAV_EXTRA_MODULES.map((m) => m.moduleKey);
  if (extraKeys.length > 0) {
    groups.push({ title: 'Khuyến mãi (mục phụ)', moduleKeys: extraKeys });
  }
  return groups;
}

export function getAdminNavHrefsForModuleKeys(moduleKeys: string[]): string[] {
  const allowed = new Set(moduleKeys);
  const hrefs: string[] = [];
  for (const g of ADMIN_NAV_GROUPS) {
    for (const it of g.items) {
      if (allowed.has(it.moduleKey)) hrefs.push(it.href);
    }
  }
  for (const extra of ADMIN_NAV_EXTRA_MODULES) {
    if (allowed.has(extra.moduleKey)) hrefs.push(extra.href);
  }
  return [...new Set(hrefs)];
}
