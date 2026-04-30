'use client';

import { useEffect, useRef } from 'react';
import type { PublicSiteEmbeds } from '@/lib/site-embeds-public';

function appendFragment(target: ParentNode, html: string) {
  const s = html.trim();
  if (!s) return;
  try {
    const range = document.createRange();
    target.appendChild(range.createContextualFragment(s));
  } catch {
    /* HTML không hợp lệ — bỏ qua */
  }
}

function prependBodyFragment(html: string) {
  const s = html.trim();
  if (!s) return;
  try {
    const range = document.createRange();
    const frag = range.createContextualFragment(s);
    document.body.insertBefore(frag, document.body.firstChild);
  } catch {
    /* noop */
  }
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
