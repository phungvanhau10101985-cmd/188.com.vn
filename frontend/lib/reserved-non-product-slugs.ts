/**
 * Slug một segment không phải URL sản phẩm (bot, scanner, file tĩnh cũ).
 * Trả 404 sớm — tránh SSR gọi 4–5 API backend (by-slug, group-listing-path…).
 *
 * Nguồn thực tế trên VPS: get-token-auth-phone, pwasw.js, login, meta.json…
 */
const EXACT_BLOCKED = new Set(
  [
    'get-token-auth-phone',
    'login',
    'register',
    'dang-ky',
    'dang-nhap',
    'dangky',
    'dangnhap',
    'auth',
    'account',
    'cart',
    'favorites',
    'admin',
    'wp-login.php',
    'wp-admin',
    'xmlrpc.php',
    'meta.json',
    'pwasw.js',
    'service-worker.js',
    'sw.js',
    'manifest.json',
    'apple-app-site-association',
    '.well-known',
    'favicon.ico',
    'robots.txt',
    'sitemap.xml',
    'vi',
    'en',
    'zh',
    'cn',
    'ja',
    'ko',
    'xml-facebook',
    'facebook',
    'feed',
    'rss',
  ].map((s) => s.toLowerCase()),
);

/** Slug có đuôi file — không phải PDP marketing (…-1164016). */
const BLOCKED_EXTENSION = /\.(js|json|xml|php|env|txt|ico|css|map|woff2?|ttf|svg|gif|png|jpe?g|webp|aspx|asp)$/i;

export function isReservedNonProductSlug(raw: string): boolean {
  const s = (raw || '').trim().toLowerCase();
  /** Khớp API group-listing-path (min_length=3) — tránh 422 + SSR treo. */
  if (!s || s.length < 3) return true;
  if (EXACT_BLOCKED.has(s)) return true;
  if (BLOCKED_EXTENSION.test(s)) return true;
  // Path traversal / probe
  if (s.includes('..') || s.startsWith('.')) return true;
  return false;
}
