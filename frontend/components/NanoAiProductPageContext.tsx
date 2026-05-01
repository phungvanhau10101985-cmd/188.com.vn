'use client';

import { useEffect } from 'react';

const ATTR = {
  sku: 'data-ctx-sku',
  image: 'data-ctx-image',
  image2: 'data-ctx-image-2',
  productUrl: 'data-ctx-product-url',
  inventory: 'data-ctx-inventory',
} as const;

function findNanoAiLoaderScript(): HTMLScriptElement | null {
  if (typeof document === 'undefined') return null;
  const list = document.querySelectorAll('script[src]');
  for (let i = 0; i < list.length; i++) {
    const el = list[i];
    const src = el.getAttribute('src') || '';
    if (/nanoai-chat-widget|nanoai\.vn\/embed/i.test(src)) {
      return el as HTMLScriptElement;
    }
  }
  return null;
}

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

function setOrRemove(script: HTMLScriptElement, attr: string, value: string | null | undefined) {
  const v = (value ?? '').trim();
  if (v) script.setAttribute(attr, v);
  else script.removeAttribute(attr);
}

export type NanoAiProductPageContextProps = {
  sku: string;
  /** Ảnh đại diện đang hiển thị (URL tương đối hoặc tuyệt đối). */
  primaryImageUrl: string;
  secondaryImageUrl?: string | null;
  /** Đường dẫn trên site, ví dụ `/products/abc-123`. */
  productPath: string;
  inventoryId?: string | null;
};

/**
 * Gắn data-ctx-* lên thẻ script load NanoAI (cùng mục admin / site embeds) để iframe chat nhận ctx_sku, ctx_image, …
 */
export default function NanoAiProductPageContext({
  sku,
  primaryImageUrl,
  secondaryImageUrl,
  productPath,
  inventoryId,
}: NanoAiProductPageContextProps) {
  useEffect(() => {
    if (typeof window === 'undefined') return;
    let cancelled = false;

    const origin = window.location.origin;
    const absProduct = absolutizeUrl(productPath, origin);
    const absImg = absolutizeUrl(primaryImageUrl, origin);
    const absImg2 = secondaryImageUrl ? absolutizeUrl(secondaryImageUrl, origin) : '';

    const apply = (): boolean => {
      const script = findNanoAiLoaderScript();
      if (!script) return false;
      setOrRemove(script, ATTR.sku, sku || null);
      setOrRemove(script, ATTR.image, absImg || null);
      setOrRemove(script, ATTR.image2, absImg2 || null);
      setOrRemove(script, ATTR.productUrl, absProduct || null);
      setOrRemove(script, ATTR.inventory, inventoryId ?? null);
      return true;
    };

    if (apply()) {
      return () => {
        cancelled = true;
      };
    }

    const tid = window.setInterval(() => {
      if (cancelled) return;
      if (apply()) {
        window.clearInterval(tid);
      }
    }, 200);

    const stop = window.setTimeout(() => window.clearInterval(tid), 15_000);

    return () => {
      cancelled = true;
      window.clearInterval(tid);
      window.clearTimeout(stop);
    };
  }, [sku, primaryImageUrl, secondaryImageUrl, productPath, inventoryId]);

  return <span id="copy-code-product" hidden>{sku}</span>;
}
