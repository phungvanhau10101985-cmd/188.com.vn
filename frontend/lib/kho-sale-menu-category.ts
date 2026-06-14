import type { CategoryLevel1 } from '@/types/api';

/** Nhãn cố định trong menu danh mục — trỏ /kho-sale (hàng hoàn / thanh lý kho). */
export const KHO_SALE_MENU_NAME = 'Sale kho';
export const KHO_SALE_MENU_SLUG = 'kho-sale';
export const KHO_SALE_HREF = '/kho-sale';

export function isKhoSaleMenuCategory(
  level1: Pick<CategoryLevel1, 'name' | 'slug'> | null | undefined,
): boolean {
  if (!level1) return false;
  const slug = (level1.slug || '').trim().toLowerCase();
  const name = (level1.name || '').trim().toLowerCase();
  return slug === KHO_SALE_MENU_SLUG || name === KHO_SALE_MENU_NAME.toLowerCase();
}

/** Có ít nhất một danh mục thật từ API (không chỉ mục «Sale kho» client chèn). */
export function hasRealCategoryTree(tree: CategoryLevel1[] | null | undefined): boolean {
  return (tree || []).some((c) => !isKhoSaleMenuCategory(c));
}

/** Bỏ mục «Sale kho» synthetic trước khi lưu cache (chỉ giữ data API). */
export function stripKhoSaleMenuCategory(tree: CategoryLevel1[]): CategoryLevel1[] {
  return (tree || []).filter((c) => !isKhoSaleMenuCategory(c));
}

/** Chỉ có «Sale kho» synthetic — coi như chưa có data, cần fetch/cache lại. */
export function isPlaceholderOnlyCategoryTree(tree: CategoryLevel1[] | null | undefined): boolean {
  const list = tree || [];
  return list.length > 0 && !hasRealCategoryTree(list);
}

export function level1CategoryHref(level1: Pick<CategoryLevel1, 'name' | 'slug'>): string {
  if (isKhoSaleMenuCategory(level1)) return KHO_SALE_HREF;
  const slug = (level1.slug || level1.name || '').trim();
  return `/danh-muc/${encodeURIComponent(slug)}`;
}

/** Chèn «Sale kho» lên đầu cây menu (không trùng nếu API đã có). */
export function withKhoSaleMenuCategory(tree: CategoryLevel1[]): CategoryLevel1[] {
  const base = (tree || []).filter((c) => !isKhoSaleMenuCategory(c));
  return [
    {
      name: KHO_SALE_MENU_NAME,
      slug: KHO_SALE_MENU_SLUG,
      children: [],
    },
    ...base,
  ];
}
