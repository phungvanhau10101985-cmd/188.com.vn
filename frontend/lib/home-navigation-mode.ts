'use client';

/** PDP → trang chủ: bắt buộc tính gợi ý tươi, không đọc snapshot. */
const FRESH_KEY = '188_home_recommendation_fresh';

export function markHomeRecommendationFresh(): void {
  if (typeof window === 'undefined') return;
  try {
    sessionStorage.setItem(FRESH_KEY, '1');
  } catch {
    /* ignore */
  }
}

export function consumeHomeRecommendationFresh(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const fresh = sessionStorage.getItem(FRESH_KEY) === '1';
    sessionStorage.removeItem(FRESH_KEY);
    return fresh;
  } catch {
    return false;
  }
}

export function trackPathForHomeRecommendationFresh(
  pathname: string,
  prevPathname: string | null | undefined
): void {
  const prev = (prevPathname ?? '').replace(/\/$/, '') || '/';
  const now = (pathname ?? '').replace(/\/$/, '') || '/';
  if (now === '/' && /^\/products\/[^/]+$/.test(prev)) {
    markHomeRecommendationFresh();
  }
}
