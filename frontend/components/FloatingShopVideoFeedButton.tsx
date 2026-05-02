'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { SHOP_VIDEO_FEED_PATH, shopVideoFeedHrefFromPathname } from '@/lib/shop-video-feed';
import {
  DEFAULT_SHOP_VIDEO_FAB_SETTINGS,
  fetchShopVideoFabPublicSettings,
  type ShopVideoFabPublicSettings,
} from '@/lib/shop-video-fab-settings';

function pathNorm(p: string | null | undefined): string {
  if (p == null) return '/';
  const t = p.replace(/\/$/, '').trim();
  return t === '' ? '/' : t;
}

/**
 * Icon nổi cố định viewport → feed lướt video.
 * Vị trí (px): API `/shop-video-fab/public`, chỉnh trong admin » Vị trí nút lướt video.
 */
export default function FloatingShopVideoFeedButton() {
  const pathname = usePathname();
  const norm = pathNorm(pathname);
  const feedHref = shopVideoFeedHrefFromPathname(pathname);
  const [fab, setFab] = useState<ShopVideoFabPublicSettings>(DEFAULT_SHOP_VIDEO_FAB_SETTINGS);
  const [isMd, setIsMd] = useState(false);

  useEffect(() => {
    const norm = pathNorm(pathname);
    if (
      norm === SHOP_VIDEO_FEED_PATH ||
      pathname?.startsWith('/auth/') ||
      pathname?.startsWith('/admin')
    ) {
      return;
    }
    let cancelled = false;
    fetchShopVideoFabPublicSettings().then((s) => {
      if (!cancelled) setFab(s);
    });
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)');
    const apply = () => setIsMd(mq.matches);
    apply();
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, []);

  if (norm === SHOP_VIDEO_FEED_PATH || pathname?.startsWith('/auth/') || pathname?.startsWith('/admin')) {
    return null;
  }

  const isProductDetail = Boolean(pathname?.match(/^\/products\/[^/]+$/));
  const reserveMobileBottom =
    !pathname?.startsWith('/auth/') && !isProductDetail && norm !== SHOP_VIDEO_FEED_PATH;

  const rightPx = isMd ? fab.right_desktop_px : fab.right_mobile_px;
  const bottomPx = isMd
    ? fab.bottom_desktop_px
    : reserveMobileBottom
      ? fab.bottom_mobile_px_with_nav
      : fab.bottom_mobile_px_no_nav;

  return (
    <Link
      data-188-video-fab
      href={feedHref}
      prefetch={false}
      draggable={false}
      onDragStart={(e) => e.preventDefault()}
      style={{ bottom: bottomPx, right: rightPx }}
      className="fixed z-[70] flex h-[52px] w-[52px] pointer-events-auto items-center justify-center rounded-full bg-gradient-to-br from-[#ea580c] to-[#c2410c] text-white shadow-[0_3px_12px_rgba(234,88,12,0.4)] ring-2 ring-white transition hover:scale-[1.06] hover:shadow-lg active:scale-[0.97]"
      aria-label="Lướt xem video shop"
      title="Lướt xem video shop"
    >
      <svg className="h-[26px] w-[26px] shrink-0 drop-shadow-sm" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
        <path d="M17 10.5V7a1 1 0 00-1-1H4a1 1 0 00-1 1v10a1 1 0 001 1h12a1 1 0 001-1v-3.5l4 4v-11l-4 4z" />
      </svg>
    </Link>
  );
}
