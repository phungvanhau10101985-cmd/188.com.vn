'use client';

import { useSyncExternalStore } from 'react';

let nowMs: number | null = null;
let intervalId: number | null = null;
const listeners = new Set<() => void>();

function emit() {
  nowMs = Date.now();
  listeners.forEach((fn) => fn());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (typeof window !== 'undefined' && intervalId == null) {
    emit();
    intervalId = window.setInterval(emit, 1000);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && intervalId != null) {
      window.clearInterval(intervalId);
      intervalId = null;
      nowMs = null;
    }
  };
}

function getSnapshot(): number | null {
  return nowMs;
}

function getServerSnapshot(): null {
  return null;
}

function emptySubscribe(_listener: () => void) {
  return () => {};
}

/** Một clock chung cho mọi countdown — tránh N× setInterval (lưới 48 SP treo tab). */
export function useCountdownNowMs(enabled = true): number | null {
  return useSyncExternalStore(
    enabled ? subscribe : emptySubscribe,
    enabled ? getSnapshot : () => null,
    getServerSnapshot,
  );
}
