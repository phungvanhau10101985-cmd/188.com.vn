/**
 * Mở trang chat hosted NanoAI (embed) kèm ngữ cảnh SP — dùng khi không gọi API partner.
 * Base URL: thẻ script `nanoai-chat-widget.js` (`data-chat-url`) hoặc `NEXT_PUBLIC_NANOAI_CHAT_URL`.
 */

import { productPathSlugFromApi } from '@/lib/product-path-slug';
import { clearNanoAiCheckoutOnCart } from '@/lib/nanoai-overlay-pass-through';

export type NanoAiTryOnCtx = {
  sku: string;
  primaryImageUrl: string;
  secondaryImageUrl?: string | null;
  /** Đường dẫn trên site, ví dụ `/products/slug` */
  productPath: string;
  inventoryId?: string | null;
};

/** Nguồn ctx_* khi mở từ feed video — khớp docs NanoAI `ctx_source`. */
export const NANO_AI_CTX_SOURCE_VIDEO_FEED = 'shop_video_feed';

/** Nguồn ctx_* khi mở từ trang chi tiết sản phẩm (sticky bar). */
export const NANO_AI_CTX_SOURCE_PRODUCT_PDP = 'product_detail';

/** Nguồn ctx_* khi mở thử đồ từ tab trên trang chủ (không gắn SP cụ thể). */
export const NANO_AI_CTX_SOURCE_SHOP_HOME = 'shop_home';

export type NanoAiGatewayPayload = {
  sku: string;
  imageUrl: string;
  productUrl?: string;
  inventoryId?: string | null;
};

export type NanoAiConsultOpenResult =
  | { ok: true; mode: 'gateway' }
  | { ok: false; reason: 'no_gateway' | 'missing_sku' | 'missing_image' };

declare global {
  interface Window {
    NanoAIMessagingGateway?: {
      openConsult?: (payload: {
        sku: string;
        imageUrl: string;
        productUrl?: string;
        inventoryId?: string;
      }) => void;
      openTryOn?: (payload: {
        imageUrl: string;
        sku?: string;
        productUrl?: string;
        inventoryId?: string;
      }) => void;
    };
  }
}

const NANOAI_VIDEO_IMAGE_RE = /\.(mp4|webm|mov|m4v)(\?|$)/i;

/** Ảnh hợp lệ cho NanoAI: HTTPS/URL tuyệt đối, không phải link video. */
export function isNanoAiEligibleImageUrl(raw: string): boolean {
  const t = raw.trim();
  if (!t) return false;
  return !NANOAI_VIDEO_IMAGE_RE.test(t);
}

export function getNanoAiMessagingGateway(): Window['NanoAIMessagingGateway'] | null {
  if (typeof window === 'undefined') return null;
  const gw = window.NanoAIMessagingGateway;
  if (!gw || typeof gw !== 'object') return null;
  return gw;
}

type NanoAi188ProductRef = {
  id: number;
  code?: string | null;
  product_id?: string | null;
  slug?: string | null;
  main_image?: string | null;
  images?: string[] | null;
  inventory_id?: string | null;
};

function pickNanoAiProductImageUrl(
  p: NanoAi188ProductRef,
  opts?: { imageUrl?: string | null; origin?: string },
): string {
  const ordered = [opts?.imageUrl, p.main_image, ...(p.images || [])].filter(Boolean) as string[];
  const uniq = [...new Set(ordered.map((u) => u.trim()).filter(Boolean))];
  const origin = opts?.origin ?? (typeof window !== 'undefined' ? window.location.origin : '');
  for (const raw of uniq) {
    if (!isNanoAiEligibleImageUrl(raw)) continue;
    return origin ? absolutizeUrl(raw, origin) : raw;
  }
  return '';
}

