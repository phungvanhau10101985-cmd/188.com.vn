'use client';

import { useLayoutEffect, useRef } from 'react';
import type { PublicSiteEmbeds } from '@/lib/site-embeds-public';
import {
  clearGoogleAdsSendToAdminOnlyMode,
  setGoogleAdsSendToFromAdmin,
  clearGoogleAdsWebConversionsFromEmbed,
  setGoogleAdsWebConversionsFromEmbed,
} from '@/lib/google-ads-gtag';

/**
 * Script chèn qua innerHTML / createContextualFragment không được trình duyệt thực thi.
 * Tách script → tạo thẻ mới bằng createElement và copy toàn bộ attribute + src/text.
 */
function cloneExecutableScript(old: HTMLScriptElement): HTMLScriptElement {
  const nu = document.createElement('script');
  for (let i = 0; i < old.attributes.length; i++) {
    const a = old.attributes[i];
    if (a) nu.setAttribute(a.name, a.value);
  }
  if (!old.getAttribute('src') && old.textContent != null && old.textContent !== '') {
    nu.textContent = old.textContent;
  }
  return nu;
}

/**
 * Parse một đoạn HTML (có thể nhiều node gốc) vào target; script được thực thi.
 */
function injectHtml(target: ParentNode, html: string, mode: 'append' | 'prepend') {
  const s = html.trim();
  if (!s) return;
  try {
    const doc = new DOMParser().parseFromString(`<body>${s}</body>`, 'text/html');
    if (doc.querySelector('parsererror')) {
      throw new Error('parse');
    }
    const nodes = Array.from(doc.body.childNodes);
    const run = (node: Node) => {
      if (node.nodeName === 'SCRIPT') {
        const el = cloneExecutableScript(node as HTMLScriptElement);
        if (mode === 'append') target.appendChild(el);
        else target.insertBefore(el, target.firstChild);
        return;
      }
      const imported = document.importNode(node, true);
      if (mode === 'append') target.appendChild(imported);
      else target.insertBefore(imported, target.firstChild);
    };
    if (mode === 'prepend') {
      for (let i = nodes.length - 1; i >= 0; i--) run(nodes[i]!);
    } else {
      for (let i = 0; i < nodes.length; i++) run(nodes[i]!);
    }
  } catch {
    try {
      const range = document.createRange();
      target.appendChild(range.createContextualFragment(s));
    } catch {
      /* HTML không hợp lệ — bỏ qua */
    }
  }
}

function appendFragment(target: ParentNode, html: string) {
  injectHtml(target, html, 'append');
}

function prependBodyFragment(html: string) {
  injectHtml(document.body, html, 'prepend');
}

/**
 * Client-only: chèn mã embed vào head/body sau khi React gắn root (layout effect = trước paint).
 *
 * Phải chạy **đồng bộ trong useLayoutEffect** (không defer `setTimeout`): hook con (Analytics, trang deposit)
 * dùng `useEffect` — nếu pixel inject trễ hơn, `fbq` chưa có hoặc sự kiện `188-site-embeds-ready` lệ pha với listener.
 */
export default function SiteEmbedsRootClient({
  embeds,
  headClientRemainders,
}: {
  embeds: PublicSiteEmbeds;
  headClientRemainders: string[];
}) {
  const initial = useRef({ embeds, headClientRemainders });

  useLayoutEffect(() => {
    if (typeof window === 'undefined') return;

    const inject = () => {
      const win = window as Window & { __188_SITE_EMBEDS__?: boolean };
      if (win.__188_SITE_EMBEDS__) return;

      try {
        const {
          embeds: e,
          headClientRemainders: remain,
        } = initial.current;
        const {
          head,
          body_open,
          body_close,
          googleAdsAwIds,
          googleAdsWebConversions,
          googleAdsWebConversionsLegacyPdpOnly,
        } = e;
        if (googleAdsAwIds !== undefined) {
          setGoogleAdsSendToFromAdmin(googleAdsAwIds);
        } else {
          clearGoogleAdsSendToAdminOnlyMode();
        }
        if (googleAdsWebConversions !== undefined) {
          setGoogleAdsWebConversionsFromEmbed(googleAdsWebConversions, {
            legacyPdpOnly: !!googleAdsWebConversionsLegacyPdpOnly,
          });
        } else {
          clearGoogleAdsWebConversionsFromEmbed();
        }

        const ssrHead = document.querySelector('script[data-188-ssr-head]');
        if (ssrHead) {
          remain.forEach((h) => appendFragment(document.head, h));
        } else {
          head.forEach((h) => appendFragment(document.head, h));
        }

        for (let i = body_open.length - 1; i >= 0; i--) prependBodyFragment(body_open[i] ?? '');
        body_close.forEach((b) => appendFragment(document.body, b));
        win.__188_SITE_EMBEDS__ = true;
        window.dispatchEvent(new Event('188-site-embeds-ready'));
      } catch (err) {
        console.warn('[SiteEmbeds] inject failed', err);
      }
    };

    inject();
  }, []);

  return null;
}
