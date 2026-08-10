'use client';

/**
 * Danh mục khách chưa đăng nhập từng bấm chọn ở khối «CÓ THỂ BẠN THÍCH» (khi chưa có tín
 * hiệu gì — chưa xem sản phẩm nào). Lưu localStorage (gắn theo trình duyệt, cùng vòng đời
 * với `188_guest_browser_id`) — KHÔNG gửi lên server, chỉ dùng để lần sau ghé lại (vẫn chưa
 * có lượt xem, chưa đăng nhập) tự chuyển thẳng đến trang danh mục đó.
 */
const STORAGE_KEY = '188_guest_category_interest';

export type GuestCategoryInterest = {
  path: string;
  name: string;
  savedAt: number;
};

export function getGuestCategoryInterest(): GuestCategoryInterest | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<GuestCategoryInterest>;
    if (!parsed?.path || typeof parsed.path !== 'string') return null;
    return {
      path: parsed.path,
      name: parsed.name || '',
      savedAt: typeof parsed.savedAt === 'number' ? parsed.savedAt : 0,
    };
  } catch {
    return null;
  }
}

export function setGuestCategoryInterest(path: string, name: string): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ path, name, savedAt: Date.now() })
    );
  } catch {
    /* ignore */
  }
}

export function clearGuestCategoryInterest(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