/** Chuẩn hóa SP 188 → payload cổng NanoAIMessagingGateway (consult / try-on). */
export function buildNanoAiGatewayPayloadFrom188Product(
  p: NanoAi188ProductRef,
  opts?: { imageUrl?: string | null },
): NanoAiGatewayPayload {
  const sku = (String(p.code ?? '').trim() || String(p.product_id ?? '').trim() || String(p.id)).trim();
  const slugPart =
    productPathSlugFromApi(p.slug ?? undefined, p.product_id ?? undefined) ||
    String(p.product_id ?? '').trim() ||
    String(p.id);
  const productPath = `/products/${slugPart}`;
  const origin = typeof window !== 'undefined' ? window.location.origin : '';
  return {
    sku,
    imageUrl: pickNanoAiProductImageUrl(p, { imageUrl: opts?.imageUrl, origin }),
    productUrl: origin ? absolutizeUrl(productPath, origin) : productPath,
    inventoryId: p.inventory_id ?? null,
  };
}

const NANOAI_GATEWAY_ATTRS = [
  'data-nanoai-consult',
  'data-nanoai-try-on',
  'data-nanoai-sku',
  'data-nanoai-image',
  'data-nanoai-product-url',
  'data-nanoai-inventory-id',
] as const;

/** data-nanoai-* trên nút PDP — widget bắt click khi không gọi JS gateway. */
export function nanoAiGatewayButtonDataset(
  payload: NanoAiGatewayPayload,
  kind: 'consult' | 'try_on',
): Record<string, string> {
  const out: Record<string, string> =
    kind === 'consult' ? { 'data-nanoai-consult': '' } : { 'data-nanoai-try-on': '' };
  if (kind === 'consult' && payload.sku) out['data-nanoai-sku'] = payload.sku;
  if (payload.imageUrl) out['data-nanoai-image'] = payload.imageUrl;
  if (payload.productUrl) out['data-nanoai-product-url'] = payload.productUrl;
  const inv = (payload.inventoryId ?? '').trim();
  if (inv) out['data-nanoai-inventory-id'] = inv;
  return out;
}

function clearNanoAiGatewayAttrs(el: HTMLElement): void {
  for (const attr of NANOAI_GATEWAY_ATTRS) el.removeAttribute(attr);
}

/** Gắn data-nanoai-* lên phần tử (xóa attrs cổng cũ trước). */
export function applyNanoAiGatewayButtonDataset(
  el: HTMLElement,
  payload: NanoAiGatewayPayload,
  kind: 'consult' | 'try_on',
): void {
  clearNanoAiGatewayAttrs(el);
  const dataset = nanoAiGatewayButtonDataset(payload, kind);
  for (const [attr, value] of Object.entries(dataset)) {
    el.setAttribute(attr, value);
  }
}

const NANOAI_CONSULT_LAUNCHER_SELECTORS = [
  '[data-nanoai-consult-launcher]',
  '[data-nanoai-chat-bubble]',
  '[data-nanoai-launcher]',
  '[data-nanoai-chat-launcher]',
  'button.nanoai-chat-launcher',
] as const;

const NANOAI_TRY_ON_LAUNCHER_SELECTORS = [
  '[data-nanoai-try-on-launcher]',
  '[data-nanoai-try-on-launcher] button',
] as const;

function queryElementsDeep(selector: string, root: Document | ShadowRoot = document): HTMLElement[] {
  const found: HTMLElement[] = [];
  try {
    root.querySelectorAll(selector).forEach((el) => {
      if (el instanceof HTMLElement) found.push(el);
    });
    root.querySelectorAll('*').forEach((host) => {
      if (host instanceof Element && host.shadowRoot) {
        found.push(...queryElementsDeep(selector, host.shadowRoot));
      }
    });
  } catch {
    /* closed shadow / perm denied */
  }
  return found;
}

function isVisibleLauncher(el: HTMLElement): boolean {
  const cs = getComputedStyle(el);
  if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') return false;
  const r = el.getBoundingClientRect();
  return r.width >= 28 && r.height >= 28;
}

function looksLikeConsultLauncher(el: HTMLElement): boolean {
  if (el.hasAttribute('data-nanoai-try-on-launcher')) return false;
  if (el.closest('[data-nanoai-try-on-launcher]')) return false;
  const label = (el.getAttribute('aria-label') || el.textContent || '').toLowerCase();
  if (/thử đồ|try[\s-]?on|camera|video/i.test(label)) return false;
  return true;
}

function findNanoAiConsultLaunchers(): HTMLElement[] {
  const found = new Set<HTMLElement>();
  for (const sel of NANOAI_CONSULT_LAUNCHER_SELECTORS) {
    for (const el of queryElementsDeep(sel)) {
      if (!isVisibleLauncher(el)) continue;
      if (!looksLikeConsultLauncher(el)) continue;
      found.add(el);
    }
  }
  return Array.from(found);
}

