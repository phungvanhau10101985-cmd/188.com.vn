import {
  DEPOSIT_MIN_VND,
  DEPOSIT_PERCENT,
  HIGH_UNIT_MIN_PERCENT,
  HIGH_UNIT_PRICE_VND,
} from '@/lib/business-info';

export { HIGH_UNIT_MIN_PERCENT, HIGH_UNIT_PRICE_VND };

/** Đơn giá >= mốc đơn lớn: một mình dòng đó đã đủ điều kiện. */
export function lineHitsHighUnitPrice(unitPrice: number, threshold: number = HIGH_UNIT_PRICE_VND): boolean {
  const price = Math.round(Number(unitPrice) || 0);
  return price >= normalizeHighOrderAmount(threshold);
}

/** Giá trị hàng của đơn >= mốc thì dùng % cọc của đơn lớn. */
export function orderHitsHighValue(goods: number, threshold: number = HIGH_UNIT_PRICE_VND): boolean {
  const amount = Math.round(Number(goods) || 0);
  return amount >= normalizeHighOrderAmount(threshold);
}

export function normalizeHighOrderAmount(raw: number): number {
  const n = Math.round(Number(raw));
  if (!Number.isFinite(n) || n < 100_000) return HIGH_UNIT_PRICE_VND;
  if (n > 500_000_000) return 500_000_000;
  return n;
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

/** % cọc một phần. Dưới mốc dùng % đơn nhỏ; từ mốc trở lên dùng % đơn lớn. */
export function partialPercentForLines(
  configured: number,
  highOrderValue: boolean,
  highPercent: number = HIGH_UNIT_MIN_PERCENT,
): number {
  const pct = Math.round(Number(configured));
  const applied = pct >= 1 && pct <= 99 ? pct : DEPOSIT_PERCENT;
  if (!highOrderValue) return applied;
  const high = Math.round(Number(highPercent));
  return high >= 1 && high <= 99 ? high : HIGH_UNIT_MIN_PERCENT;
}

export function partialPercentForGoods(
  configured: number,
  goods: number,
  threshold: number = HIGH_UNIT_PRICE_VND,
  highPercent: number = HIGH_UNIT_MIN_PERCENT,
): number {
  return partialPercentForLines(configured, orderHitsHighValue(goods, threshold), highPercent);
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
