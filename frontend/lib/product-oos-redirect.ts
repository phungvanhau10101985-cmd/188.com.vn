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
  if (!key) return null;

  const apiBase = getApiBaseUrl();

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
    });
    if (!res.ok) return null;
    const data = (await res.json()) as ProductGroupListingRedirectResult;
    const path = (data.redirect_path || '').trim();
    if (!path || !path.startsWith('/')) return null;
    if (path === `/products/${key}`) return null;
    return path;
  } catch {
    return null;
  }
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