function findNanoAiTryOnLaunchers(): HTMLElement[] {
  const found = new Set<HTMLElement>();
  for (const sel of NANOAI_TRY_ON_LAUNCHER_SELECTORS) {
    for (const el of queryElementsDeep(sel)) {
      if (!isVisibleLauncher(el)) continue;
      found.add(el);
    }
  }
  for (const el of queryElementsDeep('[data-nanoai-try-on]')) {
    if (!(el instanceof HTMLElement)) continue;
    if (el.matches('button, [role="button"]') && isVisibleLauncher(el)) {
      found.add(el);
    }
  }
  return Array.from(found);
}

/**
 * FAB widget NanoAI (Tư vấn nhắn tin / Thử đồ camera) — gắn data-nanoai-consult vs data-nanoai-try-on
 * theo SP đang xem. Không trộn attrs consult/try-on trên cùng một nút.
 */
export function syncNanoAiWidgetLauncherGatewayButtons(payload: NanoAiGatewayPayload): void {
  if (typeof window === 'undefined') return;

  const consultLaunchers = findNanoAiConsultLaunchers();
  for (const el of consultLaunchers) {
    applyNanoAiGatewayButtonDataset(el, payload, 'consult');
  }

  const tryOnLaunchers = findNanoAiTryOnLaunchers();
  for (const el of tryOnLaunchers) {
    if (consultLaunchers.includes(el)) continue;
    applyNanoAiGatewayButtonDataset(el, payload, 'try_on');
  }
}

/**
 * Mở khung chat tư vấn kèm ngữ cảnh SP — **không** gọi `openConsult` / `auto_consult`.
 * Khách thấy nháp «Gửi mã SP đang xem» và tự gửi; shop trả lời sau khi khách gửi.
 */
export function openNanoAiConsultEmbed(payload: NanoAiGatewayPayload): NanoAiConsultOpenResult {
  if (typeof window === 'undefined') return { ok: false, reason: 'no_gateway' };
  const sku = (payload.sku || '').trim();
  const imageUrl = (payload.imageUrl || '').trim();
  if (!sku) {
    console.warn('[NanoAI] openNanoAiConsultEmbed thiếu sku');
    return { ok: false, reason: 'missing_sku' };
  }
  if (!imageUrl || !isNanoAiEligibleImageUrl(imageUrl)) {
    console.warn('[NanoAI] openNanoAiConsultEmbed thiếu imageUrl hợp lệ (HTTPS, không video)');
    return { ok: false, reason: 'missing_image' };
  }

  const origin = window.location.origin;
  let productPath = '/';
  if (payload.productUrl) {
    try {
      productPath = new URL(payload.productUrl, origin).pathname || '/';
    } catch {
      productPath = payload.productUrl.startsWith('/') ? payload.productUrl : `/${payload.productUrl}`;
    }
  }

  syncNanoAiLoaderScriptProductContext({
    sku,
    primaryImageUrl: imageUrl,
    secondaryImageUrl: null,
    productPath,
    inventoryId: payload.inventoryId ?? null,
  });
  syncNanoAiWidgetLauncherGatewayButtons(payload);

  if (clickNanoAiChatLauncher()) return { ok: true, mode: 'gateway' };
  return { ok: false, reason: 'no_gateway' };
}

/** Chuẩn hóa SP 188 → payload thử đồ NanoAI (hosted). */
export function buildNanoAiTryOnCtxFrom188Product(
  p: NanoAi188ProductRef,
  opts?: { imageUrl?: string | null },
): NanoAiTryOnCtx {
  const sku = (String(p.code ?? '').trim() || String(p.product_id ?? '').trim() || String(p.id)).trim();
  const ordered = [opts?.imageUrl, p.main_image, ...(p.images || [])].filter(Boolean) as string[];
  const uniq = [...new Set(ordered.map((u) => u.trim()).filter(Boolean))];
  const primary = uniq.find((u) => isNanoAiEligibleImageUrl(u)) || '';
  const secondary = uniq.find((u) => u !== primary && isNanoAiEligibleImageUrl(u)) || null;
  const slugPart =
    productPathSlugFromApi(p.slug ?? undefined, p.product_id ?? undefined) ||
    String(p.product_id ?? '').trim() ||
    String(p.id);
  return {
    sku,
    primaryImageUrl: primary,
    secondaryImageUrl: secondary,
    productPath: `/products/${slugPart}`,
    inventoryId: p.inventory_id ?? null,
  };
}

