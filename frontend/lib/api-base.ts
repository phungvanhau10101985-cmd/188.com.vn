/**
 * Base URL gọi API (/api/v1, không có slash cuối).
 *
 * - Trang HTTPS (ngrok, production) không dùng `http://localhost` từ env — trình duyệt chặn
 *   (mixed content) → "Failed to fetch". Khi đó dùng cùng host + `/api/v1` (Next rewrite → FastAPI).
 * - `next dev` + HTTP localhost: cùng origin `/api/v1` hoặc fallback localhost:8000.
 * - Tắt rewrite: NEXT_PUBLIC_API_NEXT_PROXY=0; nếu gọi thẳng API, NEXT_PUBLIC_API_BASE_URL phải là HTTPS công khai.
 */
function stripTrailingSlash(url: string): string {
  return url.replace(/\/$/, '');
}

/** http://localhost hoặc http://127.0.0.1 — không dùng được trên trang HTTPS. */
function isInsecureLocalhostUrl(url: string): boolean {
  try {
    const u = new URL(url);
    if (u.protocol !== 'http:') return false;
    return u.hostname === 'localhost' || u.hostname === '127.0.0.1';
  } catch {
    return false;
  }
}

export function getApiBaseUrl(): string {
  let custom = (process.env.NEXT_PUBLIC_API_BASE_URL || '').trim();
  if (custom && typeof window !== 'undefined') {
    if (window.location.protocol === 'https:' && isInsecureLocalhostUrl(custom)) {
      custom = '';
    }
  }
  if (custom) {
    return stripTrailingSlash(custom);
  }

  const proxyOff = process.env.NEXT_PUBLIC_API_NEXT_PROXY === '0';
  const useSameOriginByEnv =
    !proxyOff &&
    (process.env.NODE_ENV === 'development' || process.env.NEXT_PUBLIC_API_NEXT_PROXY === '1');

  if (typeof window !== 'undefined') {
    const httpsPage = window.location.protocol === 'https:';
    if (!proxyOff && (useSameOriginByEnv || httpsPage)) {
      return `${window.location.origin}/api/v1`;
    }
    return 'http://localhost:8000/api/v1';
  }

  if (!proxyOff && process.env.NEXT_PUBLIC_API_NEXT_PROXY === '1') {
    const internal = (process.env.API_INTERNAL_ORIGIN || 'http://127.0.0.1:8000').replace(/\/$/, '');
    return `${internal}/api/v1`;
  }
  return 'http://127.0.0.1:8000/api/v1';
}

/** Tránh trang cảnh báo ngrok chặn một số request (tuỳ phiên bản). */
export function ngrokFetchHeaders(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  const h = window.location.hostname;
  if (!h.includes('ngrok')) return {};
  return { 'ngrok-skip-browser-warning': 'true' };
}
