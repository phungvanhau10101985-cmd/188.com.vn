import type { AddToCartRequest } from '@/features/cart/types/cart';
import type { CartItem } from '@/features/cart/types/cart';
import type { Product, ProductInfoJSON } from '@/types/api';
import { newMetaEventId, sendFacebookCapiFromBrowser } from '@/lib/facebook-capi-client';

export const META_PIXEL_CURRENCY = 'VND';

type FbqFn = (...args: unknown[]) => void;
type StandardEventName = 'PageView' | 'ViewContent' | 'AddToCart' | 'Purchase';
type PixelEventMode = 'standard' | 'custom';

/**
 * Tránh ViewContent trùng (Meta cảnh báo): React 18 Strict Mode gọi useEffect 2 lần khi dev;
 * hoặc handler gọi đúp. Chỉ bỏ qua khi cùng payload trong cửa sổ ngắn.
 */
let lastViewContentFingerprint: string | null = null;
let lastViewContentAtMs = 0;
const VIEW_CONTENT_DEDUPE_MS = 2500;

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

function shouldDedupeViewContent(fp: string, now: number): boolean {
  if (lastViewContentFingerprint === fp && now - lastViewContentAtMs < VIEW_CONTENT_DEDUPE_MS) {
    return true;
  }
  lastViewContentFingerprint = fp;
  lastViewContentAtMs = now;
  return false;
}

function getFbq(): FbqFn | undefined {
  if (typeof window === 'undefined') return undefined;
  const fbq = (window as Window & { fbq?: FbqFn }).fbq;
  return typeof fbq === 'function' ? fbq : undefined;
}

