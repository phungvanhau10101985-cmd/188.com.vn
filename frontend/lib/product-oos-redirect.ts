/**
 * PDP hết hàng / không tồn tại → redirect listing nhóm (/c/..., /danh-muc/..., /?q=...).
 */
import { getApiBaseUrl } from '@/lib/api-base';

export interface ProductGroupListingRedirectResult {
  redirect_path: string | null;
  redirect_type?: string;
  redirect_slug?: string | null;
}

export async function resolveProductGroupListingPath(
  slug: string,
  options?: { /** URL /moi-ma-... một segment */ legacyMarketingPath?: boolean },
): Promise<string | null> {
  const key = (slug || '').trim();
  if (!key) return null;

  const apiBase =
    typeof window === 'undefined'
      ? getApiBaseUrl()
      : process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8001/api/v1';

  try {
    const params = new URLSearchParams({ slug: key });
    if (options?.legacyMarketingPath) {
      params.set('legacy_path', 'true');
    }
    const res = await fetch(`${apiBase}/products/oos-group-redirect?${params}`, {
      cache: 'no-store',
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
