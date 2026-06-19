'use client';

/**
 * Google Ads — gtag: tiếp thị lại động (Retail) + sự kiện GA4-style.
 * `send_to`: ưu tiên danh sách AW- do API embed công khai trả về (chỉ mã admin google/ads).
 * API cũ không có trường đó → tạm dùng NEXT_PUBLIC_GOOGLE_ADS_AW_ID + quét script AW- trên DOM (không khuyến nghị).
 * Chuyển đổi AW-/label (gtag conversion) — khớp admin + NEXT_PUBLIC_*:
 * | Key API / env | Loại site_embed_codes | Nơi bắn |
 * |---------------|------------------------|---------|
 * | pdp | ads_pdp_conversion | PDP — trackGoogleAdsViewItemProduct |
 * | add_to_cart | ads_conversion_add_to_cart | useCart → trackGoogleAdsAddToCart |
 * | begin_checkout | ads_conversion_begin_checkout | /cart — trackGoogleAdsCartPageView |
 * | deposit_page | ads_conversion_deposit_page | /account/orders/[id]/deposit — trackGoogleAdsDepositCheckoutPage |
 * | purchase | ads_conversion_purchase | /cart checkout + deposit (COD) — trackGoogleAdsPurchase |
 */
import type { AddToCartRequest } from '@/features/cart/types/cart';
import type { CartItem } from '@/features/cart/types/cart';
import type { Product } from '@/types/api';
import { productPathSlugFromApi } from '@/lib/product-path-slug';
import type { GoogleAdsWebConversionsPublic } from '@/lib/site-embeds-public';
import {
  metaContentIdsForProduct,
  metaContentIdsFromAddToCart,
  metaContentIdsFromCartItem,
} from '@/lib/meta-pixel';

export const GOOGLE_ADS_CURRENCY = 'VND';

type GtagCommand = (...args: unknown[]) => void;

function getGtag(): GtagCommand | undefined {
  if (typeof window === 'undefined') return undefined;
  const g = (window as Window & { gtag?: GtagCommand }).gtag;
  return typeof g === 'function' ? g : undefined;
}

/** null = chưa cấu hình từ embed (dùng legacy); non-null = chỉ đích admin (có thể rỗng). */
let googleAdsSendToFromAdmin: string[] | null = null;

/** Gọi từ SiteEmbedsRoot sau khi inject — chỉ gửi sự kiện tới các AW- này. */
export function setGoogleAdsSendToFromAdmin(ids: string[]): void {
  googleAdsSendToFromAdmin = [
    ...new Set(
      ids
        .map((s) => String(s ?? '').trim().toUpperCase())
        .filter((s) => /^AW-\d+$/.test(s))
    ),
  ];
}

/** API embed cũ / thiếu trường google_ads_aw_ids — gom env + DOM như trước. */
export function clearGoogleAdsSendToAdminOnlyMode(): void {
  googleAdsSendToFromAdmin = null;
}

function collectAwIdsFromScripts(): string[] {
  if (typeof document === 'undefined') return [];
  const out: string[] = [];
  document.querySelectorAll('script[src*="googletagmanager.com/gtag/js"]').forEach((el) => {
    const src = el.getAttribute('src') || '';
    const m = src.match(/[?&]id=(AW-\d+)/i);
    if (m?.[1]) out.push(m[1].toUpperCase());
  });
  return [...new Set(out)];
}

