/**
 * PDP hết hàng → redirect sang slug nhóm / biến thể giống >= 80% (backend SequenceMatcher).
 */
import { getApiBaseUrl } from '@/lib/api-base';

export const PRODUCT_OOS_SLUG_SIMILARITY_MIN = 0.8;

export interface ProductOosGroupRedirectResult {
  redirect_slug: string | null;
  redirect_path: string | null;
  similarity_min?: number;
}

export async function resolveProductOosGroupRedirectSlug(
  slug: string,
  options?: { minSimilarity?: number },
): Promise<string | null> {
  const key = (slug || '').trim();
  if (!key) return null;

  const minSimilarity = options?.minSimilarity ?? PRODUCT_OOS_SLUG_SIMILARITY_MIN;
  const apiBase =
    typeof window === 'undefined'
      ? getApiBaseUrl()
      : process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8001/api/v1';

  try {
    const params = new URLSearchParams({
      slug: key,
      min_similarity: String(minSimilarity),
    });
    const res = await fetch(`${apiBase}/products/oos-group-redirect?${params}`, {
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) return null;
    const data = (await res.json()) as ProductOosGroupRedirectResult;
    const target = (data.redirect_slug || '').trim();
    return target && target !== key ? target : null;
  } catch {
    return null;
  }
}

/** Path PDP — slug từ API đã an toàn (a-z, số, gạch ngang). */
export function productOosGroupRedirectPath(slug: string): string {
  const seg = (slug || '').trim().replace(/^\/+|\/+$/g, '');
  return seg ? `/products/${seg}` : '/';
}
