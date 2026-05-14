import type { Product } from '@/types/api';

/** Tab “SP liên quan” trên trang chi tiết — dùng chung MobileHeader + RelatedProducts */
export const PRODUCT_RELATED_TAB_IDS = ['bestselling', 'same_price', 'lower_price', 'higher_price'] as const;
export type ProductRelatedTabId = (typeof PRODUCT_RELATED_TAB_IDS)[number];

/** Độ rộng khoảng giá (VND) cho «thấp hơn / cao hơn» — so với giá SP hiện tại. */
export const PRODUCT_RELATED_PRICE_BAND_VND = 300_000;

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

/** Giá neo (VND) — làm tròn xuống số nguyên; null nếu không hợp lệ. */
export function floorPriceVnd(n: unknown): number | null {
  const v = typeof n === 'number' ? n : Number(n);
  if (!Number.isFinite(v) || v <= 0) return null;
  return Math.floor(v);
}

function priceBandLower(cur: number): { min_price: number; max_price: number } | null {
  const band = PRODUCT_RELATED_PRICE_BAND_VND;
  const max_price = cur - 1;
  if (max_price < 0) return null;
  const min_price = Math.max(0, cur - band);
  if (min_price > max_price) return null;
  return { min_price, max_price };
}

function priceBandHigher(cur: number): { min_price: number; max_price: number } {
  const band = PRODUCT_RELATED_PRICE_BAND_VND;
  return { min_price: cur + 1, max_price: cur + band };
}

function appendCategoryTriple(
  p: URLSearchParams,
  category?: string,
  subcategory?: string,
  sub_subcategory?: string
) {
  if (category) p.set('category', category);
  if (subcategory) p.set('subcategory', subcategory);
  if (sub_subcategory) p.set('sub_subcategory', sub_subcategory);
}

/**
 * Cùng danh mục cấp 2 + cùng shop Trung Quốc — `shop_name_chinese` (cột Shop Trung Quốc / AM trong export).
 */
export function listingParamsSameChineseShopCat2(
  product: Pick<Product, 'category' | 'subcategory' | 'shop_name_chinese'>
): {
  category?: string;
  subcategory: string;
  shop_name_chinese: string;
} | null {
  const sub2 = excelCell(product.subcategory);
  const sc = excelCell(product.shop_name_chinese);
  if (!sub2 || !sc) return null;
  return {
    category: excelCell(product.category),
    subcategory: sub2,
    shop_name_chinese: sc,
  };
}

/**
 * Query API / URL cho «giá thấp hơn» / «giá cao hơn»: cùng danh mục cấp 2 ± 300k quanh giá hiện tại.
 */
export function listingParamsForPriceSiblingTab(
  tab: 'lower_price' | 'higher_price',
  product: Pick<Product, 'category' | 'subcategory' | 'price'>
): {
  category?: string;
  subcategory: string;
  min_price: number;
  max_price: number;
} | null {
  const sub2 = excelCell(product.subcategory);
  const cur = floorPriceVnd(product.price);
  if (!sub2 || cur == null) return null;

  const category = excelCell(product.category);
  const base = { category, subcategory: sub2 };

  if (tab === 'lower_price') {
    const b = priceBandLower(cur);
    if (!b) return null;
    return { ...base, min_price: b.min_price, max_price: b.max_price };
  }
  const b = priceBandHigher(cur);
  return { ...base, min_price: b.min_price, max_price: b.max_price };
}

/** Ghi khi xem chi tiết SP — MobileHeader đọc để mở trang chủ với đúng filter */
export const PD_RELATED_FILTERS_STORAGE_KEY = '188_pd_related_filters';

export type StoredRelatedFilters = {
  shop_id?: string;
  shop_name?: string;
  /** Style — cột Style (AF) import → `products.style` */
  style?: string;
  category?: string;
  subcategory?: string;
  sub_subcategory?: string;
  /** Shop Trung Quốc — `shop_name_chinese` (cột AM export) */
  shop_name_chinese?: string;
  price_anchor?: number;
};

export function filtersFromProduct(
  p: Pick<
    Product,
    | 'shop_id'
    | 'shop_name'
    | 'style'
    | 'category'
    | 'subcategory'
    | 'sub_subcategory'
    | 'shop_name_chinese'
    | 'price'
  >
): StoredRelatedFilters {
  return {
    shop_id: excelCell(p.shop_id),
    shop_name: excelCell(p.shop_name),
    style: excelCell(p.style),
    category: excelCell(p.category),
    subcategory: excelCell(p.subcategory),
    sub_subcategory: excelCell(p.sub_subcategory),
    shop_name_chinese: excelCell(p.shop_name_chinese),
    price_anchor: floorPriceVnd(p.price) ?? undefined,
  };
}

export function persistRelatedFiltersFromProduct(
  p: Pick<
    Product,
    | 'shop_id'
    | 'shop_name'
    | 'style'
    | 'category'
    | 'subcategory'
    | 'sub_subcategory'
    | 'shop_name_chinese'
    | 'price'
  >
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
    let price_anchor: number | undefined;
    const pa = o['price_anchor'];
    if (typeof pa === 'number' && Number.isFinite(pa)) {
      price_anchor = Math.floor(pa);
    } else if (typeof pa === 'string' && pa.trim()) {
      const n = Number(pa);
      if (Number.isFinite(n)) price_anchor = Math.floor(n);
    }
    const shop_name_chinese = str('shop_name_chinese') ?? str('chinese_name');
    return {
      shop_id: str('shop_id'),
      shop_name: str('shop_name'),
      style: str('style'),
      category: str('category'),
      subcategory: str('subcategory'),
      sub_subcategory: str('sub_subcategory'),
      shop_name_chinese,
      price_anchor,
    };
  } catch {
    return {};
  }
}

