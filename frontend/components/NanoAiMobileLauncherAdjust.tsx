'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import {
  DEFAULT_SHOP_VIDEO_FAB_SETTINGS,
  fetchShopVideoFabPublicSettings,
  type ShopVideoFabPublicSettings,
} from '@/lib/shop-video-fab-settings';
import { SHOP_VIDEO_FEED_PATH } from '@/lib/shop-video-feed';

const MOBILE_MQ = '(max-width: 767px)';
const VIDEO_FAB_SIZE_PX = 52;
const FLOAT_GAP_PX = 12;
const MOBILE_NAV_PX = 60;
const NANOAI_Z_INDEX = 75;

const NANOAI_HOST_SELECTORS = [
  '#nanoai-chat-widget-v1',
  '[id^="nanoai-chat-widget"]',
  '[id*="nanoai-chat-widget"]',
  '[data-nanoai-launcher]',
  '[data-nanoai-chat-launcher]',
];

function pathNorm(p: string | null | undefined): string {
  if (p == null) return '/';
  const t = p.replace(/\/$/, '').trim();
  return t === '' ? '/' : t;
}

function isMobileViewport(): boolean {
  return typeof window !== 'undefined' && window.matchMedia(MOBILE_MQ).matches;
}

function showVideoFab(pathname: string | null): boolean {
  const norm = pathNorm(pathname);
  if (norm === SHOP_VIDEO_FEED_PATH) return false;
  if (pathname?.startsWith('/auth/')) return false;
  if (pathname?.startsWith('/admin')) return false;
  return true;
}

function showMobileBottomNav(pathname: string | null): boolean {
  const norm = pathNorm(pathname);
  if (norm === SHOP_VIDEO_FEED_PATH) return false;
  return !Boolean(pathname?.match(/^\/products\/[^/]+$/));
}

function findNanoAiHosts(): HTMLElement[] {
  const found = new Set<HTMLElement>();
  for (const sel of NANOAI_HOST_SELECTORS) {
    document.querySelectorAll<HTMLElement>(sel).forEach((el) => {
      const host = resolveFixedHost(el);
      if (host) found.add(host);
    });
  }
  return Array.from(found);
}

function resolveFixedHost(el: HTMLElement): HTMLElement | null {
  let node: HTMLElement | null = el;
  while (node) {
    const cs = getComputedStyle(node);
    if (cs.position === 'fixed') return node;
    node = node.parentElement;
  }
  return el;
}

function computeMobileBottomPx(
  pathname: string | null,
  fab: ShopVideoFabPublicSettings,
): number {
  const hasVideo = showVideoFab(pathname);
  const hasNav = showMobileBottomNav(pathname);

  if (hasVideo) {
    const videoBottom = hasNav ? fab.bottom_mobile_px_with_nav : fab.bottom_mobile_px_no_nav;
    return videoBottom + VIDEO_FAB_SIZE_PX + FLOAT_GAP_PX;
  }

  if (hasNav) {
    return MOBILE_NAV_PX + FLOAT_GAP_PX;
  }

  return fab.bottom_mobile_px_no_nav + FLOAT_GAP_PX;
}

function applyMobileLayout(pathname: string | null, fab: ShopVideoFabPublicSettings) {
  if (!isMobileViewport()) return;

  const bottomPx = computeMobileBottomPx(pathname, fab);
  const rightPx = fab.right_mobile_px;

  for (const host of findNanoAiHosts()) {
    host.style.setProperty('display', 'block', 'important');
    host.style.setProperty('visibility', 'visible', 'important');
    host.style.setProperty('opacity', '1', 'important');
    host.style.setProperty('pointer-events', 'auto', 'important');
    host.style.setProperty('transform', 'none', 'important');
    host.style.setProperty('z-index', String(NANOAI_Z_INDEX), 'important');
    host.style.setProperty(
      'bottom',
      `calc(${bottomPx}px + env(safe-area-inset-bottom, 0px))`,
      'important',
    );
    host.style.setProperty(
      'right',
      `calc(${rightPx}px + env(safe-area-inset-right, 0px))`,
      'important',
    );
    host.dataset.nanoai188MobileAdjusted = '1';
  }
}

function clearMobileLayout() {
  for (const host of findNanoAiHosts()) {
    if (host.dataset.nanoai188MobileAdjusted !== '1') continue;
    host.style.removeProperty('display');
    host.style.removeProperty('visibility');
    host.style.removeProperty('opacity');
    host.style.removeProperty('pointer-events');
    host.style.removeProperty('transform');
    host.style.removeProperty('z-index');
    host.style.removeProperty('bottom');
    host.style.removeProperty('right');
    delete host.dataset.nanoai188MobileAdjusted;
  }
}

/**
 * Mobile: đẩy launcher NanoAI lên trên bottom nav + nút video (tránh bị che / “mất” nút chat).
 */
export default function NanoAiMobileLauncherAdjust() {
  const pathname = usePathname();

  useEffect(() => {
    if (typeof window === 'undefined') return;

    let fab = DEFAULT_SHOP_VIDEO_FAB_SETTINGS;
    let cancelled = false;

    const run = () => {
      if (cancelled) return;
      if (!isMobileViewport()) {
        clearMobileLayout();
        return;
      }
      applyMobileLayout(pathname, fab);
    };

    void fetchShopVideoFabPublicSettings().then((s) => {
      if (cancelled) return;
      fab = s;
      run();
    });

    run();

    const mq = window.matchMedia(MOBILE_MQ);
    const onMq = () => run();
    mq.addEventListener('change', onMq);

    let scanTimer: ReturnType<typeof setTimeout> | undefined;
    const schedule = () => {
      if (scanTimer) clearTimeout(scanTimer);
      scanTimer = setTimeout(run, 180);
    };

    const mo = new MutationObserver(schedule);
    mo.observe(document.body, { childList: true, subtree: true });

    window.addEventListener('188-site-embeds-ready', schedule);
    window.addEventListener('resize', schedule, { passive: true });

    return () => {
      cancelled = true;
      mq.removeEventListener('change', onMq);
      mo.disconnect();
      window.removeEventListener('188-site-embeds-ready', schedule);
      window.removeEventListener('resize', schedule);
      if (scanTimer) clearTimeout(scanTimer);
      clearMobileLayout();
    };
  }, [pathname]);

  return null;
}
