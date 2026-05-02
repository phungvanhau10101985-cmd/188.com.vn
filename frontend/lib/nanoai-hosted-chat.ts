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

export function getNanoAiLoaderScriptEl(): HTMLScriptElement | null {
  if (typeof document === 'undefined') return null;
  const list = document.querySelectorAll('script[src]');
  for (let i = 0; i < list.length; i++) {
    const el = list[i] as HTMLScriptElement;
    const src = el.getAttribute('src') || '';
    if (/nanoai-chat-widget|nanoai\.vn\/embed/i.test(src)) {
      return el;
    }
  }
  return null;
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

/** @returns true nếu đã mở tab mới */
export function openNanoAiTryOnHosted(ctx: NanoAiTryOnCtx): boolean {
  const url = buildNanoAiTryOnHostedUrl(ctx);
  if (!url) return false;
  window.open(url, '_blank', 'noopener,noreferrer');
  return true;
}
