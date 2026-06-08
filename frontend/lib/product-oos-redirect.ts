/**
 * PDP hết hàng / không tồn tại → redirect listing nhóm (/c/..., /danh-muc/..., /?q=...).
 */
import { getApiBaseUrl } from '@/lib/api-base';
import { normalizeLegacyProductPath } from '@/lib/legacy-product-path';

export interface ProductGroupListingRedirectResult {
  redirect_path: string | null;
  redirect_type?: string;
  redirect_slug?: string | null;
}

const listingPathPromiseCache = new Map<string, Promise<string | null>>();
const LISTING_PATH_CACHE_MAX = 200;

function cacheKeyForListingPath(slug: string, legacyMarketingPath?: boolean): string {
  return `${legacyMarketingPath ? 'legacy' : 'normal'}:${slug.toLowerCase()}`;
}

/** Redirect tìm kiếm nhanh từ slug marketing — không gọi API (bot/link SP ẩn ảnh). */
export function fastSearchListingPathFromSlug(slug: string): string | null {
  const key = normalizeLegacyProductPath(slug).toLowerCase();
  if (!key || key.length < 6) return null;
  const parts = key
    .split("-")
    .filter(
      (p) =>
        p.length > 0 &&
        !/^\d{5,}$/.test(p) &&
        !p.includes("a188") &&
        !/^a?\d{6,}$/i.test(p),
    );
  if (parts.length < 2) return null;
  const q = parts.slice(0, 4).join(" ");
  return `/?q=${encodeURIComponent(q)}`;
}

export async function resolveProductGroupListingPath(
  slug: string,
  options?: {
    /** URL /moi-ma-... một segment — giữ query legacy_path cho tương thích */
    legacyMarketingPath?: boolean;
    /** Cho phép cache ngắn (client fallback); SSR nên để false */
    allowCache?: boolean;
  },
): Promise<string | null> {
  const key = normalizeLegacyProductPath(slug);
  if (!key || key.length < 3) return null;
  const normalizedKey = key.replace(/^\/+|\/+$/g, '').toLowerCase();
  const cacheKey = cacheKeyForListingPath(normalizedKey, options?.legacyMarketingPath);
  if (options?.allowCache) {
    const hit = listingPathPromiseCache.get(cacheKey);
    if (hit) return hit;
  }

  const apiBase = getApiBaseUrl();

  const task = (async () => {
    try {
    const params = new URLSearchParams({ slug: key });
    if (options?.legacyMarketingPath) {
      params.set('legacy_path', 'true');
    }
    const res = await fetch(`${apiBase}/products/group-listing-path?${params}`, {
      ...(options?.allowCache
        ? { next: { revalidate: 300 } }
        : { cache: 'no-store' as const }),
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as ProductGroupListingRedirectResult;
    const path = (data.redirect_path || '').trim();
    if (!path || !path.startsWith('/')) return null;
    const normalizedPath = path.replace(/\/+$/g, '').toLowerCase();
    // Chặn self-redirect loop:
    // - /products/{slug} -> /products/{slug}
    // - /{legacy-slug}   -> /{legacy-slug}
    if (normalizedPath === `/products/${normalizedKey}`) return null;
    if (normalizedPath === `/${normalizedKey}`) return null;
    return path;
    } catch {
      return null;
    }
  })();

  if (!options?.allowCache) {
    return task;
  }

  listingPathPromiseCache.set(cacheKey, task);
  if (listingPathPromiseCache.size > LISTING_PATH_CACHE_MAX) {
    const oldestKey = listingPathPromiseCache.keys().next().value;
    if (oldestKey) listingPathPromiseCache.delete(oldestKey);
  }
  return task;
}

/** @deprecated Dùng resolveProductGroupListingPath */
export async function resolveProductOosGroupRedirectSlug(
  slug: string,
  options?: { minSimilarity?: number; legacyMarketingPath?: boolean },
): Promise<string | null> {
  void options?.minSimilarity;
  return resolveProductGroupListingPath(slug, {
    legacyMarketingPath: options?.legacyMarketingPath,
  });
}

/** Chuẩn hoá path listing từ API (đã là /c/... hoặc /danh-muc/...). */
export function productOosGroupRedirectPath(pathOrSlug: string): string {
  const raw = (pathOrSlug || '').trim();
  if (!raw) return '/';
  if (raw.startsWith('/')) return raw;
  return `/products/${raw.replace(/^\/+|\/+$/g, '')}`;
}
