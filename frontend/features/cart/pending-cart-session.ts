import type { AddToCartRequest } from '@/features/cart/types/cart';

const STORAGE_KEY = '188_pending_cart_after_login';

function sameLine(a: AddToCartRequest, b: AddToCartRequest): boolean {
  return (
    a.product_id === b.product_id &&
    (a.selected_size ?? '') === (b.selected_size ?? '') &&
    (a.selected_color ?? '') === (b.selected_color ?? '')
  );
}

/** Gộp vào phiên — sau đăng nhập sẽ đưa vào giỏ server rồi mở /cart. */
export function queuePendingCartAfterLogin(item: AddToCartRequest): void {
  if (typeof window === 'undefined') return;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    const prev: AddToCartRequest[] = raw ? JSON.parse(raw) : [];
    const list = Array.isArray(prev) ? prev.map((x) => ({ ...x })) : [];
    const idx = list.findIndex((x) => sameLine(x, item));
    if (idx >= 0) {
      list[idx] = { ...list[idx], quantity: list[idx].quantity + item.quantity };
    } else {
      list.push({ ...item });
    }
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  } catch {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify([{ ...item }]));
    } catch {
      /* noop */
    }
  }
}

/** Đọc (không xóa) — dùng trước khi đồng bộ; gọi clear sau khi thành công. */
export function readPendingCartAfterLogin(): AddToCartRequest[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.map((x: AddToCartRequest) => ({ ...x })) : [];
  } catch {
    return [];
  }
}

export function clearPendingCartAfterLogin(): void {
  if (typeof window === 'undefined') return;
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* noop */
  }
}

/** Đọc và xóa — chỉ dùng khi chắc chắn không cần retry (hiếm). */
export function consumePendingCartAfterLogin(): AddToCartRequest[] {
  const items = readPendingCartAfterLogin();
  clearPendingCartAfterLogin();
  return items;
}
