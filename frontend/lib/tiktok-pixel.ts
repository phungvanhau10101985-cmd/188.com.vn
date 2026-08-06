import type { AddToCartRequest } from '@/features/cart/types/cart';
import type { CartItem } from '@/features/cart/types/cart';
import type { Product } from '@/types/api';
import {
  META_PIXEL_CURRENCY,
  metaContentIdsForProduct,
  metaContentIdsFromAddToCart,
  metaContentIdsFromCartItem,
  metaPurchaseEventId,
} from '@/lib/meta-pixel';

export const TIKTOK_PIXEL_CURRENCY = META_PIXEL_CURRENCY;

type TtqTrackFn = (
  event: string,
  data?: Record<string, unknown>,
  options?: { event_id?: string }
) => void;
type TtqPageFn = () => void;
type TtqApi = TtqTrackFn & { page?: TtqPageFn; track?: TtqTrackFn };

let lastViewContentFingerprint: string | null = null;
let lastViewContentAtMs = 0;
const VIEW_CONTENT_DEDUPE_MS = 2500;

let lastAddToCartFingerprint: string | null = null;
let lastAddToCartAtMs = 0;
const ADD_TO_CART_DEDUPE_MS = 2000;

let lastInitiateCheckoutFingerprint: string | null = null;
let lastInitiateCheckoutAtMs = 0;
const INITIATE_CHECKOUT_DEDUPE_MS = 3000;

const PAGE_VIEW_DEDUPE_MS = 3500;

type TikTokPageViewWindow = Window & {
  __188TikTokPvKey?: string;
  __188TikTokPvAt?: number;
};

function getTtq(): TtqApi | undefined {
  if (typeof window === 'undefined') return undefined;
  const ttq = (window as Window & { ttq?: TtqApi }).ttq;
  return ttq && typeof ttq.track === 'function' ? ttq : undefined;
}

function whenTtqReady(run: () => void): void {
  if (typeof window === 'undefined') return;
  if (getTtq()) {
    run();
    return;
  }
  let done = false;
  const fire = () => {
    if (done) return;
    const ttq = getTtq();
    if (!ttq) return;
    done = true;
    run();
  };
  const onEmbeds = () => fire();
  window.addEventListener('188-site-embeds-ready', onEmbeds);
  let ticks = 0;
  const max = 200;
  const id = window.setInterval(() => {
    fire();
    if (done) {
      window.clearInterval(id);
      window.removeEventListener('188-site-embeds-ready', onEmbeds);
      return;
    }
    ticks += 1;
    if (ticks >= max) {
      window.clearInterval(id);
      window.removeEventListener('188-site-embeds-ready', onEmbeds);
      window.requestAnimationFrame(() => fire());
    }
  }, 100);
}

function uniqIds(ids: string[]): string[] {
  const out: string[] = [];
  for (const raw of ids) {
    const s = (raw ?? '').trim();
    if (!s) continue;
    if (!out.includes(s)) out.push(s);
  }
  return out;
}

function tiktokContentsFromCartItems(items: CartItem[]): Array<Record<string, unknown>> {
  return items.map((line) => {
    const ids = metaContentIdsFromCartItem(line);
    const unit =
      (typeof line.unit_price === 'number' && !Number.isNaN(line.unit_price) ? line.unit_price : null) ??
      (typeof line.product_price === 'number' && !Number.isNaN(line.product_price) ? line.product_price : null) ??
      (line.product_data && typeof line.product_data.price === 'number' ? line.product_data.price : null) ??
      0;
    const primaryId = ids[0] ?? String(line.product_id);
    const pd =
      line.product_data && typeof line.product_data === 'object'
        ? (line.product_data as Record<string, unknown>)
        : {};
    const name = pd.name != null ? String(pd.name).trim() : '';
    return {
      content_id: primaryId,
      content_type: 'product',
      ...(name ? { content_name: name } : {}),
      quantity: line.quantity,
      price: unit,
    };
  });
}

function tiktokCartProperties(params: {
  items: CartItem[];
  value: number;
  orderId?: number | string;
  extra?: Record<string, unknown>;
}): Record<string, unknown> {
  const { items, value, orderId, extra } = params;
  const contents = tiktokContentsFromCartItems(items);
  const contentIds = uniqIds(items.flatMap((line) => metaContentIdsFromCartItem(line)));
  const numItems = items.reduce((n, line) => n + line.quantity, 0);

  return {
    value,
    currency: TIKTOK_PIXEL_CURRENCY,
    content_type: 'product',
    ...(contentIds[0] ? { content_id: contentIds[0] } : {}),
    contents,
    quantity: numItems,
    ...(orderId != null && orderId !== '' ? { order_id: String(orderId) } : {}),
    ...(extra || {}),
  };
}

