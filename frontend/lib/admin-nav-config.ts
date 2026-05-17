/** Menu sidebar quản trị — nhóm để dễ scan trên desktop & mobile */

export type AdminNavLink = { href: string; label: string; privilegedOnly?: boolean };

export type AdminNavGroup = { title: string; items: AdminNavLink[] };

export const ADMIN_NAV_GROUPS: AdminNavGroup[] = [
  {
    title: 'Bán hàng & sản phẩm',
    items: [
      { href: '/admin/orders', label: 'Đơn hàng' },
      { href: '/admin/products', label: 'Sản phẩm' },
      { href: '/admin/products/source-stock-check', label: 'Kiểm tra nguồn hàng' },
      { href: '/admin/products/taobao-cards-parse', label: 'Parse HTML listing Taobao' },
      { href: '/admin/products#import-hibox', label: 'Import Hibox' },
      { href: '/admin/product-questions', label: 'Hỏi đáp sản phẩm' },
      { href: '/admin/product-reviews', label: 'Đánh giá sản phẩm' },
    ],
  },
  {
    title: 'Danh mục & tìm kiếm',
    items: [
      { href: '/admin/danh-muc-seo', label: 'Danh mục SEO' },
      { href: '/admin/taxonomy', label: 'Cây danh mục' },
      { href: '/admin/search-mappings', label: 'Từ khóa mapping' },
      { href: '/admin/search-cache', label: 'Cache tìm kiếm' },
    ],
  },
  {
    title: 'Khách hàng & thanh toán',
    items: [
      { href: '/admin/members', label: 'Thành viên' },
      { href: '/admin/staff-access', label: 'Quyền nhân viên', privilegedOnly: true },
      { href: '/admin/loyalty', label: 'Thành viên (điểm)' },
      { href: '/admin/bank-accounts', label: 'Nạp tiền / QR' },
    ],
  },
  {
    title: 'Website & nhúng',
    items: [
      { href: '/admin/chat-embeds', label: 'Chat & MXH' },
      { href: '/admin/shop-video-fab', label: 'Nút video' },
      { href: '/admin/embed-codes', label: 'Mã nhúng analytics' },
      { href: '/admin/bunny-cdn', label: 'Ảnh Bunny CDN' },
      { href: '/admin/api-keys', label: 'API & tích hợp', privilegedOnly: true },
    ],
  },
  {
    title: 'Khác',
    items: [{ href: '/admin/notifications', label: 'Thông báo' }],
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
