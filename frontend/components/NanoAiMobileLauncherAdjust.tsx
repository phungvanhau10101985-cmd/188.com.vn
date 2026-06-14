'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import {
  clearNanoAiOverlayPassThrough,
  releaseNanoAiClickBlockers,
} from '@/lib/nanoai-overlay-pass-through';
import { startNanoAiChatWidgetBootWatch } from '@/lib/nanoai-hosted-chat';

const ROOT_SELECTORS = [
  '#nanoai-chat-widget-v1',
  '[id^="nanoai-chat-widget"]',
  '[id*="nanoai-chat-widget"]',
];

const VIDEO_FAB_SELECTOR = '[data-188-video-fab]';
const STACK_GAP_PX = 10;

type NanoEmbedLayout = {
  side: 'left' | 'right';
  offsetX: number;
  bottom: number;
  mobileBreakpoint: number;
  bubbleSize: number;
  mobileBubbleSize: number;
};

type BubbleAnchor = {
  bottom: number;
  offsetX: number;
  fromVideoFab: boolean;
};

function findActiveEmbedScript(widgetId: string): HTMLScriptElement | null {
  const scripts = Array.from(
    document.querySelectorAll<HTMLScriptElement>('script[src*="nanoai-chat-widget.js"]'),
  );
  if (scripts.length === 0) return null;

  const withMatchingWidgetId = scripts.filter((s) => (s.getAttribute('data-widget-id') || '') === widgetId);
  if (withMatchingWidgetId.length > 0) {
    return withMatchingWidgetId[withMatchingWidgetId.length - 1] ?? null;
  }
  return scripts[scripts.length - 1] ?? null;
}

function parseIntClamp(raw: string | null, fallback: number, min: number, max: number): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, Math.round(n)));
}

function readEmbedLayout(): NanoEmbedLayout {
  const widgetId = 'nanoai-chat-widget-v1';
  const script = findActiveEmbedScript(widgetId);
  const side = script?.getAttribute('data-side') === 'left' ? 'left' : 'right';
  return {
    side,
    offsetX: parseIntClamp(script?.getAttribute('data-offset-x') ?? null, 16, 0, 300),
    bottom: parseIntClamp(script?.getAttribute('data-bottom') ?? null, 20, 0, 1200),
    mobileBreakpoint: parseIntClamp(script?.getAttribute('data-mobile-breakpoint') ?? null, 768, 320, 1600),
    bubbleSize: parseIntClamp(script?.getAttribute('data-bubble-size') ?? null, 56, 28, 200),
    mobileBubbleSize: parseIntClamp(script?.getAttribute('data-mobile-bubble-size') ?? null, 52, 28, 200),
  };
}

function viewportHeight(): number {
  return (
    window.innerHeight ||
    document.documentElement.clientHeight ||
    document.body.clientHeight ||
    800
  );
}

function viewportWidth(): number {
  return window.innerWidth || document.documentElement.clientWidth || document.body.clientWidth || 360;
}

function clampBottomOffset(bottom: number, sizePx: number): number {
  const maxBottom = Math.max(8, viewportHeight() - sizePx - 8);
  return Math.min(Math.max(8, bottom), maxBottom);
}

function clampHorizontalOffset(offset: number, bubbleWidth: number): number {
  const vw = viewportWidth();
  const maxOffset = Math.max(8, vw - bubbleWidth - 8);
  return Math.min(Math.max(8, offset), maxOffset);
}

/**
 * Căn bubble Tư vấn thẳng cột với nút video shop (đọc rect thật — desktop + mobile).
 * Fallback: thuộc tính embed script khi không có nút video.
 */
function computeBubbleAnchor(
  layout: NanoEmbedLayout,
  bubbleEl: HTMLElement | null,
  bubbleSizeFallback: number,
): BubbleAnchor {
  const fallback: BubbleAnchor = {
    bottom: clampBottomOffset(layout.bottom, bubbleSizeFallback),
    offsetX: layout.offsetX,
    fromVideoFab: false,
  };

  const videoFab = document.querySelector<HTMLElement>(VIDEO_FAB_SELECTOR);
  if (!videoFab) return fallback;

  const r = videoFab.getBoundingClientRect();
  if (r.width < 20 || r.height < 20) return fallback;

  const vw = viewportWidth();
  const vh = viewportHeight();
  if (!vw || !vh) return fallback;

  const bubbleWidth = Math.max(bubbleEl?.offsetWidth || 0, bubbleSizeFallback);
  const bubbleHeight = Math.max(bubbleEl?.offsetHeight || 0, bubbleSizeFallback);
  const videoCenterX = r.left + r.width / 2;

  const bottom = clampBottomOffset(vh - r.top + STACK_GAP_PX, bubbleHeight);

  if (layout.side === 'left') {
    const left = clampHorizontalOffset(videoCenterX - bubbleWidth / 2, bubbleWidth);
    return {
      bottom,
      offsetX: left,
      fromVideoFab: true,
    };
  }

  const right = clampHorizontalOffset(vw - videoCenterX - bubbleWidth / 2, bubbleWidth);
  return {
    bottom,
    offsetX: right,
    fromVideoFab: true,
  };
}