/** Đợi fbq sau khi script Pixel chèn (hydrate). */
function whenFbqReady(run: () => void): void {
  if (typeof window === 'undefined') return;
  if (getFbq()) {
    run();
    return;
  }
  let ticks = 0;
  const max = 40;
  const id = window.setInterval(() => {
    ticks += 1;
    if (getFbq()) {
      window.clearInterval(id);
      run();
    } else if (ticks >= max) {
      window.clearInterval(id);
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

function skuFromProductInfo(pi: Product['product_info']): string | null {
  if (!pi) return null;
  if (typeof pi === 'string') {
    try {
      const j = JSON.parse(pi) as ProductInfoJSON | null;
      const s = j?.product_info?.sku;
      return typeof s === 'string' && s.trim() ? s.trim() : null;
    } catch {
      return null;
    }
  }
  const o = pi as ProductInfoJSON;
  const s = o?.product_info?.sku;
  return typeof s === 'string' && s.trim() ? s.trim() : null;
}

/**
 * content_ids cho Meta — khớp file import: cột `id` → `product.product_id`; cột `sku` → `code` / product_info.sku.
 * Nếu thiếu `product_id` (SP cũ), tạm dùng id DB để không gãy pixel.
 */
export function metaContentIdsForProduct(p: Pick<Product, 'id' | 'code' | 'product_id' | 'product_info'>): string[] {
  const fromSheetId = (p.product_id || '').trim();
  const remarketingId = fromSheetId || String(p.id);
  const fromJson = skuFromProductInfo(p.product_info);
  const sku = (fromJson || (p.code || '').trim()).trim();
  return uniqIds([remarketingId, sku].filter(Boolean));
}

export function metaContentIdsFromAddToCart(item: AddToCartRequest): string[] {
  const pd =
    item.product_data && typeof item.product_data === 'object' ? (item.product_data as Record<string, unknown>) : {};
  const fromSheetId = pd.product_id != null ? String(pd.product_id).trim() : '';
  const remarketingId = fromSheetId || String(item.product_id);
  const sku = (pd.code != null ? String(pd.code).trim() : '').trim();
  return uniqIds([remarketingId, sku].filter(Boolean));
}

export function metaContentIdsFromCartItem(
  item: Pick<CartItem, 'product_id' | 'product_code' | 'product_data'>
): string[] {
  const pd =
    item.product_data && typeof item.product_data === 'object' ? (item.product_data as Record<string, unknown>) : {};
  const fromSheetId = pd.product_id != null ? String(pd.product_id).trim() : '';
  const remarketingId = fromSheetId || String(item.product_id);
  const sku =
    (item.product_code != null && String(item.product_code).trim()) ||
    (pd.code != null ? String(pd.code).trim() : '') ||
    '';
  return uniqIds([remarketingId, sku].filter(Boolean));
}

function firePixelAndCapi(
  eventName: StandardEventName | string,
  customData: Record<string, unknown>,
  opts?: { keepalive?: boolean; sendCapi?: boolean; mode?: PixelEventMode }
): void {
  const eventId = newMetaEventId(eventName);
  whenFbqReady(() => {
    const fbq = getFbq();
    if (fbq) {
      fbq(opts?.mode === 'custom' ? 'trackCustom' : 'track', eventName, customData, { eventID: eventId });
    }
  });
  if (opts?.sendCapi === false) {
    return;
  }
  const custom_data = Object.keys(customData).length ? customData : undefined;
  void sendFacebookCapiFromBrowser(
    {
      event_name: eventName,
      event_id: eventId,
      custom_data,
    },
    { keepalive: opts?.keepalive === true }
  );
}

function cartMetaCustomData(params: {
  items: CartItem[];
  value: number;
  orderId?: number | string;
  extra?: Record<string, unknown>;
}): Record<string, unknown> {
  const { items, value, orderId, extra } = params;
  const contents = items.map((line) => {
    const ids = metaContentIdsFromCartItem(line);
    const unit =
      (typeof line.unit_price === 'number' && !Number.isNaN(line.unit_price) ? line.unit_price : null) ??
      (typeof line.product_price === 'number' && !Number.isNaN(line.product_price) ? line.product_price : null) ??
      (line.product_data && typeof line.product_data.price === 'number' ? line.product_data.price : null) ??
      0;
    const primaryId = ids[0] ?? String(line.product_id);
    return { id: primaryId, quantity: line.quantity, item_price: unit };
  });

  const content_ids = uniqIds(items.flatMap((line) => metaContentIdsFromCartItem(line)));
  const num_items = items.reduce((n, line) => n + line.quantity, 0);

  return {
    value,
    currency: META_PIXEL_CURRENCY,
    content_type: 'product',
    content_ids,
    contents,
    num_items,
    ...(orderId != null && orderId !== '' ? { order_id: String(orderId) } : {}),
    ...(extra || {}),
  };
}

let lastPageViewRouteKey: string | null = null;
let lastPageViewAtMs = 0;
const PAGE_VIEW_DEDUPE_MS = 2500;

export function trackMetaPageView(routeKey?: string): void {
  const key =
    (routeKey != null && String(routeKey).trim()) ||
    (typeof window !== 'undefined' ? `${window.location.pathname}${window.location.search}` : '') ||
    '/';
  const now = Date.now();
  if (lastPageViewRouteKey === key && now - lastPageViewAtMs < PAGE_VIEW_DEDUPE_MS) {
    return;
  }
  lastPageViewRouteKey = key;
  lastPageViewAtMs = now;
  /** Chỉ Pixel — gửi thêm CAPI PageView khiến Pixel Helper thường báo 2× PageView (browser + server). */
  firePixelAndCapi('PageView', {}, { sendCapi: false });
}

export function trackMetaViewContentProduct(product: Product): void {
  const content_ids = metaContentIdsForProduct(product);
  if (!content_ids.length) return;
  const value = typeof product.price === 'number' && !Number.isNaN(product.price) ? product.price : 0;
  const category = product.category || product.subcategory;
  const fp = viewContentFingerprint(product, content_ids, value, category);
  if (shouldDedupeViewContent(fp, Date.now())) return;

  const primaryId = content_ids[0]!;

  const customData: Record<string, unknown> = {
    content_ids,
    content_type: 'product',
    content_name: product.name,
    ...(category ? { content_category: category } : {}),
    value,
    currency: META_PIXEL_CURRENCY,
    contents: [{ id: primaryId, quantity: 1, item_price: value }],
  };
  firePixelAndCapi('ViewContent', customData);
}

export function trackMetaAddToCart(item: AddToCartRequest): void {
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
  const name = pd.name != null ? String(pd.name) : undefined;

  const customData: Record<string, unknown> = {
    content_ids,
    content_type: 'product',
    ...(name ? { content_name: name } : {}),
    value,
    currency: META_PIXEL_CURRENCY,
    contents: [{ id: primaryId, quantity: qty, item_price: price }],
  };
  firePixelAndCapi('AddToCart', customData, { keepalive: true });
}

export function trackMetaPurchase(params: {
  items: CartItem[];
  value: number;
  orderId?: number | string;
}): void {
  const { items, value, orderId } = params;
  if (!items.length) return;

  const customData = cartMetaCustomData({ items, value, orderId });
  firePixelAndCapi('Purchase', customData, { keepalive: true });
}

export function trackMetaOrderAwaitingDeposit(params: {
  items: CartItem[];
  value: number;
  depositAmount?: number | string;
  orderId?: number | string;
}): void {
  const { items, value, depositAmount, orderId } = params;
  if (!items.length) return;

  const depositValue = depositAmount != null ? Number(depositAmount) : undefined;
  const customData = cartMetaCustomData({
    items,
    value,
    orderId,
    extra: {
      order_status: 'waiting_deposit',
      deposit_required: true,
      ...(depositValue != null && Number.isFinite(depositValue) ? { deposit_amount: depositValue } : {}),
    },
  });
  firePixelAndCapi('OrderAwaitingDeposit', customData, { keepalive: true, mode: 'custom' });
}

/** Dòng đơn từ API `getOrder` — map sang CartItem để Purchase/Meta giữ đúng product_id & giá. */
export type OrderApiLineForMeta = {
  id: number;
  product_id: number;
  product_name?: string;
  product_code?: string;
  quantity: number;
  unit_price: number | string;
  total_price?: number | string;
};

export function cartItemsFromOrderLines(lines: OrderApiLineForMeta[]): CartItem[] {
  return (lines || [])
    .filter((l) => l != null && Number.isFinite(Number(l.product_id)))
    .map((line) => {
      const unit = typeof line.unit_price === 'number' ? line.unit_price : Number(line.unit_price);
      const totalRaw = line.total_price;
      const total =
        typeof totalRaw === 'number'
          ? totalRaw
          : totalRaw != null && String(totalRaw).trim() !== ''
            ? Number(totalRaw)
            : Number.isFinite(unit)
              ? unit * line.quantity
              : 0;
      const u = Number.isFinite(unit) ? unit : 0;
      const t = Number.isFinite(total) ? total : 0;
      const pid = Number(line.product_id);
      return {
        id: line.id,
        product_id: pid,
        quantity: line.quantity,
        unit_price: u,
        total_price: t,
        ...(line.product_code ? { product_code: line.product_code } : {}),
        product_data: {
          id: pid,
          name: line.product_name,
          price: u,
        },
      };
    });
}

/**
 * Fallback khi GET đơn không có `items` hoặc map rỗng — tránh không bắn Purchase/Pixel+CAPI sau cọc.
 * content_ids ưu tiên `product_code` = mã đơn (vd. DH024).
 */
export function cartItemsFromOrderOrFallback(
  order: {
    id: number;
    order_code?: string | null;
    total_amount?: number | string | null;
  },
  lines?: OrderApiLineForMeta[] | null
): CartItem[] {
  const mapped = cartItemsFromOrderLines(lines ?? []);
  if (mapped.length) return mapped;

  const rawTot = order.total_amount;
  const total =
    typeof rawTot === 'number'
      ? Number.isFinite(rawTot)
        ? rawTot
        : 0
      : rawTot != null && String(rawTot).trim() !== ''
        ? Number(rawTot)
        : 0;
  if (!(Number.isFinite(total) && total > 0)) return [];

  const code = String(order.order_code ?? order.id ?? '').trim() || String(order.id);
  const pid = Number(order.id);
  const product_id = Number.isFinite(pid) && pid > 0 ? pid : 1;

  return [
    {
      id: product_id,
      product_id,
      quantity: 1,
      unit_price: total,
      total_price: total,
      ...(code ? { product_code: code } : {}),
      product_data: { id: product_id, name: `Đơn ${code}`, price: total },
    },
  ];
}
