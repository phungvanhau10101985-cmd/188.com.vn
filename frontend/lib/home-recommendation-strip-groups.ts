import type { Product } from '@/types/api';

export type HomeProductStripGroup = {
  id: string;
  kind: 'shop' | 'cohort';
  label: string;
  products: Product[];
};

export const HOME_SHOP_STRIP_MAX_GROUPS = 8;
export const HOME_COHORT_STRIP_GROUPS = 2;
export const HOME_MIXED_STRIP_TOTAL = 10;

export function shopKeyForProduct(product: Product): string {
  const key = (product.shop_name_chinese || product.shop_name || '').trim().toLowerCase();
  return key || '__unknown__';
}

export function shopLabelForProduct(product: Product): string {
  const label = (product.shop_name_chinese || product.shop_name || 'Shop').trim();
  return label || 'Shop';
}

/** Gom SP cùng shop theo thứ tự xuất hiện (ưu tiên shop xem gần nhất). */
export function groupProductsByShop(
  products: Product[],
  maxGroups = HOME_SHOP_STRIP_MAX_GROUPS
): HomeProductStripGroup[] {
  const order: string[] = [];
  const buckets = new Map<string, Product[]>();
  const labels = new Map<string, string>();

  for (const product of products) {
    const key = shopKeyForProduct(product);
    if (!buckets.has(key)) {
      buckets.set(key, []);
      order.push(key);
      labels.set(key, shopLabelForProduct(product));
    }
    if (order.indexOf(key) < maxGroups) {
      buckets.get(key)!.push(product);
    }
  }

  return order
    .slice(0, maxGroups)
    .map((key) => ({
      id: `shop-${key}`,
      kind: 'shop' as const,
      label: labels.get(key) ?? 'Shop',
      products: buckets.get(key) ?? [],
    }))
    .filter((group) => group.products.length > 0);
}

/** Chia đều gợi ý tuổi/giới thành 2 dòng cuộn ngang. */
export function splitCohortStripGroups(products: Product[]): HomeProductStripGroup[] {
  if (products.length === 0) return [];

  const half = Math.ceil(products.length / HOME_COHORT_STRIP_GROUPS);
  const chunks = [
    products.slice(0, half),
    products.slice(half, half * 2),
  ].filter((chunk) => chunk.length > 0);

  return chunks.map((chunk, index) => ({
    id: `cohort-${index}`,
    kind: 'cohort' as const,
    label: 'Đề xuất theo tuổi & giới tính',
    products: chunk,
  }));
}

/** Xen 2 nhóm cohort vào giữa tối đa 8 nhóm shop (10 dòng). */
export function mixShopAndCohortStrips(
  shopGroups: HomeProductStripGroup[],
  cohortGroups: HomeProductStripGroup[]
): HomeProductStripGroup[] {
  const shops = shopGroups.slice(0, HOME_SHOP_STRIP_MAX_GROUPS);
  const cohorts = cohortGroups.slice(0, HOME_COHORT_STRIP_GROUPS);
  if (cohorts.length === 0) return shops;

  const cohortSlots =
    cohorts.length >= 2 ? [2, 6] : cohorts.length === 1 ? [Math.min(4, Math.max(shops.length, 0))] : [];

  const mixed: HomeProductStripGroup[] = [];
  let shopIndex = 0;
  let cohortIndex = 0;

  for (let slot = 0; slot < HOME_MIXED_STRIP_TOTAL; slot++) {
    if (cohortSlots.includes(slot) && cohortIndex < cohorts.length) {
      mixed.push(cohorts[cohortIndex]!);
      cohortIndex += 1;
      continue;
    }
    if (shopIndex < shops.length) {
      mixed.push(shops[shopIndex]!);
      shopIndex += 1;
    }
  }

  return mixed;
}