function enforceViewportAnchoring() {
  const layout = readEmbedLayout();
  const isMobile = window.innerWidth <= layout.mobileBreakpoint;
  const bubbleSizeFallback = isMobile ? layout.mobileBubbleSize : layout.bubbleSize;

  ROOT_SELECTORS.forEach((sel) => {
    document.querySelectorAll<HTMLElement>(sel).forEach((root) => {
      root.style.setProperty('position', 'fixed', 'important');
      root.style.setProperty('left', '0', 'important');
      root.style.setProperty('top', '0', 'important');
      root.style.setProperty('right', '0', 'important');
      root.style.setProperty('bottom', '0', 'important');
      root.style.setProperty('width', '100vw', 'important');
      root.style.setProperty('height', '100dvh', 'important');
      root.style.setProperty('max-width', '100vw', 'important');
      root.style.setProperty('max-height', '100dvh', 'important');
      root.style.setProperty('margin', '0', 'important');
      root.style.setProperty('transform', 'none', 'important');
      root.style.setProperty('pointer-events', 'none', 'important');

      const bubble = root.querySelector<HTMLElement>('[data-nanoai-chat-bubble]');
      if (!bubble) return;

      const anchor = computeBubbleAnchor(layout, bubble, bubbleSizeFallback);

      bubble.style.setProperty('position', 'absolute', 'important');
      bubble.style.setProperty('bottom', `${anchor.bottom}px`, 'important');
      bubble.style.setProperty('margin', '0', 'important');
      if (layout.side === 'left') {
        bubble.style.setProperty('left', `${anchor.offsetX}px`, 'important');
        bubble.style.setProperty('right', 'auto', 'important');
      } else {
        bubble.style.setProperty('right', `${anchor.offsetX}px`, 'important');
        bubble.style.setProperty('left', 'auto', 'important');
      }

      if (anchor.fromVideoFab) {
        bubble.dataset.nanoai188VideoAnchored = '1';
      } else {
        delete bubble.dataset.nanoai188VideoAnchored;
      }
    });
  });
}

function clearMobileLayoutOn(el: HTMLElement) {
  el.style.removeProperty('display');
  el.style.removeProperty('visibility');
  el.style.removeProperty('opacity');
  el.style.removeProperty('pointer-events');
  el.style.removeProperty('transform');
  el.style.removeProperty('margin');
  el.style.removeProperty('inset');
  el.style.removeProperty('position');
  el.style.removeProperty('top');
  el.style.removeProperty('left');
  el.style.removeProperty('z-index');
  el.style.removeProperty('bottom');
  el.style.removeProperty('right');
  delete el.dataset.nanoai188MobileAdjusted;
  delete el.dataset.nanoai188VideoAnchored;
}

function clearMobileLayout() {
  document.querySelectorAll<HTMLElement>('[data-nanoai188-mobile-adjusted="1"]').forEach(clearMobileLayoutOn);
}

/**
 * Căn launcher NanoAI theo nút video shop (desktop + mobile).
 * Không có nút video → dùng `data-bottom` / `data-offset-x` từ script embed.
 */
export default function NanoAiMobileLauncherAdjust() {
  const pathname = usePathname();

  useEffect(() => {
    if (typeof window === 'undefined') return;

    clearMobileLayout();
    releaseNanoAiClickBlockers();
    enforceViewportAnchoring();
    const stopBootWatch = startNanoAiChatWidgetBootWatch();

    let rafId: number | undefined;
    let rafQueued = false;
    const schedule = () => {
      if (rafQueued) return;
      rafQueued = true;
      rafId = window.requestAnimationFrame(() => {
        rafQueued = false;
        enforceViewportAnchoring();
        // Bubble pill rộng hơn bubble-size — căn lại sau khi layout xong.
        rafId = window.requestAnimationFrame(() => {
          enforceViewportAnchoring();
        });
      });
    };

    const mo = new MutationObserver(schedule);
    mo.observe(document.body, { childList: true, subtree: true, attributes: true });
    window.addEventListener('resize', schedule, { passive: true });
    window.addEventListener('188-site-embeds-ready', schedule);

    return () => {
      mo.disconnect();
      window.removeEventListener('resize', schedule);
      window.removeEventListener('188-site-embeds-ready', schedule);
      if (rafId !== undefined) window.cancelAnimationFrame(rafId);
      stopBootWatch();
      clearMobileLayout();
      clearNanoAiOverlayPassThrough();
    };
  }, [pathname]);

  return null;
}
