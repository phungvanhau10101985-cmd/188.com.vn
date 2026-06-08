/**
 * SSR PDP / legacy: redirect listing nhóm với ít round-trip nhất.
 */
import type { Product } from '@/types/api';
import { getProductBySlugForSSR } from '@/lib/product-seo';
import {
  fastSearchListingPathFromSlug,
  resolveProductGroupListingPath,
} from '@/lib/product-oos-redirect';

export async function loadProductForOosPage(slug: string): Promise<Product | null> {
  return getProductBySlugForSSR(slug, {
    noStore: true,
    attachGroupListing: true,
  });
}

export async function resolveOosListingPathForSlug(
  slug: string,
  product?: Product | null,
  options?: { legacyMarketingPath?: boolean },
): Promise<string | null> {
  const whStock = (product?.warehouse_variants ?? []).some((v) => (v.available ?? 0) > 0);
  if (product?.source_oos && whStock) {
    return null;
  }
  const embedded = (product?.group_listing_path || '').trim();
  if (embedded) return embedded;
  if (!product && slug.toLowerCase().includes('a188')) {
    const fast = fastSearchListingPathFromSlug(slug);
    if (fast) return fast;
  }
  return resolveProductGroupListingPath(slug, options);
}