function fireTikTokTrack(
  eventName: string,
  properties: Record<string, unknown>,
  opts?: { sync?: boolean; eventId?: string }
): void {
  const run = () => {
    const ttq = getTtq();
    if (!ttq?.track) return;
    const options = opts?.eventId ? { event_id: opts.eventId } : undefined;
    ttq.track(eventName, properties, options);
  };
  if (opts?.sync && getTtq()) {
    run();
  } else {
    whenTtqReady(run);
  }
}

function addToCartFingerprint(item: AddToCartRequest): string {
  const ids = metaContentIdsFromAddToCart(item);
  return `${ids.join(',')}|${item.quantity}|${item.selected_size ?? ''}|${item.selected_color ?? ''}`;
}

function viewContentFingerprint(
  product: Product,
  contentIds: string[],
  value: number,
  category: string | undefined
): string {
  const cat = category ?? '';
  const sheetId = (product.product_id || '').trim() || String(product.id);
  return `${sheetId}|${value}|${cat}|${contentIds.join(',')}|${product.name ?? ''}`;
}

function shouldSkipTikTokPageView(key: string, now: number, skipDedupe?: boolean): boolean {
  if (skipDedupe) return false;
  if (typeof window === 'undefined') return false;
  const w = window as TikTokPageViewWindow;
  if (
    w.__188TikTokPvKey === key &&
    w.__188TikTokPvAt != null &&
    now - w.__188TikTokPvAt < PAGE_VIEW_DEDUPE_MS
  ) {
    return true;
  }
  w.__188TikTokPvKey = key;
  w.__188TikTokPvAt = now;
  return false;
}

/** SPA route change — ttq.page() sau lần load đầu (base embed đã gọi ttq.page()). */
export function trackTikTokPageView(
  routeKey?: string,
  opts?: { skipDedupe?: boolean }
): void {
  const key =
    (routeKey != null && String(routeKey).trim()) ||
    (typeof window !== 'undefined' ? `${window.location.pathname}${window.location.search}` : '') ||
    '/';
  const now = Date.now();
  if (shouldSkipTikTokPageView(key, now, opts?.skipDedupe)) {
    return;
  }
  whenTtqReady(() => {
    const ttq = getTtq();
    ttq?.page?.();
  });
}

export function trackTikTokViewContentProduct(
  product: Product,
  opts?: { routeKey?: string; skipDedupe?: boolean }
): void {
  const contentIds = metaContentIdsForProduct(product);
  if (!contentIds.length) return;
  const value = typeof product.price === 'number' && !Number.isNaN(product.price) ? product.price : 0;
  const category = product.category || product.subcategory;
  const fp = viewContentFingerprint(product, contentIds, value, category);
  const now = Date.now();
  if (!opts?.skipDedupe && lastViewContentFingerprint === fp && now - lastViewContentAtMs < VIEW_CONTENT_DEDUPE_MS) {
    return;
  }
  lastViewContentFingerprint = fp;
  lastViewContentAtMs = now;

  const primaryId = contentIds[0]!;
  const properties: Record<string, unknown> = {
    content_id: primaryId,
    content_type: 'product',
    content_name: product.name,
    ...(category ? { content_category: category } : {}),
    value,
    currency: TIKTOK_PIXEL_CURRENCY,
    contents: [
      {
        content_id: primaryId,
        content_type: 'product',
        content_name: product.name,
        quantity: 1,
        price: value,
      },
    ],
  };
  fireTikTokTrack('ViewContent', properties, { sync: true });
}

let lastGroupViewContentFingerprint: string | null = null;
let lastGroupViewContentAtMs = 0;

/** ViewContent cho trang hiển thị nhiều sản phẩm cùng lúc (ladipage theo danh mục/nhiều SP chọn). */
export function trackTikTokViewContentProducts(
  products: Product[],
  opts?: { contentName?: string; skipDedupe?: boolean }
): void {
  const ids = uniqIds(products.flatMap((p) => metaContentIdsForProduct(p)));
  if (!ids.length) return;
  const value = products.reduce((sum, p) => sum + (typeof p.price === 'number' ? p.price : 0), 0);
  const fp = `${ids.join(',')}|${products.length}|${value}`;
  const now = Date.now();
  if (!opts?.skipDedupe && lastGroupViewContentFingerprint === fp && now - lastGroupViewContentAtMs < VIEW_CONTENT_DEDUPE_MS) {
    return;
  }
  lastGroupViewContentFingerprint = fp;
  lastGroupViewContentAtMs = now;

  const properties: Record<string, unknown> = {
    content_type: 'product',
    ...(opts?.contentName ? { content_name: opts.contentName } : {}),
    value,
    currency: TIKTOK_PIXEL_CURRENCY,
    contents: products.map((p) => {
      const pIds = metaContentIdsForProduct(p);
      return {
        content_id: pIds[0] || String(p.id),
        content_type: 'product',
        content_name: p.name,
        quantity: 1,
        price: p.price || 0,
      };
    }),
  };
  fireTikTokTrack('ViewContent', properties, { sync: true });
}

