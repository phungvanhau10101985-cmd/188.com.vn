/**
 * Khóa mục quyền admin — đồng bộ với backend app/core/admin_permissions.py ALLOWED_MODULE_KEYS.
 */

export const ADMIN_MODULE_NAV: Record<string, string> = {
  orders: '/admin/orders',
  products: '/admin/products',
  taxonomy: '/admin/taxonomy',
  search_mappings: '/admin/search-mappings',
  search_cache: '/admin/search-cache',
  category_seo: '/admin/danh-muc-seo',
  bunny_cdn: '/admin/bunny-cdn',
  product_questions: '/admin/product-questions',
  product_reviews: '/admin/product-reviews',
  members: '/admin/members',
  bank_accounts: '/admin/bank-accounts',
  loyalty: '/admin/loyalty',
  embed_codes: '/admin/embed-codes',
  chat_embeds: '/admin/chat-embeds',
  shop_video_fab: '/admin/shop-video-fab',
  notifications: '/admin/notifications',
  staff_access: '/admin/staff-access',
};

/** Thứ tự checkbox + ưu tiên trang mặc định sau đăng nhập. */
export const ADMIN_MODULE_ORDER: string[] = [
  'orders',
  'products',
  'taxonomy',
  'search_mappings',
  'search_cache',
  'category_seo',
  'bunny_cdn',
  'product_questions',
  'product_reviews',
  'members',
  'bank_accounts',
  'loyalty',
  'embed_codes',
  'chat_embeds',
  'shop_video_fab',
  'notifications',
  'staff_access',
];

/** Checkbox gán quyền NV — không gán « Quản lý quyền nhân viên » qua granular. */
export const ADMIN_MODULE_KEYS_ASSIGNABLE = ADMIN_MODULE_ORDER.filter((k) => k !== 'staff_access');

export const ADMIN_MODULE_LABELS: Record<string, string> = {
  orders: 'Đơn hàng',
  products: 'Sản phẩm',
  taxonomy: 'Cây danh mục',
  search_mappings: 'Từ khóa mapping',
  search_cache: 'Cache & thống kê tìm kiếm',
  category_seo: 'Tổng hợp danh mục SEO',
  bunny_cdn: 'Đăng ảnh Bunny CDN',
  product_questions: 'Câu hỏi / trả lời SP',
  product_reviews: 'Đánh giá sản phẩm',
  members: 'Thành viên',
  bank_accounts: 'Cấu hình nạp tiền',
  loyalty: 'Cấu hình thành viên',
  embed_codes: 'Mã nhúng (GA, FB…)',
  chat_embeds: 'Nhúng chat',
  shop_video_fab: 'Nút lướt video',
  notifications: 'Thông báo',
  staff_access: 'Quản lý quyền nhân viên',
};

/** Preset khi gán NV theo vai trò (null = không áp dụng). */
export function presetModuleKeysForStaffRole(
  staffRole: 'none' | 'order_manager' | 'admin' | 'product_manager' | 'content_manager',
): string[] {
  switch (staffRole) {
    case 'order_manager':
      return ['orders'];
    case 'product_manager':
      return ['products', 'taxonomy', 'search_mappings', 'search_cache', 'category_seo', 'bunny_cdn'];
    case 'content_manager':
      return ['product_questions', 'product_reviews', 'category_seo', 'embed_codes', 'chat_embeds'];
    case 'admin':
    case 'none':
    default:
      return [];
  }
}
