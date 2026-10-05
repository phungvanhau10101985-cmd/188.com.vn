'use client';

import { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api-client';
import { DEPOSIT_MIN_VND, DEPOSIT_PERCENT } from '@/lib/business-info';

const CACHE_MS = 60_000;

export type DepositPolicy = {
  percent: number;
  minAmount: number;
};

const FALLBACK: DepositPolicy = { percent: DEPOSIT_PERCENT, minAmount: DEPOSIT_MIN_VND };

let cached: { value: DepositPolicy; at: number } | null = null;
let inflight: Promise<DepositPolicy> | null = null;

function normalizePercent(raw: unknown): number | null {
  const n = Number(raw);
  if (!Number.isFinite(n)) return null;
  const rounded = Math.round(n);
  if (rounded < 1 || rounded > 99) return null;
  return rounded;
}

function normalizeMinAmount(raw: unknown): number {
  const n = Math.round(Number(raw));
  if (!Number.isFinite(n) || n < DEPOSIT_MIN_VND) return DEPOSIT_MIN_VND;
  return n;
}

export function loadDepositPolicy(): Promise<DepositPolicy> {
  if (cached && Date.now() - cached.at < CACHE_MS) {
    return Promise.resolve(cached.value);
  }
  if (!inflight) {
    inflight = apiClient
      .getDepositPolicy()
      .then((data) => {
        const value: DepositPolicy = {
          percent: normalizePercent(data?.partial_percent) ?? DEPOSIT_PERCENT,
          minAmount: normalizeMinAmount(data?.min_amount),
        };
        cached = { value, at: Date.now() };
        return value;
      })
      .catch(() => cached?.value ?? FALLBACK)
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}

export function loadDepositPercent(): Promise<number> {
  return loadDepositPolicy().then((policy) => policy.percent);
}

/** Mức cọc một phần và sàn tiền từ quản trị. Chưa tải xong thì 30% / 100.000đ. */
export function useDepositPolicy(): DepositPolicy {
  const [policy, setPolicy] = useState<DepositPolicy>(() => cached?.value ?? FALLBACK);

  useEffect(() => {
    let cancelled = false;
    loadDepositPolicy().then((next) => {
      if (!cancelled) setPolicy(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return policy;
}

/** Mức cọc một phần từ quản trị. Chưa tải xong thì dùng 30%. */
export function useDepositPercent(): number {
  return useDepositPolicy().percent;
}
