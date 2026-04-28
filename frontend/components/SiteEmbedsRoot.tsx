'use client';

import { useLayoutEffect, useRef } from 'react';
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

/** Chèn mã từ /admin/embed-codes (đã SSR fetch) vào head/body một lần */
export default function SiteEmbedsRoot({ embeds }: { embeds: PublicSiteEmbeds }) {
  const initial = useRef(embeds);

  useLayoutEffect(() => {
    const win = typeof window !== 'undefined' ? (window as Window & { __188_SITE_EMBEDS__?: boolean }) : null;
    if (!win || win.__188_SITE_EMBEDS__) return;
    win.__188_SITE_EMBEDS__ = true;

    const { head, body_open, body_close } = initial.current;

    head.forEach((h) => appendFragment(document.head, h));

    for (let i = body_open.length - 1; i >= 0; i--) prependBodyFragment(body_open[i] ?? '');
    body_close.forEach((b) => appendFragment(document.body, b));
  }, []);

  return null;
}