export function trackTikTokAddToCart(item: AddToCartRequest): void {
  const contentIds = metaContentIdsFromAddToCart(item);
  if (!contentIds.length) return;
  const fp = addToCartFingerprint(item);
  const now = Date.now();
  if (lastAddToCartFingerprint === fp && now - lastAddToCartAtMs < ADD_TO_CART_DEDUPE_MS) {
    return;
  }
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
  const primaryId = contentIds[0]!;
  const name = pd.name != null ? String(pd.name) : undefined;

  const properties: Record<string, unknown> = {
    content_id: primaryId,
    content_type: 'product',
    ...(name ? { content_name: name } : {}),
    value,
    currency: TIKTOK_PIXEL_CURRENCY,
    contents: [
      {
        content_id: primaryId,
        content_type: 'product',
        ...(name ? { content_name: name } : {}),
        quantity: qty,
        price,
      },
    ],
  };
  lastAddToCartFingerprint = fp;
  lastAddToCartAtMs = now;
  fireTikTokTrack('AddToCart', properties, { sync: true });
}

/** Trang giỏ / bắt đầu checkout. */
export function trackTikTokInitiateCheckout(params: {
  items: CartItem[];
  value: number;
  orderId?: number | string;
  extra?: Record<string, unknown>;
}): void {
  const { items, value, orderId, extra } = params;
  if (!items.length) return;
  const fp = `${items.map((l) => `${l.id}:${l.quantity}`).join(',')}|${value}|${orderId ?? ''}|${JSON.stringify(extra ?? {})}`;
  const now = Date.now();
  if (lastInitiateCheckoutFingerprint === fp && now - lastInitiateCheckoutAtMs < INITIATE_CHECKOUT_DEDUPE_MS) {
    return;
  }
  lastInitiateCheckoutFingerprint = fp;
  lastInitiateCheckoutAtMs = now;

  const properties = tiktokCartProperties({ items, value, orderId, extra });
  fireTikTokTrack('InitiateCheckout', properties, { sync: true });
}

/** Đơn đã tạo, chờ cọc — tương đương Meta OrderAwaitingDeposit. */
export function trackTikTokPlaceAnOrder(params: {
  items: CartItem[];
  value: number;
  depositAmount?: number | string;
  orderId?: number | string;
}): void {
  const { items, value, depositAmount, orderId } = params;
  if (!items.length) return;

  const depositValue = depositAmount != null ? Number(depositAmount) : undefined;
  const properties = tiktokCartProperties({
    items,
    value,
    orderId,
    extra: {
      order_status: 'waiting_deposit',
      deposit_required: true,
      ...(depositValue != null && Number.isFinite(depositValue) ? { deposit_amount: depositValue } : {}),
    },
  });
  fireTikTokTrack('PlaceAnOrder', properties, { sync: true });
}

/** Thanh toán hoàn tất (COD hoặc sau cọc) — tương đương Meta Purchase. */
export function trackTikTokCompletePayment(params: {
  items: CartItem[];
  value: number;
  orderId?: number | string;
}): void {
  const { items, value, orderId } = params;
  if (!items.length) return;

  const properties = tiktokCartProperties({ items, value, orderId });
  fireTikTokTrack('CompletePayment', properties, {
    sync: true,
    eventId: orderId != null && orderId !== '' ? metaPurchaseEventId(orderId) : undefined,
  });
}

/** Trang thanh toán cọc — InitiateCheckout với ngữ cảnh deposit. */
export function trackTikTokDepositCheckoutPage(params: {
  items: CartItem[];
  value: number;
  orderId?: number | string;
  depositAmount?: number | string;
}): void {
  const { items, value, orderId, depositAmount } = params;
  if (!items.length) return;
  const depositValue = depositAmount != null ? Number(depositAmount) : undefined;
  trackTikTokInitiateCheckout({
    items,
    value,
    orderId,
    extra: {
      deposit_page: true,
      ...(depositValue != null && Number.isFinite(depositValue) ? { deposit_amount: depositValue } : {}),
    },
  });
}
