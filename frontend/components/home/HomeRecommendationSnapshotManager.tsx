'use client';

import { useEffect, useRef } from 'react';
import { apiClient } from '@/lib/api-client';

/** Tab ẩn / rời web ≥ 2 phút → rebuild snapshot nền cho lần mở trang chủ sau. */
const AWAY_MS = 2 * 60 * 1000;

export default function HomeRecommendationSnapshotManager() {
  const hiddenAtRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    function clearTimer() {
      if (timerRef.current != null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    }

    function queueRebuild() {
      void apiClient.rebuildHomeRecommendationSnapshot().catch(() => {});
    }

    function onHidden() {
      hiddenAtRef.current = Date.now();
      clearTimer();
      timerRef.current = setTimeout(queueRebuild, AWAY_MS);
    }

    function onVisible() {
      hiddenAtRef.current = null;
      clearTimer();
    }

    function onVisibilityChange() {
      if (document.hidden) onHidden();
      else onVisible();
    }

    function onPageHide() {
      const hiddenAt = hiddenAtRef.current;
      if (hiddenAt != null && Date.now() - hiddenAt >= AWAY_MS) {
        queueRebuild();
      }
    }

    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pagehide', onPageHide);
    return () => {
      clearTimer();
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('pagehide', onPageHide);
    };
  }, []);

  return null;
}
