/**
 * Base URL gọi API (/api/v1, không có slash cuối).
 *
 * - Trang HTTPS (ngrok, production) không dùng `http://localhost` từ env — trình duyệt chặn
 *   (mixed content) → "Failed to fetch". Khi đó dùng cùng host + `/api/v1` (Next rewrite → FastAPI).
 * - HTTP dev (mặc định): gọi cùng host Next `/api/v1` → app router proxy sang FastAPI. Trình duyệt không đụng `:8001` trực tiếp.
 * - Gọi thẳng FastAPI từ trình duyệt: NEXT_PUBLIC_API_NEXT_PROXY=0 (và có thể NEXT_PUBLIC_API_BASE_URL=http://localhost:8001/api/v1).
 * - STATIC / file backend trên dev khi đang proxy: NEXT_PUBLIC_FASTAPI_ORIGIN (mặc định logic dùng 127.0.0.1:8001 chỉ trong development).
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

  if (typeof window !== 'undefined') {
    const httpsPage = window.location.protocol === 'https:';
    // Trang HTTPS: luôn gọi API qua reverse proxy trên cùng host (/api/) — tránh rơi vào localhost khi NEXT_PUBLIC không khớp hoặc proxyOff=1
    if (httpsPage) {
      return `${window.location.origin}/api/v1`;
    }
    // HTTP: mặc định cùng origin /api/v1 (Next proxy). Chỉ gọi thẳng :8001 khi NEXT_PUBLIC_API_NEXT_PROXY=0.
    if (!proxyOff) {
      return `${window.location.origin}/api/v1`;
    }
    return 'http://localhost:8001/api/v1';
  }

  if (!proxyOff) {
    const internal = (process.env.API_INTERNAL_ORIGIN || 'http://127.0.0.1:8001').replace(/\/$/, '');
    return `${internal}/api/v1`;
  }
  return 'http://127.0.0.1:8001/api/v1';
}

/**
 * Origin của FastAPI (không có /api/v1) để ghép `/static/templates/...`.
 * Khi `getApiBaseUrl()` là URL tuyệt đối (http://localhost:8001/api/v1) → origin đúng cổng backend.
 */
export function getBackendOriginUrl(): string {
  if (typeof window === 'undefined') {
    return '';
  }
  try {
    const api = getApiBaseUrl();
    if (api.startsWith('http://') || api.startsWith('https://')) {
      const u = new URL(api);
      const pathNorm = u.pathname.replace(/\/$/, '');
      const proxiedViaNext =
        u.origin === window.location.origin &&
        (pathNorm === '/api/v1' || pathNorm.endsWith('/api/v1'));
      // API qua Next nhưng /static vẫn do FastAPI phục vụ — trình duyệt cần origin backend (chỉ dev mặc định 8001).
      if (proxiedViaNext) {
        if (process.env.NODE_ENV === 'development') {
          const o = (process.env.NEXT_PUBLIC_FASTAPI_ORIGIN || '').trim().replace(/\/$/, '');
          return o || 'http://127.0.0.1:8001';
        }
        return window.location.origin;
      }
      return u.origin;
    }
  } catch {
    /* fall through */
  }
  return window.location.origin;
}

/**
 * Base `/api/v1` để dán vào Google Merchant Center / Meta / TikTok — phải là URL **công khai**
 * (HTTPS, truy cập được từ Internet). `localhost` không dùng được cho scheduled fetch của họ.
 *
 * Thứ tự: `NEXT_PUBLIC_CATALOG_FEED_API_BASE_URL` → `NEXT_PUBLIC_SITE_URL` / `NEXT_PUBLIC_DOMAIN` + `/api/v1`
 * → `NEXT_PUBLIC_API_BASE_URL` (cùng kết quả trên server và client — tránh lệch hydrate với `window.origin`).
 */
export function getCatalogFeedApiBaseUrl(): string {
  const explicit = (process.env.NEXT_PUBLIC_CATALOG_FEED_API_BASE_URL || '').trim();
  if (explicit) {
    return stripTrailingSlash(explicit);
  }
  const site = (process.env.NEXT_PUBLIC_SITE_URL || process.env.NEXT_PUBLIC_DOMAIN || '').trim();
  if (site) {
    return `${stripTrailingSlash(site)}/api/v1`;
  }
  return stripTrailingSlash(process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8001/api/v1');
}

/** True nếu URL feed rõ ràng không thể truy cập từ server của Google/Meta/TikTok. */
export function isNonPublicCatalogFeedBase(url: string): boolean {
  try {
    const u = new URL(url);
    return u.hostname === 'localhost' || u.hostname === '127.0.0.1';
  } catch {
    return false;
  }
}

/** Tránh trang cảnh báo ngrok chặn một số request (tuỳ phiên bản). */
export function ngrokFetchHeaders(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  const h = window.location.hostname;
  if (!h.includes('ngrok')) return {};
  return { 'ngrok-skip-browser-warning': 'true' };
}
