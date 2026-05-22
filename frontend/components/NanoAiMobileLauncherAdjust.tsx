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
const MAX_LAUNCHER_PX = 200;

const LAUNCHER_SELECTORS = [
  '[data-nanoai-launcher]',
  '[data-nanoai-chat-launcher]',
  '#nanoai-chat-widget-v1 > button',
  '#nanoai-chat-widget-v1 button',
  '[id^="nanoai-chat-widget"] button',
  '[id*="nanoai-chat"] button',
  'button.nanoai-chat-launcher',
];

const ROOT_SELECTORS = [
  '#nanoai-chat-widget-v1',
  '[id^="nanoai-chat-widget"]',
  '[id*="nanoai-chat-widget"]',
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

function isLauncherSized(el: HTMLElement): boolean {
  const r = el.getBoundingClientRect();
  if (r.width < 28 || r.height < 28) return false;
  if (r.width > MAX_LAUNCHER_PX || r.height > MAX_LAUNCHER_PX) return false;
  return true;
}

/** Chỉ chỉnh nút launcher nhỏ — tránh container full-screen che trang /account. */
function findNanoAiLaunchers(): HTMLElement[] {
  const found = new Set<HTMLElement>();

  for (const sel of LAUNCHER_SELECTORS) {
    document.querySelectorAll<HTMLElement>(sel).forEach((el) => {
      if (isLauncherSized(el)) found.add(el);
    });
  }

  for (const sel of ROOT_SELECTORS) {
    document.querySelectorAll<HTMLElement>(sel).forEach((el) => {
      const cs = getComputedStyle(el);
      if (cs.position !== 'fixed') return;
      if (!isLauncherSized(el)) return;
      found.add(el);
    });
  }

  return Array.from(found);
}

function isLargeFixedOverlay(el: HTMLElement): boolean {
  const cs = getComputedStyle(el);
  if (cs.position !== 'fixed' && cs.position !== 'absolute') return false;
  const r = el.getBoundingClientRect();
  const vw = typeof window !== 'undefined' ? window.innerWidth : 0;
  const vh = typeof window !== 'undefined' ? window.innerHeight : 0;
  if (!vw || !vh) return false;
  return r.width >= vw * 0.72 || r.height >= vh * 0.72;
}

function isInteractiveNanoAiNode(el: HTMLElement): boolean {
  const tag = el.tagName;
  if (/^(BUTTON|A|IFRAME|INPUT|TEXTAREA|SELECT)$/i.test(tag)) return true;
  const role = el.getAttribute('role');
  if (role === 'button' || role === 'dialog' || role === 'textbox') return true;
  if (el.isContentEditable) return true;
  return isLauncherSized(el);
}

/** Container NanoAI full-screen không nuốt tap trang — chỉ phần tử tương tác nhận click. */
function releaseNanoAiClickBlockers() {
  if (!isMobileViewport()) return;

  for (const sel of ROOT_SELECTORS) {
    document.querySelectorAll<HTMLElement>(sel).forEach((root) => {
      if (!isLargeFixedOverlay(root)) return;

      root.style.setProperty('pointer-events', 'none', 'important');
      root.dataset.nanoai188OverlayPass = '1';

      const stack: HTMLElement[] = [root];
      while (stack.length > 0) {
        const node = stack.pop()!;
        for (const child of Array.from(node.children)) {
          if (!(child instanceof HTMLElement)) continue;
          stack.push(child);
          if (isInteractiveNanoAiNode(child) || !isLargeFixedOverlay(child)) {
            child.style.setProperty('pointer-events', 'auto', 'important');
            child.dataset.nanoai188OverlayPass = '1';
          } else {
            child.style.setProperty('pointer-events', 'none', 'important');
            child.dataset.nanoai188OverlayPass = '1';
          }
        }
      }
    });
  }
}

function clearOverlayPass() {
  document.querySelectorAll<HTMLElement>('[data-nanoai188-overlay-pass="1"]').forEach((el) => {
    el.style.removeProperty('pointer-events');
    delete el.dataset.nanoai188OverlayPass;
  });
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

  releaseNanoAiClickBlockers();

  for (const launcher of findNanoAiLaunchers()) {
    launcher.style.setProperty('display', 'block', 'important');
    launcher.style.setProperty('visibility', 'visible', 'important');
    launcher.style.setProperty('opacity', '1', 'important');
    launcher.style.setProperty('pointer-events', 'auto', 'important');
    launcher.style.setProperty('transform', 'none', 'important');
    launcher.style.setProperty('top', 'auto', 'important');
    launcher.style.setProperty('left', 'auto', 'important');
    launcher.style.setProperty('z-index', String(NANOAI_Z_INDEX), 'important');
    launcher.style.setProperty(
      'bottom',
      `calc(${bottomPx}px + env(safe-area-inset-bottom, 0px))`,
      'important',
    );
    launcher.style.setProperty(
      'right',
      `calc(${rightPx}px + env(safe-area-inset-right, 0px))`,
      'important',
    );
    launcher.dataset.nanoai188MobileAdjusted = '1';
  }
}

function clearMobileLayout() {
  document.querySelectorAll<HTMLElement>('[data-nanoai188-mobile-adjusted="1"]').forEach((el) => {
    el.style.removeProperty('display');
    el.style.removeProperty('visibility');
    el.style.removeProperty('opacity');
    el.style.removeProperty('pointer-events');
    el.style.removeProperty('transform');
    el.style.removeProperty('top');
    el.style.removeProperty('left');
    el.style.removeProperty('z-index');
    el.style.removeProperty('bottom');
    el.style.removeProperty('right');
    delete el.dataset.nanoai188MobileAdjusted;
  });
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
        clearOverlayPass();
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
      clearOverlayPass();
    };
  }, [pathname]);

  return null;
}
