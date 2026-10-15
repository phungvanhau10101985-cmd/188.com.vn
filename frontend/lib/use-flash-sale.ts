'use client';

import { useCallback, useEffect, useSyncExternalStore } from 'react';
import type { FlashSaleBlockResponse, Product, SiteSaleProductPricing } from '@/types/api';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { apiClient } from '@/lib/api-client';
import { getGuestSessionId } from '@/lib/guest-session';
import { isFlashSalePricing } from '@/lib/site-sale';

export const EMPTY_FLASH_BY_ID: Record<number, SiteSaleProductPricing> = {};

type FlashSaleSnapshot = {
  products: Product[];
  byId: Record<number, SiteSaleProductPricing>;
  countdownTo: string | null;
  slotKey: string | null;
  loading: boolean;
  error: string | null;
  identity: string | null;
};

const SERVER_SNAPSHOT: FlashSaleSnapshot = {
  products: [],
  byId: EMPTY_FLASH_BY_ID,
  countdownTo: null,
  slotKey: null,
  loading: true,
  error: null,
  identity: null,
};

let store: FlashSaleSnapshot = { ...SERVER_SNAPSHOT, loading: true };
let inflight: Promise<void> | null = null;
let inflightIdentity: string | null = null;
let flightSeq = 0;
let requested = false;
let refreshTimer: number | null = null;
let pastSlotRetried = false;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((fn) => fn());
}

function currentIdentityKey(): string {
  if (typeof window === 'undefined') return 'ssr';
  const token = localStorage.getItem('access_token');
  if (token) return `user:${token.slice(0, 16)}`;
  const guest = getGuestSessionId();
  return guest ? `guest:${guest}` : 'anon';
}

function buildById(products: Product[]): Record<number, SiteSaleProductPricing> {
  if (!products.length) return EMPTY_FLASH_BY_ID;
  const byId: Record<number, SiteSaleProductPricing> = {};
  for (const row of products) {
    const sale = row.flash_sale || row.site_sale;
    if (!row.id || !sale || !isFlashSalePricing(sale)) continue;
    byId[row.id] = sale;
  }
  return Object.keys(byId).length ? byId : EMPTY_FLASH_BY_ID;
}

function scheduleSlotRefresh(countdownTo: string | null) {
  if (refreshTimer !== null) {
    window.clearTimeout(refreshTimer);
    refreshTimer = null;
  }
  if (!countdownTo) return;
  const end = new Date(countdownTo).getTime();
  if (!Number.isFinite(end)) return;
  const remaining = end - Date.now();
  if (remaining <= 0) {
    if (pastSlotRetried) return;
    pastSlotRetried = true;
  } else {
    pastSlotRetried = false;
  }
  const wait =
    remaining > 0
      ? Math.min(11 * 60 * 1000, Math.max(400, remaining + 400))
      : 1500;
  refreshTimer = window.setTimeout(() => {
    refreshTimer = null;
    void loadFlashSaleOnce(true, true);
  }, wait);
}

async function loadFlashSaleOnce(force = false, silent = false): Promise<void> {
  const identity = currentIdentityKey();
  if (inflight && (!force || inflightIdentity === identity)) {
    return inflight;
  }
  if (!force && requested && store.identity === identity) return;

  requested = true;
  if (force) {
    store = silent
      ? { ...store, error: null }
      : { ...store, loading: true, error: null };
    emit();
  }

  const seq = ++flightSeq;
  const flight = (async () => {
    try {
      const data: FlashSaleBlockResponse = await apiClient.getFlashSaleBlock();
      if (seq !== flightSeq) return;
      const products = data.products ?? [];
      store = {
        products,
        byId: buildById(products),
        countdownTo: data.countdown_to ?? data.slot_end_at ?? null,
        slotKey: data.slot_key ?? null,
        loading: false,
        error: null,
        identity,
      };
    } catch (e) {
      if (seq !== flightSeq) return;
      if (process.env.NODE_ENV === 'development') {
        console.warn('[useFlashSale] Không tải được flash sale:', e);
      }
      store = {
        products: [],
        byId: EMPTY_FLASH_BY_ID,
        countdownTo: null,
        slotKey: null,
        loading: false,
        error: 'Không tải được Flash sale.',
        identity,
      };
    } finally {
      if (seq !== flightSeq) return;
      inflight = null;
      inflightIdentity = null;
      emit();
      scheduleSlotRefresh(store.countdownTo);
    }
  })();

  inflight = flight;
  inflightIdentity = identity;
  return flight;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (typeof window !== 'undefined') {
    if (store.identity && store.identity !== currentIdentityKey()) {
      void loadFlashSaleOnce(true);
    } else {
      void loadFlashSaleOnce();
    }
  }
  return () => listeners.delete(listener);
}

function getClientSnapshot(): FlashSaleSnapshot {
  return store;
}

function getServerSnapshot(): FlashSaleSnapshot {
  return SERVER_SNAPSHOT;
}

/** Một request flash-sale-block cho cả app (homepage + PDP + listing). */
export function useFlashSale() {
  const { isAuthenticated, user, isLoading: authLoading } = useAuth();
  const snapshot = useSyncExternalStore(
    subscribe,
    getClientSnapshot,
    getServerSnapshot,
  );

  const reload = useCallback(async () => {
    requested = false;
    await loadFlashSaleOnce(true);
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined' || authLoading) return;
    const identity = currentIdentityKey();
    if (snapshot.identity && snapshot.identity !== identity) {
      void loadFlashSaleOnce(true);
    }
  }, [authLoading, isAuthenticated, user?.id, snapshot.identity]);

  return {
    products: snapshot.products,
    byId: snapshot.byId,
    countdownTo: snapshot.countdownTo,
    slotKey: snapshot.slotKey,
    loading: snapshot.loading,
    error: snapshot.error,
    reload,
  };
}