function collectGa4IdsFromScripts(): string[] {
  if (typeof document === 'undefined') return [];
  const out: string[] = [];
  document.querySelectorAll('script[src*="googletagmanager.com/gtag/js"]').forEach((el) => {
    const src = el.getAttribute('src') || '';
    const m = src.match(/[?&]id=(G-[A-Z0-9]+)/i);
    if (m?.[1]) out.push(m[1].toUpperCase());
  });
  document.querySelectorAll('script').forEach((el) => {
    const text = el.textContent || '';
    const re = /gtag\s*\(\s*['"]config['"]\s*,\s*['"](G-[A-Z0-9]+)['"]/gi;
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      if (m[1]) out.push(m[1].toUpperCase());
    }
  });
  return [...new Set(out)];
}

function collectSendToFromEnv(): string[] {
  const raw = process.env.NEXT_PUBLIC_GOOGLE_ADS_AW_ID?.trim();
  if (!raw) return [];
  return [
    ...new Set(
      raw
        .split(/[\s,]+/)
        .map((s) => s.trim().toUpperCase())
        .filter((s) => /^AW-\d+$/.test(s))
    ),
  ];
}

function collectGa4FromEnv(): string[] {
  const raw =
    process.env.NEXT_PUBLIC_GA4_MEASUREMENT_ID?.trim() ||
    process.env.NEXT_PUBLIC_GOOGLE_ANALYTICS_ID?.trim() ||
    process.env.NEXT_PUBLIC_GOOGLE_ANALYTICS_MEASUREMENT_ID?.trim();
  if (!raw) return [];
  return [
    ...new Set(
      raw
        .split(/[\s,]+/)
        .map((s) => s.trim().toUpperCase())
        .filter((s) => /^G-[A-Z0-9]+$/.test(s))
    ),
  ];
}

/** Các đích AW- cho `send_to` — khi embed API có google_ads_aw_ids thì chỉ dùng danh sách admin. */
export function getGoogleAdsSendToTargets(): string[] {
  if (googleAdsSendToFromAdmin !== null) {
    return googleAdsSendToFromAdmin;
  }
  return [...new Set([...collectSendToFromEnv(), ...collectAwIdsFromScripts()])];
}

function sendToJoined(): string | null {
  const ids = getGoogleAdsSendToTargets();
  return ids.length ? ids.join(',') : null;
}

function getGa4SendToTargets(): string[] {
  return [...new Set([...collectGa4FromEnv(), ...collectGa4IdsFromScripts()])];
}

export type GoogleAdsWebConversionKey = keyof GoogleAdsWebConversionsPublic;

const EMPTY_WEB_CONV: Record<GoogleAdsWebConversionKey, string> = {
  pdp: '',
  add_to_cart: '',
  begin_checkout: '',
  deposit_page: '',
  purchase: '',
};

/** API đã trả `google_ads_web_conversions` — chỉ dùng giá trị từ đó (chuỗi rỗng = tắt). */
let webConversionsFromApi = false;
let webConversionsRaw: Record<GoogleAdsWebConversionKey, string> = { ...EMPTY_WEB_CONV };

/** Legacy API: chỉ trả PDP — PDP theo admin, các conversion khác vẫn NEXT_PUBLIC_* */
let webConvPdpOverrideLegacy: string | null = null;

export function setGoogleAdsWebConversionsFromEmbed(
  conv: GoogleAdsWebConversionsPublic | undefined,
  options?: { legacyPdpOnly?: boolean },
): void {
  if (!conv) {
    webConversionsFromApi = false;
    webConversionsRaw = { ...EMPTY_WEB_CONV };
    webConvPdpOverrideLegacy = null;
    return;
  }
  if (options?.legacyPdpOnly) {
    webConversionsFromApi = false;
    webConversionsRaw = { ...EMPTY_WEB_CONV };
    webConvPdpOverrideLegacy = String(conv.pdp ?? '').trim().replace(/\s/g, '');
    return;
  }
  webConvPdpOverrideLegacy = null;
  webConversionsFromApi = true;
  webConversionsRaw = {
    pdp: String(conv.pdp ?? '').trim().replace(/\s/g, ''),
    add_to_cart: String(conv.add_to_cart ?? '').trim().replace(/\s/g, ''),
    begin_checkout: String(conv.begin_checkout ?? '').trim().replace(/\s/g, ''),
    deposit_page: String(conv.deposit_page ?? '').trim().replace(/\s/g, ''),
    purchase: String(conv.purchase ?? '').trim().replace(/\s/g, ''),
  };
}

export function clearGoogleAdsWebConversionsFromEmbed(): void {
  setGoogleAdsWebConversionsFromEmbed(undefined);
}

/** Một token conversion Google Ads — chỉ AW-/label; có thể dán kèm send_to/snippet, hệ thống tự trích. */
const AW_CONVERSION_LABEL_RE = /\bAW-\d+\/[A-Za-z0-9_-]+/i;

function parseFullSendTo(s: string): string | null {
  const trimmed = (s || '').trim();
  if (!trimmed) return null;
  let m = trimmed.match(AW_CONVERSION_LABEL_RE);
  if (!m) {
    const compact = trimmed.replace(/\s/g, '');
    m = compact.match(/AW-\d+\/[A-Za-z0-9_-]+/i);
  }
  if (!m) return null;
  const t = m[0].replace(/\s/g, '');
  if (!/^AW-\d+\/[A-Za-z0-9_-]+$/i.test(t)) return null;
  const slash = t.indexOf('/');
  return `${t.slice(0, slash).toUpperCase()}/${t.slice(slash + 1)}`;
}

const CONVERSION_ENV: Record<GoogleAdsWebConversionKey, string | undefined> = {
  pdp: process.env.NEXT_PUBLIC_GOOGLE_ADS_PDP_CONVERSION_SEND_TO,
  add_to_cart: process.env.NEXT_PUBLIC_GOOGLE_ADS_ADD_TO_CART_CONVERSION_SEND_TO,
  begin_checkout: process.env.NEXT_PUBLIC_GOOGLE_ADS_BEGIN_CHECKOUT_CONVERSION_SEND_TO,
  deposit_page: process.env.NEXT_PUBLIC_GOOGLE_ADS_DEPOSIT_PAGE_CONVERSION_SEND_TO,
  purchase: process.env.NEXT_PUBLIC_GOOGLE_ADS_PURCHASE_CONVERSION_SEND_TO,
};

function conversionSendToFor(key: GoogleAdsWebConversionKey): string | null {
  if (key === 'pdp' && webConvPdpOverrideLegacy != null && webConvPdpOverrideLegacy !== '') {
    return parseFullSendTo(webConvPdpOverrideLegacy);
  }
  if (webConversionsFromApi) {
    const raw = webConversionsRaw[key];
    const parsed = raw ? parseFullSendTo(raw) : null;
    if (parsed) return parsed;
    /** API trả object nhưng từng key trống → dùng NEXT_PUBLIC_* cho bước đó (admin có thể vừa lưu, cache chưa kịp). */
    const envRaw = CONVERSION_ENV[key]?.trim();
    if (!envRaw) return null;
    return parseFullSendTo(envRaw);
  }
  const envRaw = CONVERSION_ENV[key]?.trim();
  if (!envRaw) return null;
  return parseFullSendTo(envRaw);
}

/** Thứ tự ổn định — dùng chuỗi fingerprint cấu hình (admin + env). */
const CONVERSION_KEYS_ORDER: GoogleAdsWebConversionKey[] = [
  'pdp',
  'add_to_cart',
  'begin_checkout',
  'deposit_page',
  'purchase',
];

/** Chuỗi ổn định theo mọi send_to đã resolve — khi admin/env đổi, component phụ thuộc nên re-fire tracking. */
export function peekGoogleAdsConversionsFingerprint(): string {
  return CONVERSION_KEYS_ORDER.map((k) => `${k}:${peekGoogleAdsConversionSendTo(k) ?? ''}`).join('|');
}

/** Cho fingerprint / debug: giá trị send_to thực tế sau API+env (không log bí mật khác). */
export function peekGoogleAdsConversionSendTo(key: GoogleAdsWebConversionKey): string | null {
  return conversionSendToFor(key);
}

/** CwCD — chiết khấu tự động Merchant Center (aw_merchant_id, feed country/language). */
function readGoogleMerchantCwcdConfig(): {
  merchantId: number | null;
  feedCountry: string;
  feedLanguage: string;
} {
  const midRaw = process.env.NEXT_PUBLIC_GOOGLE_MERCHANT_CENTER_ID?.trim();
  let merchantId: number | null = null;
  if (midRaw) {
    const n = Number.parseInt(midRaw, 10);
    if (Number.isFinite(n) && n > 0) merchantId = n;
  }
  const feedCountry = (process.env.NEXT_PUBLIC_GOOGLE_FEED_COUNTRY || 'VN').trim().toUpperCase();
  const feedLanguage = (process.env.NEXT_PUBLIC_GOOGLE_FEED_LANGUAGE || 'vi').trim().toLowerCase();
  return { merchantId, feedCountry, feedLanguage };
}

function cartLineListPrice(line: CartItem): number {
  const pd =
    line.product_data && typeof line.product_data === 'object' ? (line.product_data as Record<string, unknown>) : {};
  const list =
    (typeof line.list_price === 'number' && !Number.isNaN(line.list_price) ? line.list_price : null) ??
    (typeof line.original_price === 'number' && !Number.isNaN(line.original_price) ? line.original_price : null) ??
    (typeof pd.list_price === 'number' ? pd.list_price : null) ??
    (typeof pd.original_price === 'number' ? pd.original_price : null);
  return list != null && Number.isFinite(list) ? list : lineUnitPrice(line);
}

function cartDataDiscountTotal(lines: CartItem[]): number {
  let total = 0;
  for (const line of lines) {
    const qty = Math.max(1, line.quantity || 1);
    const unit = lineUnitPrice(line);
    const list = cartLineListPrice(line);
    if (list > unit) total += (list - unit) * qty;
  }
  return Math.max(0, Math.round(total));
}

/** items.id phải khớp cột `id` trong feed GMC (product_id). */
function gtagCwcdItemsFromCartLines(lines: CartItem[]): Record<string, unknown>[] {
  return lines.map((line) => {
    const pd =
      line.product_data && typeof line.product_data === 'object' ? (line.product_data as Record<string, unknown>) : {};
    const feedId =
      (pd.product_id != null ? String(pd.product_id).trim() : '') ||
      (line.product_code != null ? String(line.product_code).trim() : '') ||
      String(line.product_id);
    return {
      id: feedId,
      quantity: line.quantity,
      price: lineUnitPrice(line),
    };
  });
}

function applyCwcdToConversionBody(
  body: Record<string, unknown>,
  lines: CartItem[],
): void {
  const cwcd = readGoogleMerchantCwcdConfig();
  if (!cwcd.merchantId || !lines.length) return;
  body.aw_merchant_id = cwcd.merchantId;
  body.aw_feed_country = cwcd.feedCountry;
  body.aw_feed_language = cwcd.feedLanguage;
  body.items = gtagCwcdItemsFromCartLines(lines);
  const discount = cartDataDiscountTotal(lines);
  if (discount > 0) {
    body.discount = discount;
  }
}

function fireGoogleAdsConversion(
  key: GoogleAdsWebConversionKey,
  payload: {
    value: number;
    items: Record<string, unknown>[];
    transaction_id?: string;
    cart_lines?: CartItem[];
  },
): void {
  const send_to = conversionSendToFor(key);
  if (!send_to) return;
  whenGtagReady(() => {
    const gtag = getGtag();
    if (!gtag) return;
    const convValue = payload.value > 0 ? payload.value : 1.0;
    const body: Record<string, unknown> = {
      send_to,
      value: convValue,
      currency: GOOGLE_ADS_CURRENCY,
      items: payload.items,
    };
    if (payload.transaction_id && String(payload.transaction_id).trim() !== '') {
      body.transaction_id = String(payload.transaction_id).trim();
    }
    if ((key === 'purchase' || key === 'begin_checkout') && payload.cart_lines?.length) {
      applyCwcdToConversionBody(body, payload.cart_lines);
    }
    /** Tiếp thị lại động: Google thường đọc ecomm_* + «id» trong items; Tag Assistant đôi khi chỉ hiện rõ các trường này. */
    if (payload.items.length > 0) {
      const ids = payload.items
        .map((it) => String((it as { item_id?: unknown; id?: unknown }).item_id ?? (it as { id?: unknown }).id ?? '').trim())
        .filter(Boolean);
      if (ids.length === 1) {
        body.ecomm_prodid = ids[0];
      } else if (ids.length > 1) {
        body.ecomm_prodid = ids;
      }
      if (convValue > 0) {
        body.ecomm_totalvalue = convValue;
      }
    }
    gtag('event', 'conversion', body);
  });
}

/** Khớp Merchant / dynamic remarketing: vừa item_id (GA4) vừa id (legacy). */
function gtagItemFromProduct(product: Product, primaryId: string, value: number): Record<string, unknown> {
  const item: Record<string, unknown> = {
    item_id: primaryId,
    id: primaryId,
    quantity: 1,
    google_business_vertical: 'retail',
  };
  if (value > 0) item.price = value;
  if (product.name?.trim()) item.item_name = product.name.trim();
  if (product.brand_name?.trim()) item.item_brand = product.brand_name.trim();
  if (product.category?.trim()) item.item_category = product.category.trim();
  if (product.subcategory?.trim()) item.item_category2 = product.subcategory.trim();
  if (typeof window !== 'undefined') {
    const seg = productPathSlugFromApi(product.slug, product.product_id);
    if (seg) item.item_url = `${window.location.origin}/products/${seg}`;
  }
  return item;
}

function fireGoogleAdsPdpConversion(product: Product, primaryId: string, value: number): void {
  const convValue = value > 0 ? value : 1.0;
  fireGoogleAdsConversion('pdp', { value: convValue, items: [gtagItemFromProduct(product, primaryId, value)] });
}

function whenGtagReady(run: () => void): void {
  if (typeof window === 'undefined') return;
  if (getGtag()) {
    run();
    return;
  }
  let done = false;
  const fire = () => {
    if (done) return;
    if (!getGtag()) return;
    done = true;
    run();
  };
  const onEmbeds = () => fire();
  window.addEventListener('188-site-embeds-ready', onEmbeds);
  let ticks = 0;
  const max = 200;
  const iv = window.setInterval(() => {
    fire();
    if (done) {
      window.clearInterval(iv);
      window.removeEventListener('188-site-embeds-ready', onEmbeds);
      return;
    }
    ticks += 1;
    if (ticks >= max) {
      window.clearInterval(iv);
      window.removeEventListener('188-site-embeds-ready', onEmbeds);
    }
  }, 100);
}

function fireGtagEvent(eventName: string, payload: Record<string, unknown>): void {
  const adsSendTo = sendToJoined();
  const ga4SendTo = getGa4SendToTargets();
  if (!adsSendTo && !ga4SendTo.length) return;
  whenGtagReady(() => {
    const gtag = getGtag();
    if (!gtag) return;
    if (adsSendTo) {
      gtag('event', eventName, { send_to: adsSendTo, ...payload });
    }
    ga4SendTo.forEach((send_to) => {
      gtag('event', eventName, { send_to, ...payload });
    });
  });
}

/** Tiếp thị lại Retail cổ điển: page_view + ecomm_*. */
function retailDynamicPageView(payload: {
  ecomm_pagetype: 'home' | 'searchresults' | 'category' | 'product' | 'cart' | 'purchase' | 'other';
  ecomm_prodid?: string | string[];
  ecomm_totalvalue?: number;
}): void {
  const adsSendTo = sendToJoined();
  const ga4SendTo = getGa4SendToTargets();
  if (!adsSendTo && !ga4SendTo.length) return;
  whenGtagReady(() => {
    const gtag = getGtag();
    if (!gtag) return;
    const body: Record<string, unknown> = {
      ecomm_pagetype: payload.ecomm_pagetype,
    };
    if (payload.ecomm_prodid != null) {
      const v = payload.ecomm_prodid;
      body.ecomm_prodid = Array.isArray(v) ? v : v;
    }
    if (payload.ecomm_totalvalue != null && payload.ecomm_totalvalue > 0) {
      body.ecomm_totalvalue = payload.ecomm_totalvalue;
    }
    if (adsSendTo) {
      gtag('event', 'page_view', { send_to: adsSendTo, ...body });
    }
    ga4SendTo.forEach((send_to) => {
      gtag('event', 'page_view', { send_to, ...body });
    });
  });
}

function lineUnitPrice(line: CartItem): number {
  const u =
    (typeof line.unit_price === 'number' && !Number.isNaN(line.unit_price) ? line.unit_price : null) ??
    (typeof line.product_price === 'number' && !Number.isNaN(line.product_price) ? line.product_price : null) ??
    (line.product_data && typeof line.product_data.price === 'number' ? line.product_data.price : null) ??
    0;
  return Number.isFinite(u) ? u : 0;
}

function gtagItemsFromCartLines(lines: CartItem[]): Record<string, unknown>[] {
  return lines.map((line) => {
    const ids = metaContentIdsFromCartItem(line);
    const item_id = ids[0] ?? String(line.product_id);
    const price = lineUnitPrice(line);
    const pd = line.product_data;
    const name =
      (line.product_name && String(line.product_name).trim()) ||
      (pd && typeof pd.name === 'string' ? pd.name.trim() : '') ||
      '';
    const brand = pd && typeof pd.brand_name === 'string' ? pd.brand_name.trim() : '';
    const item: Record<string, unknown> = {
      item_id,
      id: item_id,
      quantity: line.quantity,
      price,
      google_business_vertical: 'retail',
    };
    if (name) item.item_name = name;
    if (brand) item.item_brand = brand;
    return item;
  });
}

function uniqProdIdsFromLines(lines: CartItem[]): string[] {
  const out: string[] = [];
  for (const line of lines) {
    for (const id of metaContentIdsFromCartItem(line)) {
      if (!out.includes(id)) out.push(id);
    }
  }
  return out;
}

let lastRouteRetailKey = '';
let lastRouteRetailAtMs = 0;
const ROUTE_RETAIL_DEDUPE_MS = 2500;

let lastCartRetailFp = '';
let lastCartRetailAtMs = 0;
const CART_RETAIL_DEDUPE_MS = 2000;

let lastViewItemFp = '';
let lastViewItemAtMs = 0;
const VIEW_ITEM_DEDUPE_MS = 2500;

function viewItemFingerprint(product: Product, primaryId: string, value: number): string {
  const sheetId = (product.product_id || '').trim() || String(product.id);
  const pdpConv = conversionSendToFor('pdp') ?? '';
  return `${pdpConv}|${sheetId}|${primaryId}|${value}|${product.name ?? ''}`;
}

function shouldDedupe(ts: number, lastKey: string, key: string, lastAt: number, windowMs: number): boolean {
  return lastKey === key && ts - lastAt < windowMs;
}

/**
 * Theo dõi theo route SPA (trang chủ, danh mục, tìm kiếm, …). Bỏ qua /products/* (xem view_item) và /cart (snapshot giỏ).
 */
export function trackGoogleAdsRouteRetail(pathWithQuery: string): void {
  const sendTo = sendToJoined();
  if (!sendTo) return;

  const [pathOnly, query] = pathWithQuery.split('?');
  const q = query ?? '';
  const sp = new URLSearchParams(q);

  if (pathOnly === '/cart' || /^\/products\/[^/]+\/?$/.test(pathOnly)) {
    return;
  }

  const now = Date.now();
  if (shouldDedupe(now, lastRouteRetailKey, pathWithQuery, lastRouteRetailAtMs, ROUTE_RETAIL_DEDUPE_MS)) {
    return;
  }
  lastRouteRetailKey = pathWithQuery;
  lastRouteRetailAtMs = now;

  let pagetype: 'home' | 'searchresults' | 'category' | 'other' = 'other';
  if (pathOnly === '/') {
    if ((sp.get('q') ?? '').trim()) {
      pagetype = 'searchresults';
    } else if (
      (sp.get('category') ?? '').trim() ||
      (sp.get('subcategory') ?? '').trim() ||
      (sp.get('sub_subcategory') ?? '').trim()
    ) {
      pagetype = 'category';
    } else {
      pagetype = 'home';
    }
  } else if (pathOnly.startsWith('/danh-muc')) {
    pagetype = 'category';
  }

  retailDynamicPageView({ ecomm_pagetype: pagetype });
}

export function trackGoogleAdsViewItemProduct(product: Product): void {
  const ids = metaContentIdsForProduct(product);
  if (!ids.length) return;
  const value = typeof product.price === 'number' && !Number.isNaN(product.price) ? product.price : 0;
  const primaryId = ids[0]!;
  const now = Date.now();
  const fp = viewItemFingerprint(product, primaryId, value);
  if (shouldDedupe(now, lastViewItemFp, fp, lastViewItemAtMs, VIEW_ITEM_DEDUPE_MS)) {
    return;
  }
  lastViewItemFp = fp;
  lastViewItemAtMs = now;

  fireGtagEvent('view_item', {
    currency: GOOGLE_ADS_CURRENCY,
    value,
    items: [gtagItemFromProduct(product, primaryId, value)],
  });
  retailDynamicPageView({
    ecomm_pagetype: 'product',
    ecomm_prodid: primaryId,
    ecomm_totalvalue: value > 0 ? value : undefined,
  });
  fireGoogleAdsPdpConversion(product, primaryId, value);
}

export function trackGoogleAdsAddToCart(item: AddToCartRequest): void {
  const content_ids = metaContentIdsFromAddToCart(item);
  if (!content_ids.length) return;
  const pd =
    item.product_data && typeof item.product_data === 'object' ? (item.product_data as Record<string, unknown>) : {};
  const rawPrice = pd.price;
  const price = (() => {
    if (typeof rawPrice === 'number' && Number.isFinite(rawPrice)) return rawPrice;
    const n = Number(rawPrice);
    return Number.isFinite(n) ? n : 0;
  })();
  const qty = item.quantity;
  const value = price * qty;
  const primaryId = content_ids[0]!;
  const name = pd.name != null ? String(pd.name).trim() : '';
  const brand = pd.brand_name != null ? String(pd.brand_name).trim() : '';

  const addItem: Record<string, unknown> = {
    item_id: primaryId,
    id: primaryId,
    quantity: qty,
    price,
    google_business_vertical: 'retail',
  };
  if (name) addItem.item_name = name;
  if (brand) addItem.item_brand = brand;

  fireGtagEvent('add_to_cart', {
    currency: GOOGLE_ADS_CURRENCY,
    value,
    items: [addItem],
  });
  fireGoogleAdsConversion('add_to_cart', { value, items: [addItem] });
  retailDynamicPageView({
    ecomm_pagetype: 'cart',
    ecomm_prodid: content_ids,
    ecomm_totalvalue: value > 0 ? value : undefined,
  });
}

/** Trang giỏ: ecomm cart + danh sách id (toàn bộ dòng, không chỉ dòng đã chọn). */
export function trackGoogleAdsCartPageView(lines: CartItem[], totalValue: number): void {
  if (!lines.length) return;
  const convCfg = peekGoogleAdsConversionsFingerprint();
  const fp = `${convCfg}|${lines.map((l) => `${l.id}:${l.quantity}`).join(',')}|${totalValue}`;
  const now = Date.now();
  if (shouldDedupe(now, lastCartRetailFp, fp, lastCartRetailAtMs, CART_RETAIL_DEDUPE_MS)) {
    return;
  }
  lastCartRetailFp = fp;
  lastCartRetailAtMs = now;

  const prodIds = uniqProdIdsFromLines(lines);
  const value = Number.isFinite(totalValue) && totalValue > 0 ? totalValue : 0;
  fireGtagEvent('begin_checkout', {
    currency: GOOGLE_ADS_CURRENCY,
    value,
    items: gtagItemsFromCartLines(lines),
  });
  fireGoogleAdsConversion('begin_checkout', {
    value,
    items: gtagItemsFromCartLines(lines),
    cart_lines: lines,
  });
  retailDynamicPageView({
    ecomm_pagetype: 'cart',
    ecomm_prodid: prodIds.length ? prodIds : undefined,
    ecomm_totalvalue: value > 0 ? value : undefined,
  });
}

export function trackGoogleAdsPurchase(params: {
  items: CartItem[];
  value: number;
  orderId?: number | string;
}): void {
  const { items, value, orderId } = params;
  if (!items.length) return;
  const v = Number.isFinite(value) && value > 0 ? value : 0;
  const purchasePayload: Record<string, unknown> = {
    currency: GOOGLE_ADS_CURRENCY,
    value: v,
    ...(orderId != null && String(orderId).trim() !== '' ? { transaction_id: String(orderId) } : {}),
    items: gtagItemsFromCartLines(items),
  };
  applyCwcdToConversionBody(purchasePayload, items);
  fireGtagEvent('purchase', purchasePayload);
  fireGoogleAdsConversion('purchase', {
    value: v,
    items: gtagItemsFromCartLines(items),
    cart_lines: items,
    ...(orderId != null && String(orderId).trim() !== '' ? { transaction_id: String(orderId) } : {}),
  });
  retailDynamicPageView({
    ecomm_pagetype: 'purchase',
    ecomm_prodid: uniqProdIdsFromLines(items),
    ecomm_totalvalue: v > 0 ? v : undefined,
  });
}

/** Đơn chờ cọc — tương đương Meta OrderAwaitingDeposit (không coi là purchase). */
export function trackGoogleAdsOrderAwaitingDeposit(params: {
  items: CartItem[];
  value: number;
  depositAmount?: number | string;
  orderId?: number | string;
}): void {
  const { items, value } = params;
  if (!items.length) return;
  const v = Number.isFinite(value) && value > 0 ? value : 0;
  fireGtagEvent('begin_checkout', {
    currency: GOOGLE_ADS_CURRENCY,
    value: v,
    items: gtagItemsFromCartLines(items),
  });
  retailDynamicPageView({
    ecomm_pagetype: 'cart',
    ecomm_prodid: uniqProdIdsFromLines(items),
    ecomm_totalvalue: v > 0 ? v : undefined,
  });
}

/** Trang thanh toán cọc — tiếp thị lại động + chuyển đổi Ads «trang đặt cọc» (nếu cấu hình). */
export function trackGoogleAdsDepositCheckoutPage(params: {
  items: CartItem[];
  value: number;
  orderId?: number;
}): void {
  const { items, value, orderId } = params;
  if (!items.length) return;
  const v = Number.isFinite(value) && value > 0 ? value : 0;
  fireGoogleAdsConversion('deposit_page', {
    value: v,
    items: gtagItemsFromCartLines(items),
    ...(orderId != null && Number.isFinite(orderId) ? { transaction_id: String(orderId) } : {}),
  });
  retailDynamicPageView({
    ecomm_pagetype: 'cart',
    ecomm_prodid: uniqProdIdsFromLines(items),
    ecomm_totalvalue: v > 0 ? v : undefined,
  });
}