/** Thử đồ từ tab bottom nav trên trang chủ — không ngữ cảnh SP cụ thể. */
export const NANO_AI_TRY_ON_HOME_CTX: NanoAiTryOnCtx = {
  sku: '',
  primaryImageUrl: '',
  secondaryImageUrl: null,
  productPath: '/',
  inventoryId: null,
};

function absolutizeUrl(raw: string, origin: string): string {
  const t = raw.trim();
  if (!t) return '';
  if (/^https?:\/\//i.test(t)) return t;
  try {
    return new URL(t.startsWith('/') ? t : `/${t}`, origin).href;
  } catch {
    return t;
  }
}

const LOADER_SRC_RE = /nanoai-chat-widget|nanoai\.vn\/embed/i;

/** Mọi thẻ script loader NanoAI trên trang (thường một). */
export function findNanoAiChatLoaderScripts(): HTMLScriptElement[] {
  if (typeof document === 'undefined') return [];
  const out: HTMLScriptElement[] = [];
  const list = document.querySelectorAll('script[src]');
  for (let i = 0; i < list.length; i++) {
    const el = list[i] as HTMLScriptElement;
    const src = el.getAttribute('src') || '';
    if (LOADER_SRC_RE.test(src)) out.push(el);
  }
  return out;
}

export function getNanoAiLoaderScriptEl(): HTMLScriptElement | null {
  const arr = findNanoAiChatLoaderScripts();
  return arr[0] ?? null;
}

const CTX_ATTR = {
  sku: 'data-ctx-sku',
  image: 'data-ctx-image',
  image2: 'data-ctx-image-2',
  productUrl: 'data-ctx-product-url',
  inventory: 'data-ctx-inventory',
} as const;

function setCtxAttr(script: HTMLScriptElement, attr: string, value: string | null | undefined) {
  const v = (value ?? '').trim();
  if (v) script.setAttribute(attr, v);
  else script.removeAttribute(attr);
}

/** Đồng bộ ngữ cảnh SP lên thẻ script (widget đọc data-ctx-*). */
export function syncNanoAiLoaderScriptProductContext(ctx: NanoAiTryOnCtx): void {
  if (typeof window === 'undefined') return;
  const scripts = findNanoAiChatLoaderScripts();
  if (scripts.length === 0) return;
  const origin = window.location.origin;
  const sku = (ctx.sku || '').trim();
  const absImg = absolutizeUrl(ctx.primaryImageUrl, origin);
  const absImg2 = ctx.secondaryImageUrl ? absolutizeUrl(ctx.secondaryImageUrl, origin) : '';
  const absPu = absolutizeUrl(ctx.productPath, origin);
  const inv = (ctx.inventoryId ?? '').trim();
  for (const script of scripts) {
    setCtxAttr(script, CTX_ATTR.sku, sku || null);
    setCtxAttr(script, CTX_ATTR.image, absImg || null);
    setCtxAttr(script, CTX_ATTR.image2, absImg2 || null);
    setCtxAttr(script, CTX_ATTR.productUrl, absPu || null);
    setCtxAttr(script, CTX_ATTR.inventory, inv || null);
  }
}

const LAUNCHER_SELECTORS = [
  '[data-nanoai-launcher]',
  '[data-nanoai-chat-launcher]',
  '#nanoai-chat-widget-v1 button',
  '#nanoai-chat-widget-v1 [role="button"]',
  '[id^="nanoai-chat-widget"] button',
  '[id*="nanoai-chat"] button',
  'button.nanoai-chat-launcher',
] as const;

function queryLauncherDeep(selector: string, root: Document | ShadowRoot = document): HTMLElement | null {
  try {
    const hit = root.querySelector(selector);
    if (hit instanceof HTMLElement) return hit;
    const hosts = root.querySelectorAll('*');
    for (let i = 0; i < hosts.length; i++) {
      const el = hosts[i];
      if (el instanceof Element && el.shadowRoot) {
        const inner = queryLauncherDeep(selector, el.shadowRoot);
        if (inner) return inner;
      }
    }
  } catch {
    /* closed shadow / perm denied */
  }
  return null;
}

/** Gõ một nút mở widget nếu nhận diện được trong DOM (kể cả shadow root mở). */
export function clickNanoAiChatLauncher(): boolean {
  if (typeof document === 'undefined') return false;
  for (const sel of LAUNCHER_SELECTORS) {
    const el = queryLauncherDeep(sel);
    if (el) {
      el.click();
      return true;
    }
  }
  try {
    const floating = document.querySelector(
      '[class*="nanoai" i] button, [class*="NanoAi" i] button'
    );
    if (floating instanceof HTMLElement) {
      floating.click();
      return true;
    }
  } catch {
    /* `i` trong attribute selector có thể không hỗ trợ trên engine cũ */
  }
  return false;
}

export function dispatchNanoAiEmbedOpenTryOnSignals(): void {
  if (typeof window === 'undefined') return;
  const names = [
    'nanoai-open-try-on',
    'nanoai:openTryOn',
    'NanoAiOpenTryOn',
    '188-nanoai-open-try-on',
  ] as const;
  const detail = { source: '188-shop' as const };
  for (const name of names) {
    document.dispatchEvent(new CustomEvent(name, { bubbles: true, detail }));
    window.dispatchEvent(new CustomEvent(name, { bubbles: true, detail }));
  }
}

function collectIframesDeep(root: Document | ShadowRoot): HTMLIFrameElement[] {
  const out: HTMLIFrameElement[] = [];
  root.querySelectorAll('iframe').forEach((el) => out.push(el as HTMLIFrameElement));
  root.querySelectorAll('*').forEach((host) => {
    if (host instanceof Element && host.shadowRoot) {
      out.push(...collectIframesDeep(host.shadowRoot));
    }
  });
  return out;
}

/** iframe chat/embed NanoAI: có src messaging, hoặc blank nhưng nằm trong khối nanoai */
function isLikelyNanoAiMessagingIframe(f: HTMLIFrameElement, chatBase: string): boolean {
  const raw = (f.getAttribute('src') || f.src || '').trim();
  if (/nanoai\.vn|\/messaging\/p\//i.test(raw)) return true;
  try {
    const origin = typeof window !== 'undefined' ? window.location.origin : '';
    if (!origin) return false;
    const bu = new URL(chatBase, origin);
    if (raw && raw !== 'about:blank') {
      const u = new URL(raw, origin);
      if (u.hostname === bu.hostname && /\/messaging\//i.test(u.pathname)) return true;
    }
  } catch {
    /* ignore */
  }
  if (!raw || raw === 'about:blank') {
    let p: HTMLElement | null = f.parentElement;
    for (let i = 0; i < 12 && p; i++, p = p.parentElement) {
      const id = p.id || '';
      const cls = typeof p.className === 'string' ? p.className : '';
      const tag = (p.tagName || '').toLowerCase();
      if (/nanoai/i.test(id + cls + tag)) return true;
    }
  }
  return false;
}

/** Iframe đang thực sự hiển thị (widget đóng thường để iframe trong DOM nhưng display:none). */
function isMessagingIframeVisiblyOpen(f: HTMLIFrameElement): boolean {
  const r = f.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return false;
  let el: Element | null = f;
  for (let d = 0; d < 24 && el; d++, el = el.parentElement) {
    const st = window.getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || Number(st.opacity) < 0.05) return false;
  }
  return true;
}

/**
 * Gán src iframe = URL có `open_try_on=1` + ctx_* — widget mặc định hay mở khung chat không query này.
 * `onlyVisible`: chỉ iframe đang mở (tránh patch iframe ẩn sau khi user đóng panel rồi return sớm — lần sau không mở lại được).
 */
export function applyTryOnUrlToNanoAiMessagingIframes(
  targetUrl: string,
  chatBase: string,
  opts?: { onlyVisible?: boolean }
): number {
  if (typeof document === 'undefined') return 0;
  const onlyVisible = opts?.onlyVisible ?? false;
  let n = 0;
  for (const f of collectIframesDeep(document)) {
    if (!isLikelyNanoAiMessagingIframe(f, chatBase)) continue;
    if (onlyVisible && !isMessagingIframeVisiblyOpen(f)) continue;
    try {
      f.src = targetUrl;
      n++;
    } catch {
      /* ignore */
    }
  }
  return n;
}

export type NanoAiTryOnEmbedOpenResult =
  | { ok: true; mode: 'gateway' | 'launcher' | 'new_tab' }
  | { ok: false; reason: 'no_chat_config' | 'launcher_unknown' | 'missing_image' };

function delay(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Popup trên shop + đúng luồng thử đồ: ép iframe messaging dùng URL có `open_try_on=1` và ctx,
 * đồng thời mở launcher nếu khung đang đóng. Chỉ bấm launcher không đủ — iframe vẫn tải chat mặc định.
 */
export async function openNanoAiTryOnEmbed(
  ctx: NanoAiTryOnCtx,
  ctxSource: string = NANO_AI_CTX_SOURCE_VIDEO_FEED
): Promise<NanoAiTryOnEmbedOpenResult> {
  if (typeof window === 'undefined') return { ok: false, reason: 'no_chat_config' };

  const origin = window.location.origin;
  const imageUrl = absolutizeUrl(ctx.primaryImageUrl, origin);
  syncNanoAiLoaderScriptProductContext(ctx);

  const gw = getNanoAiMessagingGateway();
  if (gw?.openTryOn && imageUrl && isNanoAiEligibleImageUrl(imageUrl)) {
    gw.openTryOn({
      imageUrl,
      sku: (ctx.sku || '').trim() || undefined,
      productUrl: absolutizeUrl(ctx.productPath, origin) || undefined,
      inventoryId: (ctx.inventoryId ?? '').trim() || undefined,
    });
    return { ok: true, mode: 'gateway' };
  }
  if (gw?.openTryOn && imageUrl && !isNanoAiEligibleImageUrl(imageUrl)) {
    console.warn('[NanoAI] NanoAIMessagingGateway.openTryOn thiếu imageUrl hợp lệ (HTTPS, không video)');
    return { ok: false, reason: 'missing_image' };
  }

  const base = resolveNanoAiHostedChatBaseUrl();
  if (!base) return { ok: false, reason: 'no_chat_config' };

  const targetUrl = buildNanoAiTryOnHostedUrl(ctx, ctxSource);
  if (!targetUrl) return { ok: false, reason: 'no_chat_config' };

  dispatchNanoAiEmbedOpenTryOnSignals();

  const patchAll = () => applyTryOnUrlToNanoAiMessagingIframes(targetUrl, base);
  const patchVisible = () =>
    applyTryOnUrlToNanoAiMessagingIframes(targetUrl, base, { onlyVisible: true });

  /** Đã mở panel: có ít nhất một iframe messaging nhìn thấy được. */
  const tryOnFrameIsOpen = (): boolean => patchVisible() > 0;

  if (tryOnFrameIsOpen()) {
    patchAll();
    return { ok: true, mode: 'launcher' };
  }

  const clickedOnce = clickNanoAiChatLauncher();

  for (let i = 0; i < 40; i++) {
    await delay(80);
    patchAll();
    if (tryOnFrameIsOpen()) return { ok: true, mode: 'launcher' };
    if (i === 10 || i === 22) clickNanoAiChatLauncher();
  }

  if (!clickedOnce) {
    for (let i = 0; i < 14; i++) {
      await delay(100);
      patchAll();
      if (tryOnFrameIsOpen()) return { ok: true, mode: 'launcher' };
    }
  }

  if (process.env.NEXT_PUBLIC_NANOAI_TRY_ON_OPEN_TAB === '1') {
    window.open(targetUrl, '_blank', 'noopener,noreferrer');
    return { ok: true, mode: 'new_tab' };
  }

  return { ok: false, reason: 'launcher_unknown' };
}

/** URL khung chat (thường …/messaging/p/{slug}?embed=1) — không bắt buộc có sẵn query. */
export function resolveNanoAiHostedChatBaseUrl(): string | null {
  if (typeof window === 'undefined') return null;
  const fromDom = getNanoAiLoaderScriptEl()?.getAttribute('data-chat-url')?.trim();
  if (fromDom) return fromDom;
  const fromEnv = (process.env.NEXT_PUBLIC_NANOAI_CHAT_URL || '').trim();
  return fromEnv || null;
}

export function buildNanoAiTryOnHostedUrl(
  ctx: NanoAiTryOnCtx,
  ctxSource: string = NANO_AI_CTX_SOURCE_VIDEO_FEED
): string | null {
  if (typeof window === 'undefined') return null;
  const base = resolveNanoAiHostedChatBaseUrl();
  if (!base) return null;

  let u: URL;
  try {
    u = new URL(base);
  } catch {
    try {
      u = new URL(base, window.location.origin);
    } catch {
      return null;
    }
  }

  u.searchParams.set('embed', '1');
  u.searchParams.set('open_try_on', '1');

  const origin = window.location.origin;
  const sku = (ctx.sku || '').trim();
  if (sku) u.searchParams.set('ctx_sku', sku);

  const img = absolutizeUrl(ctx.primaryImageUrl, origin);
  if (img) u.searchParams.set('ctx_image', img);

  const img2 = ctx.secondaryImageUrl ? absolutizeUrl(ctx.secondaryImageUrl, origin) : '';
  if (img2) u.searchParams.set('ctx_image_2', img2);

  const pu = absolutizeUrl(ctx.productPath, origin);
  if (pu) u.searchParams.set('ctx_product_url', pu);

  const inv = (ctx.inventoryId ?? '').trim();
  if (inv) u.searchParams.set('ctx_inventory', inv);

  if (sku || img || pu || inv) {
    u.searchParams.set('ctx_source', ctxSource);
  }

  return u.toString();
}

/** Mở NanoAI trong tab mới (chỉ dùng khi cố ý; popup đúng nghĩa = widget/embed). */
export function openNanoAiTryOnHosted(ctx: NanoAiTryOnCtx): boolean {
  const url = buildNanoAiTryOnHostedUrl(ctx);
  if (!url) return false;
  window.open(url, '_blank', 'noopener,noreferrer');
  return true;
}

export const OPEN_NANOAI_CHAT_SESSION_KEY = '188_open_nanoai_chat';
export const CART_ADD_FROM_NANOAI_SESSION_KEY = '188_cart_add_from_nanoai';
export const NANOAI_SHOP_RETURN_PATH_KEY = '188_nanoai_shop_return_path';

/** Đánh dấu luồng mở /cart/add từ NanoAI — dùng khi đóng popup sau thêm giỏ. */
export function markCartAddFromNanoAiFlow(): void {
  if (typeof window === 'undefined') return;
  try {
    sessionStorage.setItem(CART_ADD_FROM_NANOAI_SESSION_KEY, '1');
    const refPath = sameOriginReferrerPath();
    if (refPath) sessionStorage.setItem(NANOAI_SHOP_RETURN_PATH_KEY, refPath);
  } catch {
    /* ignore */
  }
}

export function isCartAddFromNanoAiFlow(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return sessionStorage.getItem(CART_ADD_FROM_NANOAI_SESSION_KEY) === '1';
  } catch {
    return false;
  }
}

export function clearCartAddFromNanoAiFlow(): void {
  if (typeof window === 'undefined') return;
  try {
    sessionStorage.removeItem(CART_ADD_FROM_NANOAI_SESSION_KEY);
    sessionStorage.removeItem(NANOAI_SHOP_RETURN_PATH_KEY);
  } catch {
    /* ignore */
  }
}

/** Xóa cờ luồng NanoAI + cờ checkout giỏ (khi quay chat hoặc rời trang giỏ). */
export function clearNanoAiCartFlowState(): void {
  clearCartAddFromNanoAiFlow();
  clearNanoAiCheckoutOnCart();
}

export function getNanoAiShopReturnPath(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const stored = sessionStorage.getItem(NANOAI_SHOP_RETURN_PATH_KEY);
    if (stored && stored.startsWith('/') && !stored.startsWith('//')) return stored;
  } catch {
    /* ignore */
  }
  return null;
}

/** Sau điều hướng về trang shop, mở launcher chat (gọi từ AppShell). */
export function consumeOpenNanoAiChatPending(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const v = sessionStorage.getItem(OPEN_NANOAI_CHAT_SESSION_KEY);
    if (v !== '1') return false;
    sessionStorage.removeItem(OPEN_NANOAI_CHAT_SESSION_KEY);
    return true;
  } catch {
    return false;
  }
}

