import { DEPOSIT_MIN_VND, DEPOSIT_PERCENT, HIGH_UNIT_PRICE_VND } from '@/lib/business-info';
import { normalizeHighOrderAmount } from '@/lib/order-deposit';

export type DepositPolicy = {
  percent: number;
  minAmount: number;
  highOrderAmount: number;
};

export const DEPOSIT_POLICY_FALLBACK: DepositPolicy = {
  percent: DEPOSIT_PERCENT,
  minAmount: DEPOSIT_MIN_VND,
  highOrderAmount: HIGH_UNIT_PRICE_VND,
};

export type DepositPolicyApi = {
  partial_percent?: number;
  min_amount?: number;
  high_order_amount?: number;
};

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

export function depositPolicyFromApi(data: DepositPolicyApi | null | undefined): DepositPolicy {
  return {
    percent: normalizePercent(data?.partial_percent) ?? DEPOSIT_PERCENT,
    minAmount: normalizeMinAmount(data?.min_amount),
    highOrderAmount: normalizeHighOrderAmount(Number(data?.high_order_amount)),
  };
}
