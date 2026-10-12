import {
  DEPOSIT_MIN_VND,
  DEPOSIT_PERCENT,
  HIGH_UNIT_MIN_PERCENT,
  HIGH_UNIT_PRICE_VND,
} from '@/lib/business-info';

export { HIGH_UNIT_MIN_PERCENT, HIGH_UNIT_PRICE_VND };

/** Đơn giá >= 3.000.000đ thì dòng hàng thuộc nhóm cọc tối thiểu 30%. */
export function lineHitsHighUnitPrice(unitPrice: number): boolean {
  const price = Math.round(Number(unitPrice) || 0);
  return price >= HIGH_UNIT_PRICE_VND;
}

export function cartLineUnitPrice(item: {
  unit_price?: number | null;
  product_price?: number | null;
  product_data?: { price?: number | null } | null;
}): number {
  const raw = item.unit_price ?? item.product_price ?? item.product_data?.price ?? 0;
  const n = Number(raw);
  return Number.isFinite(n) ? n : 0;
}

/** % cọc một phần. Có đơn giá >= 3.000.000đ thì không thấp hơn 30%. */
export function partialPercentForLines(configured: number, hasHighUnitPrice: boolean): number {
  const pct = Math.round(Number(configured));
  const applied = pct >= 1 && pct <= 99 ? pct : DEPOSIT_PERCENT;
  if (hasHighUnitPrice) return Math.max(applied, HIGH_UNIT_MIN_PERCENT);
  return applied;
}

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