function markOpenNanoAiChatAfterNav(): void {
  if (typeof window === 'undefined') return;
  try {
    sessionStorage.setItem(OPEN_NANOAI_CHAT_SESSION_KEY, '1');
  } catch {
    /* ignore */
  }
}

/** Cùng tab, referrer cùng origin và không phải trang cart/add → có thể back về trang chat. */
function canHistoryBackToShopChat(): boolean {
  if (typeof window === 'undefined') return false;
  if (window.history.length <= 1) return false;
  const ref = (document.referrer || '').trim();
  if (!ref || !ref.startsWith(window.location.origin)) return false;
  try {
    const u = new URL(ref);
    if (u.pathname.startsWith('/cart/add/')) return false;
    return true;
  } catch {
    return false;
  }
}

function sameOriginReferrerPath(): string | null {
  if (typeof window === 'undefined') return null;
  const ref = (document.referrer || '').trim();
  if (!ref || !ref.startsWith(window.location.origin)) return null;
  try {
    const u = new URL(ref);
    if (u.pathname.startsWith('/cart/add/')) return null;
    return `${u.pathname}${u.search}${u.hash}`;
  } catch {
    return null;
  }
}

/**
 * Đóng trang /cart/add hoặc popup sau thêm giỏ → quay lại khung chat NanoAI trên shop.
 * Ưu tiên history.back() nếu mở cùng tab từ trang shop; không thì về trang đã lưu + mở launcher.
 */
