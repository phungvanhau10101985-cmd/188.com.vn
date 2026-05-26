/**
 * Mở trang chat hosted NanoAI (embed) kèm ngữ cảnh SP — dùng khi không gọi API partner.
 * Base URL: thẻ script `nanoai-chat-widget.js` (`data-chat-url`) hoặc `NEXT_PUBLIC_NANOAI_CHAT_URL`.
 */

import { productPathSlugFromApi } from '@/lib/product-path-slug';

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

/** Chuẩn hóa SP 188 → payload thử đồ NanoAI (hosted). */
export function buildNanoAiTryOnCtxFrom188Product(p: {
  id: number;
  code?: string | null;
  product_id?: string | null;
  slug?: string | null;
  main_image?: string | null;
  images?: string[] | null;
  inventory_id?: string | null;
}): NanoAiTryOnCtx {
  const sku = (String(p.code ?? '').trim() || String(p.product_id ?? '').trim() || String(p.id)).trim();
  const ordered = [p.main_image, ...(p.images || [])].filter(Boolean) as string[];
  const uniq = [...new Set(ordered)];
  const primary = uniq[0] || '';
  const secondary = uniq.find((u) => u !== primary) || null;
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
  | { ok: true; mode: 'launcher' | 'new_tab' }
  | { ok: false; reason: 'no_chat_config' | 'launcher_unknown' };

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
  const base = resolveNanoAiHostedChatBaseUrl();
  if (!base) return { ok: false, reason: 'no_chat_config' };

  const targetUrl = buildNanoAiTryOnHostedUrl(ctx, ctxSource);
  if (!targetUrl) return { ok: false, reason: 'no_chat_config' };

  syncNanoAiLoaderScriptProductContext(ctx);
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

  const clearFlowFlags = () => clearCartAddFromNanoAiFlow();

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
