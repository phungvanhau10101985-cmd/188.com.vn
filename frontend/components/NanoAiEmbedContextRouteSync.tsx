'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { clearNanoAiLoaderScriptProductContext } from '@/lib/nanoai-hosted-chat';
import { SHOP_VIDEO_FEED_PATH } from '@/lib/shop-video-feed';

function pathNorm(p: string | null | undefined): string {
  if (p == null) return '/';
  const t = p.replace(/\/$/, '').trim();
  return t === '' ? '/' : t;
}

function isProductDetailPath(pathname: string | null): boolean {
  return Boolean(pathname?.match(/^\/products\/[^/]+$/));
}

/**
 * Trang không phải SP / feed video: xóa data-ctx-* trên script widget (FAB = chat trống, không chip).
 */
export default function NanoAiEmbedContextRouteSync() {
  const pathname = usePathname();

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const norm = pathNorm(pathname);
    if (isProductDetailPath(pathname) || norm === SHOP_VIDEO_FEED_PATH) return;
    clearNanoAiLoaderScriptProductContext();
  }, [pathname]);

  return null;
}
