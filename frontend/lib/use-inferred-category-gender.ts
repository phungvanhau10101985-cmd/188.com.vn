'use client';

import { useEffect, useSyncExternalStore } from 'react';
import { apiClient } from '@/lib/api-client';

type GenderSnapshot = {
  suffix: string | null;
  loading: boolean;
};

const SERVER_SNAPSHOT: GenderSnapshot = { suffix: null, loading: false };

let store: GenderSnapshot = { suffix: null, loading: false };
let inflight: Promise<void> | null = null;
let activeFetchKey = '';
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((fn) => fn());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getClientSnapshot(): GenderSnapshot {
  return store;
}

function getServerSnapshot(): GenderSnapshot {
  return SERVER_SNAPSHOT;
}

async function loadInferredGender(fetchKey: string): Promise<void> {
  if (inflight && activeFetchKey === fetchKey) {
    return inflight;
  }

  activeFetchKey = fetchKey;
  store = { ...store, loading: true };
  emit();

  inflight = (async () => {
    try {
      const res = await apiClient.getInferredCategoryGender(8);
      if (activeFetchKey !== fetchKey) return;
      store = { suffix: res.gender_suffix ?? null, loading: false };
    } catch {
      if (activeFetchKey !== fetchKey) return;
      store = { suffix: null, loading: false };
    } finally {
      inflight = null;
      emit();
    }
  })();

  return inflight;
}

/** Một request inferred-gender cho cả app (AppShell + PDP dùng chung). */
export function useInferredCategoryGender(fetchKey: string): string | null {
  useEffect(() => {
    void loadInferredGender(fetchKey);
  }, [fetchKey]);

  const snapshot = useSyncExternalStore(subscribe, getClientSnapshot, getServerSnapshot);
  return snapshot.suffix;
}
