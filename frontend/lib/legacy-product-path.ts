/**
 * URL PDP legacy (một segment, không có /products/):
 * - Marketing: /moi-ma-a8735-gia-1520k-ao-khoac-nam-...-1164016
 * - index.php cũ: /index.php/vay-dam-lien-than-du-tiec-nu-1172882
 */
import type { Product } from '@/types/api';
import { getApiBaseUrl } from '@/lib/api-base';
import { getProductBySlugForSSR, getProductBySkuForSSR } from '@/lib/product-seo';
import { resolveProductGroupListingPath } from '@/lib/product-oos-redirect';
import { productPathSlugFromApi } from '@/lib/product-path-slug';

/**
 * Chuẩn hoá path legacy: bỏ `/index.php/`, query, host.
 * Vd `/index.php/vay-dam-lien-than-du-tiec-nu-1172882` → `vay-dam-lien-than-du-tiec-nu-1172882`.
 */
export function normalizeLegacyProductPath(path: string): string {
  let s = (path || '').trim();
  if (!s) return '';
  if (/^https?:\/\//i.test(s)) {
    try {
      s = new URL(s).pathname;
    } catch {
      /* giữ nguyên */
    }
  }
  s = s.replace(/^\/+/, '');
  s = s.replace(/^index\.php\/?/i, '');
  return s.replace(/^\/+/, '').trim();
}

/** Số cuối path (vd …-1164016) — thường là products.id hoặc mã nội bộ. */
export function extractTrailingNumericId(path: string): number | null {
  const m = normalizeLegacyProductPath(path).match(/-(\d{5,})$/);
  if (!m) return null;
  const n = Number.parseInt(m[1], 10);
  return Number.isFinite(n) && n > 0 ? n : null;
}

export async function getProductByDbIdForSSR(
  dbId: number,
  options?: { attachGroupListing?: boolean },
): Promise<Product | null> {
  if (!Number.isFinite(dbId) || dbId <= 0) return null;
  const apiBase = getApiBaseUrl();
  try {
    const q = options?.attachGroupListing ? '?attach_group_listing=true' : '';
    const res = await fetch(`${apiBase}/products/by-id/${dbId}${q}`, {
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) return null;
    return (await res.json()) as Product;
  } catch {
    return null;
  }
}

/** Tra SP từ path marketing / index.php: slug đầy đủ → SKU/product_id → id cuối URL. */
export async function resolveProductFromLegacyPath(path: string): Promise<Product | null> {
  const key = normalizeLegacyProductPath(path);
  if (!key) return null;

  let product = await getProductBySlugForSSR(key);
  if (product?.id) return product;

  product = await getProductBySkuForSSR(key);
  if (product?.id) return product;

  const tailId = extractTrailingNumericId(key);
  if (tailId) {
    product = await getProductByDbIdForSSR(tailId);
    if (product?.id) return product;
    product = await getProductBySkuForSSR(String(tailId));
    if (product?.id) return product;
  }

  return null;
}

/** Tra SP + đường dẫn listing song song (SSR legacy URL). */
export async function resolveLegacyProductAndListingPath(path: string): Promise<{
  product: Product | null;
  listingPath: string | null;
}> {
  const key = normalizeLegacyProductPath(path);
  const [product, listingPath] = await Promise.all([
    resolveProductFromLegacyPath(key),
    resolveProductGroupListingPath(key, { legacyMarketingPath: true }),
  ]);
  return { product, listingPath };
}

/** Segment /products/ chuẩn để redirect. */
export function canonicalProductPathFromProduct(product: Product): string | null {
  const seg = productPathSlugFromApi(product.slug, product.product_id);
  return seg ? `/products/${seg}` : null;
}
