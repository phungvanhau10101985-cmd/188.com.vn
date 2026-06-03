'use client';

import { useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { apiClient } from '@/lib/api-client';

/** Không tương tác / không chuyển trang ≥ 2 phút → rebuild snapshot nền. */
const IDLE_MS = 2 * 60 * 1000;
/** Tránh gọi rebuild liên tiếp (idle + đóng tab cùng lúc). */
const REBUILD_DEBOUNCE_MS = 30 * 1000;

const ACTIVITY_EVENTS = ['pointerdown', 'keydown', 'touchstart', 'scroll', 'click'] as const;

export default function HomeRecommendationSnapshotManager() {
  const pathname = usePathname();
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastRebuildAtRef = useRef(0);
  const bumpActivityRef = useRef<() => void>(() => {});
  const prevPathnameRef = useRef(pathname);

  useEffect(() => {
    function clearIdleTimer() {
      if (idleTimerRef.current != null) {
        clearTimeout(idleTimerRef.current);
        idleTimerRef.current = null;
      }
    }

    function queueRebuild(options?: { keepalive?: boolean }) {
      const now = Date.now();
      if (now - lastRebuildAtRef.current < REBUILD_DEBOUNCE_MS) return;
      lastRebuildAtRef.current = now;

      if (options?.keepalive) {
        apiClient.rebuildHomeRecommendationSnapshotOnUnload();
        return;
      }
      void apiClient.rebuildHomeRecommendationSnapshot().catch(() => {});
    }

    function scheduleIdleRebuild() {
      clearIdleTimer();
      idleTimerRef.current = setTimeout(() => {
        queueRebuild();
        scheduleIdleRebuild();
      }, IDLE_MS);
    }

    function bumpActivity() {
      scheduleIdleRebuild();
    }

    function onPageHide() {
      queueRebuild({ keepalive: true });
    }

    bumpActivityRef.current = bumpActivity;
    bumpActivity();

    for (const event of ACTIVITY_EVENTS) {
      window.addEventListener(event, bumpActivity, { passive: true });
    }
    window.addEventListener('pagehide', onPageHide);

    return () => {
      clearIdleTimer();
      bumpActivityRef.current = () => {};
      for (const event of ACTIVITY_EVENTS) {
        window.removeEventListener(event, bumpActivity);
      }
      window.removeEventListener('pagehide', onPageHide);
    };
  }, []);

  useEffect(() => {
    if (prevPathnameRef.current === pathname) return;
    prevPathnameRef.current = pathname;
    bumpActivityRef.current();
  }, [pathname]);

  return null;
}
