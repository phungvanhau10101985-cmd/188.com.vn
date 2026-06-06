'use client';

import { useCallback, useSyncExternalStore } from 'react';
import type { SiteSaleCalendarState } from '@/types/api';
import { apiClient } from '@/lib/api-client';

type SiteSaleSnapshot = {
  state: SiteSaleCalendarState | null;
  loading: boolean;
};

let store: SiteSaleSnapshot = { state: null, loading: true };
let inflight: Promise<void> | null = null;
let saleCalendarRequested = false;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((fn) => fn());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (typeof window !== 'undefined') {
    void loadSiteSaleOnce();
  }
  return () => listeners.delete(listener);
}

function getClientSnapshot(): SiteSaleSnapshot {
  return store;
}

function getServerSnapshot(): SiteSaleSnapshot {
  return { state: null, loading: true };
}

async function loadSiteSaleOnce(force = false): Promise<void> {
  if (!force) {
    if (inflight) return inflight;
    if (saleCalendarRequested) return;
  } else {
    inflight = null;
    store = { state: store.state, loading: true };
    emit();
  }

  saleCalendarRequested = true;

  inflight = (async () => {
    try {
      const data = await apiClient.getSiteSaleCalendar();
      store = { state: data, loading: false };
    } catch (e) {
      if (process.env.NODE_ENV === 'development') {
        console.warn('[useSiteSale] Không tải được sale calendar:', e);
      }
      store = { state: null, loading: false };
    } finally {
      inflight = null;
      emit();
    }
  })();

  return inflight;
}

/** Một request /sale-calendar/current cho cả app (tránh N× ProductCard gọi trùng). */
export function useSiteSale() {
  const snapshot = useSyncExternalStore(
    subscribe,
    getClientSnapshot,
    getServerSnapshot,
  );

  const reload = useCallback(async () => {
    await loadSiteSaleOnce(true);
  }, []);

  return { state: snapshot.state, loading: snapshot.loading, reload };
}