/** Tên query: shop Trung Quốc dạng base64url (UTF-8), không lộ chữ Hán trên URL. */
export const SHOP_NAME_CHINESE_QUERY_PARAM = 'sxc';

/** UTF-8 → base64url (chỉ [A-Za-z0-9_-], không dùng trong SSR nếu không có `btoa`). */
export function encodeShopChineseNameForListingUrl(plain: string): string {
  const s = String(plain).trim();
  if (!s) return '';
  const bytes = new TextEncoder().encode(s);
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]!);
  if (typeof btoa === 'undefined') {
    return '';
  }
  const b64 = btoa(bin);
  return b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** `sxc` base64url → chuỗi gốc; lỗi → null. */
export function decodeShopChineseNameFromListingUrl(encoded: string | null | undefined): string | null {
  const s = (encoded ?? '').trim();
  if (!s) return null;
  if (typeof atob === 'undefined') {
    return null;
  }
  try {
    const pad = s.length % 4 === 0 ? '' : '='.repeat(4 - (s.length % 4));
    const b64 = (s + pad).replace(/-/g, '+').replace(/_/g, '/');
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const out = new TextDecoder().decode(bytes).trim();
    return out || null;
  } catch {
    return null;
  }
}

/** Đọc shop TQ từ query listing: ưu tiên `sxc`, fallback `shop_name_chinese` (link cũ). */
export function shopNameChineseFromListingUrlQuery(getter: (key: string) => string | null): string | undefined {
  const fromSxc = decodeShopChineseNameFromListingUrl(getter(SHOP_NAME_CHINESE_QUERY_PARAM));
  if (fromSxc) return excelCell(fromSxc);
  return excelCell(getter('shop_name_chinese'));
}

/**
 * Query cho trang chủ `/`: bán chạy — `style`; «cùng tầm giá» — cấp 2 + shop TQ qua `sxc` (base64url);
 * thấp/cao — cấp 2 + khoảng giá ±300k.
 */
export function buildHomeListingSearchParams(
  tab: ProductRelatedTabId,
  f: StoredRelatedFilters
): URLSearchParams | null {
  const p = new URLSearchParams();

  switch (tab) {
    case 'bestselling':
      if (!f.style) return null;
      p.set('style', f.style);
      return p;
    case 'same_price': {
      if (!f.subcategory || !f.shop_name_chinese) return null;
      appendCategoryTriple(p, f.category, f.subcategory);
      const sxc = encodeShopChineseNameForListingUrl(f.shop_name_chinese);
      if (!sxc) return null;
      p.set(SHOP_NAME_CHINESE_QUERY_PARAM, sxc);
      return p;
    }
    case 'lower_price': {
      if (!f.subcategory || f.price_anchor == null) return null;
      const b = priceBandLower(f.price_anchor);
      if (!b) return null;
      appendCategoryTriple(p, f.category, f.subcategory);
      p.set('min_price', String(b.min_price));
      p.set('max_price', String(b.max_price));
      return p;
    }
    case 'higher_price': {
      if (!f.subcategory || f.price_anchor == null) return null;
      const b = priceBandHigher(f.price_anchor);
      appendCategoryTriple(p, f.category, f.subcategory);
      p.set('min_price', String(b.min_price));
      p.set('max_price', String(b.max_price));
      return p;
    }
    default:
      return null;
  }
}

/**
 * Chuỗi query cho `href` / `router.push`: mã hóa từng key và value bằng `encodeURIComponent`
 * (ký tự không-ASCII → `%` + UTF-8). `URLSearchParams.toString()` theo x-www-form-urlencoded
 * (space → `+`) và trình duyệt có thể hiển thị Unicode thô trên thanh địa chỉ — cách này giữ URL dạng phần trăm rõ ràng hơn.
 */
export function searchParamsToEncodedQueryString(p: URLSearchParams): string {
  const entries = [...p.entries()].sort(([k1, v1], [k2, v2]) =>
    k1 === k2 ? v1.localeCompare(v2) : k1.localeCompare(k2)
  );
  return entries.map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`).join('&');
}

/**
 * Clone `useSearchParams()` (ReadonlyURLSearchParams) hoặc `URLSearchParams`, giữ mọi cặp key/value đã decode
 * (dùng `append` nếu trùng key).
 */
export function cloneUrlSearchParams(sp: {
  forEach(callbackfn: (value: string, key: string) => void): void;
}): URLSearchParams {
  const p = new URLSearchParams();
  sp.forEach((value, key) => {
    p.append(key, value);
  });
  return p;
}

/** Hai chuỗi query có cùng tham số sau khi parse (bất kể thứ tự key / dạng mã hóa). */
export function urlSearchParamsSemanticsEqual(a: URLSearchParams, b: URLSearchParams): boolean {
  const sortEntries = (sp: URLSearchParams) =>
    [...sp.entries()].sort(([k1, v1], [k2, v2]) =>
      k1 === k2 ? v1.localeCompare(v2) : k1.localeCompare(k2)
    );
  const ea = sortEntries(a);
  const eb = sortEntries(b);
  return ea.length === eb.length && ea.every(([k, v], i) => k === eb[i][0] && v === eb[i][1]);
}

/** Chuỗi query hoặc null — dùng cho Link `href` */
export function buildHomeListingHref(tab: ProductRelatedTabId, f: StoredRelatedFilters): string | null {
  const params = buildHomeListingSearchParams(tab, f);
  return params ? `/?${searchParamsToEncodedQueryString(params)}` : null;
}
