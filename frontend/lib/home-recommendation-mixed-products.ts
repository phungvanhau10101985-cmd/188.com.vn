import type { Product } from '@/types/api';

export const HOME_COHORT_MIX_POOL_SIZE = 30;

/** Dedupe theo id, giữ thứ tự lần đầu gặp. */
function dedupeProducts(products: Product[]): Product[] {
  const seen = new Set<number>();
  const out: Product[] = [];
  for (const product of products) {
    if (seen.has(product.id)) continue;
    seen.add(product.id);
    out.push(product);
  }
  return out;
}

/**
 * Trộn SP cùng shop (đã xáo từ API) với pool tuổi/giới — chèn cohort ngẫu nhiên vào lưới.
 * Mỗi lần gọi (tải lại trang / seed mới) thứ tự có thể khác.
 */
export function mixShopAndCohortProducts(
  shopProducts: Product[],
  cohortProducts: Product[]
): Product[] {
  const shop = dedupeProducts(shopProducts);
  const shopIds = new Set(shop.map((p) => p.id));
  const cohortOnly = dedupeProducts(cohortProducts).filter((p) => !shopIds.has(p.id));

  if (cohortOnly.length === 0) return shop;

  const mixed = [...shop];
  for (const product of cohortOnly) {
    const insertAt = Math.floor(Math.random() * (mixed.length + 1));
    mixed.splice(insertAt, 0, product);
  }
  return mixed;
}

/** Ghép thêm batch cùng shop sau «Xem thêm» — không xáo lại danh sách đã hiển thị. */
export function appendNewShopProductsToMix(current: Product[], shopBatch: Product[]): Product[] {
  if (shopBatch.length === 0) return current;
  const ids = new Set(current.map((p) => p.id));
  const appended = dedupeProducts(shopBatch).filter((p) => !ids.has(p.id));
  return appended.length > 0 ? [...current, ...appended] : current;
}
