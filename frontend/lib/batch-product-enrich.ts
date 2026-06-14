import { apiClient } from '@/lib/api-client';
import type { Product } from '@/types/api';

/** Gom enrich snapshot → một batch GET /products/by-ids. */
export async function fetchProductsByIdsMap(ids: number[]): Promise<Map<number, Product>> {
  const products = await apiClient.getProductsByIds(ids);
  return new Map(products.map((p) => [p.id, p]));
}

export async function enrichItemsWithProductBatch<T extends { product_id: number }>(
  items: T[],
  needsEnrich: (item: T) => boolean,
  merge: (item: T, product: Product) => T
): Promise<T[]> {
  const ids = [...new Set(items.filter(needsEnrich).map((item) => item.product_id))];
  if (ids.length === 0) return items;
  const byId = await fetchProductsByIdsMap(ids);
  return items.map((item) => {
    if (!needsEnrich(item)) return item;
    const product = byId.get(item.product_id);
    return product ? merge(item, product) : item;
  });
}
