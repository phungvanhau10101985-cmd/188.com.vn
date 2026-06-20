/** Thông báo toàn site khi API trả 429 (mở quá nhiều trang / request quá nhanh). */

export const RATE_LIMIT_EVENT = '188:rate-limit';

export type RateLimitEventDetail = {
  seconds: number;
};

export function isCustomerRateLimitMessage(message: string): boolean {
  const m = (message || '').toLowerCase();
  return m.includes('thao tác quá nhanh') || m.includes('đang thao tác quá nhanh');
}

export function parseRetryAfterSecondsFromDetail(detail: string): number | null {
  const m = (detail || '').match(/(?:thử lại sau|retry(?:\s+\w+)*\s+after|chờ)\s*(\d+)\s*giây/i);
  if (!m) return null;
  const n = Number.parseInt(m[1], 10);
  return Number.isFinite(n) && n > 0 ? n : null;
}

export function extractRateLimitSeconds(
  status: number,
  detail: string,
  retryAfterHeader: string | null,
  body?: { retry_after_seconds?: unknown } | null,
): number | null {
  if (status !== 429) return null;

  const fromBody = body?.retry_after_seconds;
  if (typeof fromBody === 'number' && Number.isFinite(fromBody) && fromBody > 0) {
    return Math.floor(fromBody);
  }

  if (retryAfterHeader) {
    const n = Number(retryAfterHeader);
    if (Number.isFinite(n) && n > 0) return Math.floor(n);
  }

  const fromDetail = parseRetryAfterSecondsFromDetail(detail);
  if (fromDetail != null) return fromDetail;

  if (isCustomerRateLimitMessage(detail)) return 60;

  return null;
}

export function notifyRateLimitCooldown(seconds: number): void {
  if (typeof window === 'undefined') return;
  const sec = Math.max(1, Math.min(120, Math.floor(seconds)));
  window.dispatchEvent(
    new CustomEvent<RateLimitEventDetail>(RATE_LIMIT_EVENT, { detail: { seconds: sec } }),
  );
}

export function maybeNotifyRateLimitFromResponse(
  status: number,
  detail: string,
  retryAfterHeader: string | null,
  body?: Record<string, unknown> | null,
): void {
  const sec = extractRateLimitSeconds(status, detail, retryAfterHeader, body);
  if (sec != null) notifyRateLimitCooldown(sec);
}
