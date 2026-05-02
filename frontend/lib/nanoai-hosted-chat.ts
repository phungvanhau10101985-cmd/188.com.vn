/**
 * Mở trang chat hosted NanoAI (embed) kèm ngữ cảnh SP — dùng khi không gọi API partner.
 * Base URL: thẻ script `nanoai-chat-widget.js` (`data-chat-url`) hoặc `NEXT_PUBLIC_NANOAI_CHAT_URL`.
 */

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

/**
 * Gán src iframe = URL có `open_try_on=1` + ctx_* — widget mặc định hay mở khung chat không query này.
 * @returns số iframe đã gán (thường 1).
 */
export function applyTryOnUrlToNanoAiMessagingIframes(targetUrl: string, chatBase: string): number {
  if (typeof document === 'undefined') return 0;
  let n = 0;
  for (const f of collectIframesDeep(document)) {
    if (!isLikelyNanoAiMessagingIframe(f, chatBase)) continue;
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
export async function openNanoAiTryOnEmbed(ctx: NanoAiTryOnCtx): Promise<NanoAiTryOnEmbedOpenResult> {
  if (typeof window === 'undefined') return { ok: false, reason: 'no_chat_config' };
  const base = resolveNanoAiHostedChatBaseUrl();
  if (!base) return { ok: false, reason: 'no_chat_config' };

  const targetUrl = buildNanoAiTryOnHostedUrl(ctx);
  if (!targetUrl) return { ok: false, reason: 'no_chat_config' };

  syncNanoAiLoaderScriptProductContext(ctx);
  dispatchNanoAiEmbedOpenTryOnSignals();

  let sawPatch = false;
  const patch = (): boolean => {
    const k = applyTryOnUrlToNanoAiMessagingIframes(targetUrl, base);
    if (k > 0) sawPatch = true;
    return sawPatch;
  };

  if (patch()) return { ok: true, mode: 'launcher' };

  const clickedOnce = clickNanoAiChatLauncher();

  for (let i = 0; i < 40; i++) {
    await delay(80);
    if (patch()) return { ok: true, mode: 'launcher' };
    if (i === 10 || i === 22) clickNanoAiChatLauncher();
  }

  if (!clickedOnce) {
    for (let i = 0; i < 14; i++) {
      await delay(100);
      if (patch()) return { ok: true, mode: 'launcher' };
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
