import { DEPOSIT_MIN_VND, DEPOSIT_PERCENT } from '@/lib/business-info';

/** Cọc một phần: % giá trị hàng, không thấp hơn sàn, không vượt giá trị hàng. */
export function partialDepositAmount(
  goods: number,
  percent: number = DEPOSIT_PERCENT,
  minAmount: number = DEPOSIT_MIN_VND,
): number {
  const base = Math.max(0, Math.round(Number(goods) || 0));
  if (base <= 0) return 0;
  const pct = Math.round(Number(percent));
  const applied = pct >= 1 && pct <= 99 ? pct : DEPOSIT_PERCENT;
  const raw = Math.round((base * applied) / 100);
  const floorRaw = Math.round(Number(minAmount));
  const floor = floorRaw >= DEPOSIT_MIN_VND ? floorRaw : DEPOSIT_MIN_VND;
  return Math.min(base, Math.max(raw, floor));
}

export function formatDepositMinVnd(amount: number = DEPOSIT_MIN_VND): string {
  const n = Math.round(Number(amount));
  const safe = Number.isFinite(n) && n >= DEPOSIT_MIN_VND ? n : DEPOSIT_MIN_VND;
  return `${new Intl.NumberFormat('vi-VN').format(safe)}đ`;
}

/**
 * Sau khi POST tạo đơn: đi thẳng trang đặt cọc nếu backend trả đơn chờ cọc.
 */
export function shouldRedirectToDepositAfterCreate(order: {
  requires_deposit?: boolean;
  status?: string;
}): boolean {
  return Boolean(order.requires_deposit) && String(order.status ?? '') === 'waiting_deposit';
}
