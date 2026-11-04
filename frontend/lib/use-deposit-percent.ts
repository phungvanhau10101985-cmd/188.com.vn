'use client';

import { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api-client';
import {
  DEPOSIT_POLICY_FALLBACK,
  depositPolicyFromApi,
  type DepositPolicy,
} from '@/lib/deposit-policy';

const CACHE_MS = 60_000;

export type { DepositPolicy };

const FALLBACK = DEPOSIT_POLICY_FALLBACK;

let cached: { value: DepositPolicy; at: number } | null = null;
let inflight: Promise<DepositPolicy> | null = null;

export function loadDepositPolicy(): Promise<DepositPolicy> {
  if (cached && Date.now() - cached.at < CACHE_MS) {
    return Promise.resolve(cached.value);
  }
  if (!inflight) {
    inflight = apiClient
      .getDepositPolicy()
      .then((data) => {
        const value = depositPolicyFromApi(data);
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
