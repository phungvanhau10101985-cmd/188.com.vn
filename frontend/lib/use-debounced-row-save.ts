'use client';

import { useCallback, useEffect, useRef } from 'react';

const DEFAULT_DELAY_MS = 700;

/** Tự lưu sau khi admin sửa ô — debounce + flush ngay khi blur. */
export function useDebouncedRowSave(delayMs = DEFAULT_DELAY_MS) {
  const timersRef = useRef<Record<number, ReturnType<typeof setTimeout>>>({});

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      Object.values(timers).forEach(clearTimeout);
    };
  }, []);

  const cancelScheduled = useCallback((id: number) => {
    const t = timersRef.current[id];
    if (t) {
      clearTimeout(t);
      delete timersRef.current[id];
    }
  }, []);

  const scheduleSave = useCallback(
    (id: number, saveFn: () => void | Promise<void>) => {
      cancelScheduled(id);
      timersRef.current[id] = setTimeout(() => {
        delete timersRef.current[id];
        void saveFn();
      }, delayMs);
    },
    [cancelScheduled, delayMs],
  );

  const flushSave = useCallback(
    (id: number, saveFn: () => void | Promise<void>) => {
      cancelScheduled(id);
      void saveFn();
    },
    [cancelScheduled],
  );

  return { scheduleSave, flushSave, cancelScheduled };
}
