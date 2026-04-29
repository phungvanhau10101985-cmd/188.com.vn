'use client';

/**
 * Định danh phiên trình duyệt (analytics + header X-Guest-Session-Id cho khách).
 * Giữ cố định cho đến khi xóa dữ liệu trình duyệt — không đổi ID sau vài phút nghỉ
 * (tránh mất lịch sử xem / thích / gợi ý cùng shop).
 *
 * Migration từ khóa cũ `analytics_session` (TTL 30 phút).
 */
const STORAGE_KEY = '188_guest_browser_id';
const LEGACY_KEY = 'analytics_session';

function generateId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function getGuestSessionId(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const p = JSON.parse(raw) as { id?: string };
      if (p?.id && typeof p.id === 'string') {
        return p.id;
      }
    }
    const legacy = localStorage.getItem(LEGACY_KEY);
    if (legacy) {
      try {
        const p = JSON.parse(legacy) as { id?: string };
        if (p?.id && typeof p.id === 'string') {
          localStorage.setItem(STORAGE_KEY, JSON.stringify({ id: p.id }));
          return p.id;
        }
      } catch {
        /* ignore */
      }
    }
  } catch {
    /* ignore */
  }
  const id = generateId();
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ id }));
  } catch {
    /* ignore */
  }
  return id;
}
