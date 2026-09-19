'use client';

import { useCallback, useEffect, useSyncExternalStore } from 'react';

import { APP_WEB_ICON_URL, type CurrentAppWebIcon } from '@/lib/app-web-icon';
import { apiClient } from '@/lib/api-client';

type AppWebIconSnapshot = CurrentAppWebIcon & { loading: boolean };

const FALLBACK: AppWebIconSnapshot = {
  icon_url: APP_WEB_ICON_URL,
  default_icon_url: APP_WEB_ICON_URL,
  is_sale: false,
  loading: true,
};

let store: AppWebIconSnapshot = FALLBACK;
let inflight: Promise<void> | null = null;
let requested = false;
const listeners = new Set<() => void>();
const POLL_MS = 5 * 60 * 1000;

function emit() {
  listeners.forEach((fn) => fn());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (typeof window !== 'undefined') {
    void loadAppWebIconOnce();
  }
  return () => listeners.delete(listener);
}

async function loadAppWebIconOnce(force = false): Promise<void> {
  if (!force) {
    if (inflight) return inflight;
    if (requested) return;
  } else {
    inflight = null;
  }
  requested = true;
  inflight = (async () => {
    try {
      const data = await apiClient.getCurrentAppWebIcon();
      store = {
        ...data,
        icon_url: data.icon_url || APP_WEB_ICON_URL,
        default_icon_url: data.default_icon_url || APP_WEB_ICON_URL,
        is_sale: Boolean(data.is_sale),
        loading: false,
      };
    } catch {
      store = { ...FALLBACK, loading: false };
    } finally {
      inflight = null;
      emit();
    }
  })();
  return inflight;
}

export function useAppWebIcon() {
  const snapshot = useSyncExternalStore(subscribe, () => store, () => FALLBACK);
  const reload = useCallback(async () => {
    await loadAppWebIconOnce(true);
  }, []);
  return { ...snapshot, reload };
}

/** Poll icon sale khi app đang mở — hết sale tự về logo chính, không cần cài lại. */
export function useAppWebIconPolling() {
  const icon = useAppWebIcon();
  useEffect(() => {
    const timer = window.setInterval(() => {
      void loadAppWebIconOnce(true);
    }, POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') void loadAppWebIconOnce(true);
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);
  return icon;
}
