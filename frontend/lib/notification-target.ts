/** Đường dẫn nội bộ khi khách bấm một thông báo. */

export function safeNotificationPath(raw: string | null | undefined): string | null {
  if (!raw || typeof raw !== 'string') return null;
  const value = raw.trim();
  if (!value) return null;

  if (value.startsWith('/') && !value.startsWith('//') && !value.includes('\\') && !/\s/.test(value)) {
    return inboxPath(value);
  }

  if (typeof window === 'undefined') return null;
  try {
    const url = new URL(value);
    if (url.origin !== window.location.origin) return null;
    return inboxPath(`${url.pathname}${url.search}${url.hash}`);
  } catch {
    return null;
  }
}

function inboxPath(path: string): string | null {
  const bare = path.split('?')[0].replace(/\/$/, '') || '/';
  if (bare === '/account/notifications') return null;
  return path;
}

export function notificationActionLabel(path: string): string {
  const bare = path.split('?')[0];
  if (bare === '/cart') return 'Mở giỏ hàng';
  if (bare.startsWith('/account/khuyen-mai')) return 'Xem khuyến mãi';
  if (bare.includes('/review')) return 'Đánh giá đơn';
  if (bare.includes('/tracking')) return 'Xem vận chuyển';
  if (bare.startsWith('/account/orders/')) return 'Xem đơn hàng';
  if (bare.startsWith('/vi-dien-tu')) return 'Xem ví';
  return 'Xem chi tiết';
}
