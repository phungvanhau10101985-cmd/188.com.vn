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
let requested = false;
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

async function loadFlashSaleOnce(force = false, silent = false): Promise<void> {
  if (!force) {
    if (inflight) return inflight;
    if (requested) return;
  } else {
    inflight = null;
    store = silent
      ? { ...store, error: null }
      : { ...store, loading: true, error: null };
    emit();
  }

  requested = true;
  const identity = currentIdentityKey();

  inflight = (async () => {
    try {
      const data: FlashSaleBlockResponse = await apiClient.getFlashSaleBlock();
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
      inflight = null;
      emit();
    }
  })();

  return inflight;
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

  useEffect(() => {
    if (typeof window === 'undefined' || !snapshot.countdownTo) return;
    const end = new Date(snapshot.countdownTo).getTime();
    if (!Number.isFinite(end)) return;
    const wait = Math.min(11 * 60 * 1000, Math.max(400, end - Date.now() + 400));
    const timer = window.setTimeout(() => {
      requested = false;
      void loadFlashSaleOnce(true, true);
    }, wait);
    return () => window.clearTimeout(timer);
  }, [snapshot.countdownTo, snapshot.slotKey]);

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
