/** Menu sidebar quản trị — nhóm để dễ scan trên desktop & mobile */

export type AdminNavLink = { href: string; label: string; privilegedOnly?: boolean };

export type AdminNavGroup = { title: string; items: AdminNavLink[] };

export const ADMIN_NAV_GROUPS: AdminNavGroup[] = [
  {
    title: 'Bán hàng & sản phẩm',
    items: [
      { href: '/admin/orders', label: 'Đơn hàng' },
      { href: '/admin/products', label: 'Sản phẩm' },
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
    ],
  },
  {
    title: 'Khác',
    items: [{ href: '/admin/notifications', label: 'Thông báo' }],
  },
];
