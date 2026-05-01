'use client';

import { useEffect, useRef } from 'react';
import type { PublicSiteEmbeds } from '@/lib/site-embeds-public';

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
 * Client-only: chèn mã embed vào head/body sau hydrate (tránh lỗi hooks/React kép khi SSR).
 */
export default function SiteEmbedsRootClient({ embeds }: { embeds: PublicSiteEmbeds }) {
  const initial = useRef(embeds);

  useEffect(() => {
    const inject = () => {
      const win = typeof window !== "undefined" ? (window as Window & { __188_SITE_EMBEDS__?: boolean }) : null;
      if (!win || win.__188_SITE_EMBEDS__) return;
      win.__188_SITE_EMBEDS__ = true;

      const { head, body_open, body_close } = initial.current;

      head.forEach((h) => appendFragment(document.head, h));

      for (let i = body_open.length - 1; i >= 0; i--) prependBodyFragment(body_open[i] ?? "");
      body_close.forEach((b) => appendFragment(document.body, b));
    };

    const w = typeof window !== "undefined" ? window : null;
    if (!w) return;

    const ric = w.requestIdleCallback?.bind(w);
    let idleId: ReturnType<typeof requestIdleCallback> | undefined;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    if (ric) {
      idleId = ric(() => inject(), { timeout: 3200 });
    } else {
      timeoutId = setTimeout(inject, 400);
    }

    return () => {
      if (idleId != null && w.cancelIdleCallback) w.cancelIdleCallback(idleId);
      if (timeoutId != null) clearTimeout(timeoutId);
    };
  }, []);

  return null;
}
