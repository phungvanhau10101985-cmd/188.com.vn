'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import {
  clearNanoAiOverlayPassThrough,
  releaseNanoAiClickBlockers,
} from '@/lib/nanoai-overlay-pass-through';

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

    return () => {
      clearMobileLayout();
      clearNanoAiOverlayPassThrough();
    };
  }, [pathname]);

  return null;
}
