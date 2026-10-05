'use client';

import { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api-client';
import { DEPOSIT_PERCENT } from '@/lib/business-info';

const CACHE_MS = 60_000;

let cached: { value: number; at: number } | null = null;
let inflight: Promise<number> | null = null;

function normalizePercent(raw: unknown): number | null {
  const n = Number(raw);
  if (!Number.isFinite(n)) return null;
  const rounded = Math.round(n);
  if (rounded < 1 || rounded > 99) return null;
  return rounded;
}

export function loadDepositPercent(): Promise<number> {
  if (cached && Date.now() - cached.at < CACHE_MS) {
    return Promise.resolve(cached.value);
  }
  if (!inflight) {
    inflight = apiClient
      .getDepositPercent()
      .then((n) => {
        const value = normalizePercent(n) ?? DEPOSIT_PERCENT;
        cached = { value, at: Date.now() };
        return value;
      })
      .catch(() => cached?.value ?? DEPOSIT_PERCENT)
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}

/** Mức cọc một phần từ quản trị. Chưa tải xong thì dùng 30%. */
export function useDepositPercent(): number {
  const [percent, setPercent] = useState(() => cached?.value ?? DEPOSIT_PERCENT);

  useEffect(() => {
    let cancelled = false;
    loadDepositPercent().then((n) => {
      if (!cancelled) setPercent(n);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return percent;
}