export function returnToNanoAiChatWidget(): void {
  if (typeof window === 'undefined') return;

  let fromNanoAi = false;
  let storedDest: string | null = null;
  try {
    fromNanoAi = sessionStorage.getItem(CART_ADD_FROM_NANOAI_SESSION_KEY) === '1';
    storedDest = sessionStorage.getItem(NANOAI_SHOP_RETURN_PATH_KEY);
  } catch {
    /* ignore */
  }

  const clearFlowFlags = () => clearNanoAiCartFlowState();

  const path = window.location.pathname;

  if (path === '/cart' && fromNanoAi) {
    clearFlowFlags();
    markOpenNanoAiChatAfterNav();
    window.location.assign(storedDest || '/');
    return;
  }

  if (path.startsWith('/cart/add/') && fromNanoAi && canHistoryBackToShopChat()) {
    clearFlowFlags();
    markOpenNanoAiChatAfterNav();
    window.history.back();
    return;
  }

  if (fromNanoAi && storedDest) {
    clearFlowFlags();
    markOpenNanoAiChatAfterNav();
    window.location.assign(storedDest);
    return;
  }

  if (canHistoryBackToShopChat()) {
    markOpenNanoAiChatAfterNav();
    window.history.back();
    return;
  }

  const dest = sameOriginReferrerPath() || '/';
  markOpenNanoAiChatAfterNav();
  window.location.assign(dest);
}

/** Đọc cờ pending và mở launcher chat (AppShell / pageshow). */
export function consumeAndOpenNanoAiChatLauncher(
  maxAttempts = 12,
  intervalMs = 250,
): (() => void) | undefined {
  if (typeof window === 'undefined') return undefined;
  if (!consumeOpenNanoAiChatPending()) return undefined;
  return tryOpenNanoAiChatLauncherWithRetry(maxAttempts, intervalMs);
}

/** Thử mở launcher sau hydrate (khi vừa quay từ /cart/add). */
export function tryOpenNanoAiChatLauncherWithRetry(maxAttempts = 12, intervalMs = 250): () => void {
  if (typeof window === 'undefined') return () => {};
  let attempts = 0;
  const tick = () => {
    attempts += 1;
    if (clickNanoAiChatLauncher()) return;
    if (attempts < maxAttempts) window.setTimeout(tick, intervalMs);
  };
  const id = window.setTimeout(tick, 120);
  return () => window.clearTimeout(id);
}
