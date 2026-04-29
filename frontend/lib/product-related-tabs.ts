import type { Product } from '@/types/api';

/** Tab “SP liên quan” trên trang chi tiết — dùng chung MobileHeader + RelatedProducts */
export const PRODUCT_RELATED_TAB_IDS = ['bestselling', 'same_price', 'lower_price', 'higher_price'] as const;
export type ProductRelatedTabId = (typeof PRODUCT_RELATED_TAB_IDS)[number];

export const PRODUCT_RELATED_TABS: { id: ProductRelatedTabId; label: string }[] = [
  { id: 'bestselling', label: 'Sản phẩm bán chạy' },
  { id: 'same_price', label: 'SP cùng loại cùng tầm giá' },
  { id: 'lower_price', label: 'SP cùng loại giá thấp hơn' },
  { id: 'higher_price', label: 'SP cùng loại giá cao hơn' },
];

export function parseRelatedTabFromSearch(rt: string | null | undefined): ProductRelatedTabId {
  const v = (rt || '').trim();
  if (PRODUCT_RELATED_TAB_IDS.includes(v as ProductRelatedTabId)) {
    return v as ProductRelatedTabId;
  }
  return 'bestselling';
}

/** Giá trị cột Excel — bỏ trống / nan */
export function excelCell(v?: string | null): string | undefined {
  if (v == null) return undefined;
  const s = String(v).trim();
  if (!s || s.toLowerCase() === 'nan') return undefined;
  return s;
}

/** Ghi khi xem chi tiết SP — MobileHeader đọc để mở trang chủ với đúng filter */
export const PD_RELATED_FILTERS_STORAGE_KEY = '188_pd_related_filters';

export type StoredRelatedFilters = {
  shop_id?: string;
  shop_name?: string;
  pro_lower_price?: string;
  pro_high_price?: string;
};

export function filtersFromProduct(
  p: Pick<Product, 'shop_id' | 'shop_name' | 'pro_lower_price' | 'pro_high_price'>
): StoredRelatedFilters {
  return {
    shop_id: excelCell(p.shop_id),
    shop_name: excelCell(p.shop_name),
    pro_lower_price: excelCell(p.pro_lower_price),
    pro_high_price: excelCell(p.pro_high_price),
  };
}

export function persistRelatedFiltersFromProduct(
  p: Pick<Product, 'shop_id' | 'shop_name' | 'pro_lower_price' | 'pro_high_price'>
): void {
  if (typeof window === 'undefined') return;
  try {
    sessionStorage.setItem(PD_RELATED_FILTERS_STORAGE_KEY, JSON.stringify(filtersFromProduct(p)));
  } catch {
    /* ignore quota / private mode */
  }
}

export function readStoredRelatedFilters(): StoredRelatedFilters {
  if (typeof window === 'undefined') return {};
  try {
    const raw = sessionStorage.getItem(PD_RELATED_FILTERS_STORAGE_KEY);
    if (!raw) return {};
    const o = JSON.parse(raw) as Record<string, unknown>;
    const str = (k: string) => {
      const v = o[k];
      return typeof v === 'string' ? excelCell(v) : undefined;
    };
    return {
      shop_id: str('shop_id'),
      shop_name: str('shop_name'),
      pro_lower_price: str('pro_lower_price'),
      pro_high_price: str('pro_high_price'),
    };
  } catch {
    return {};
  }
}

/**
 * Query cho trang chủ `/` (đã hỗ trợ shop_id, shop_name, pro_lower_price, pro_high_price).
 * Trả về null nếu thiếu trường bắt buộc cho tab đó.
 */
export function buildHomeListingSearchParams(
  tab: ProductRelatedTabId,
  f: StoredRelatedFilters
): URLSearchParams | null {
  const p = new URLSearchParams();
  switch (tab) {
    case 'bestselling':
      if (!f.shop_id) return null;
      p.set('shop_id', f.shop_id);
      break;
    case 'same_price':
      if (!f.shop_name) return null;
      p.set('shop_name', f.shop_name);
      break;
    case 'lower_price':
      if (!f.pro_lower_price) return null;
      p.set('pro_lower_price', f.pro_lower_price);
      break;
    case 'higher_price':
      if (!f.pro_high_price) return null;
      p.set('pro_high_price', f.pro_high_price);
      break;
    default:
      return null;
  }
  return p;
}

/** Chuỗi query hoặc null — dùng cho Link `href` */
export function buildHomeListingHref(tab: ProductRelatedTabId, f: StoredRelatedFilters): string | null {
  const params = buildHomeListingSearchParams(tab, f);
  return params ? `/?${params.toString()}` : null;
}
