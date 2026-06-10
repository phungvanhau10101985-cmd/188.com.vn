'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import {
  clearNanoAiOverlayPassThrough,
  releaseNanoAiClickBlockers,
} from '@/lib/nanoai-overlay-pass-through';

const ROOT_SELECTORS = [
  '#nanoai-chat-widget-v1',
  '[id^="nanoai-chat-widget"]',
  '[id*="nanoai-chat-widget"]',
];

type NanoEmbedLayout = {
  side: 'left' | 'right';
  offsetX: number;
  bottom: number;
  mobileBreakpoint: number;
  bubbleSize: number;
  mobileBubbleSize: number;
};

function parseIntClamp(raw: string | null, fallback: number, min: number, max: number): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, Math.round(n)));
}

function readEmbedLayout(): NanoEmbedLayout {
  const script = document.querySelector<HTMLScriptElement>('script[src*="nanoai-chat-widget.js"]');
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

function clampBottomOffset(bottom: number, sizePx: number): number {
  const maxBottom = Math.max(8, viewportHeight() - sizePx - 8);
  return Math.min(bottom, maxBottom);
}

function enforceViewportAnchoring() {
  const layout = readEmbedLayout();
  const isMobile = window.innerWidth <= layout.mobileBreakpoint;
  const bubbleSize = isMobile ? layout.mobileBubbleSize : layout.bubbleSize;
  const safeBottom = clampBottomOffset(layout.bottom, bubbleSize);

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

      bubble.style.setProperty('position', 'absolute', 'important');
      bubble.style.setProperty('bottom', `${safeBottom}px`, 'important');
      bubble.style.setProperty('margin', '0', 'important');
      if (layout.side === 'left') {
        bubble.style.setProperty('left', `${layout.offsetX}px`, 'important');
        bubble.style.setProperty('right', 'auto', 'important');
      } else {
        bubble.style.setProperty('right', `${layout.offsetX}px`, 'important');
        bubble.style.setProperty('left', 'auto', 'important');
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
}

function clearMobileLayout() {
  document.querySelectorAll<HTMLElement>('[data-nanoai188-mobile-adjusted="1"]').forEach(clearMobileLayoutOn);
}

/**
 * Không ép vị trí launcher NanoAI.
 * Vị trí launcher sẽ do script embed (`data-bottom`, `data-offset-x`, `data-side`, ...) quyết định.
 */
export default function NanoAiMobileLauncherAdjust() {
  const pathname = usePathname();

  useEffect(() => {
    if (typeof window === 'undefined') return;

    // Dọn mọi inline style cũ từng ghi đè vị trí launcher.
    clearMobileLayout();
    releaseNanoAiClickBlockers();
    enforceViewportAnchoring();

    let timer: ReturnType<typeof setTimeout> | undefined;
    const schedule = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        enforceViewportAnchoring();
      }, 120);
    };

    const mo = new MutationObserver(schedule);
    mo.observe(document.body, { childList: true, subtree: true, attributes: true });
    window.addEventListener('resize', schedule, { passive: true });
    window.addEventListener('188-site-embeds-ready', schedule);

    return () => {
      mo.disconnect();
      window.removeEventListener('resize', schedule);
      window.removeEventListener('188-site-embeds-ready', schedule);
      if (timer) clearTimeout(timer);
      clearMobileLayout();
      clearNanoAiOverlayPassThrough();
    };
  }, [pathname]);

  return null;
}
