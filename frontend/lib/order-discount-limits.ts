export const MAX_ORDER_DISCOUNT_PERCENT = 15;

export function formatDiscountPercent(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

export type CappedPromoPercentDisplay =
  | { kind: 'nominal'; percent: number }
  | { kind: 'capped_site'; effectivePercent: number; sitePercent: number }
  | { kind: 'capped_promo'; effectivePercent: number; nominalPercent: number; cutPercent: number };

/** Nhãn % hiển thị khi promo bị trần 15% (site sale + mã/sinh nhật/hạng). */
export function resolveCappedPromoPercentDisplay(params: {
  listSubtotal: number;
  siteSaleSavings: number;
  siteSaleActive: boolean;
  discountCapped: boolean;
  rawAmount: number;
  appliedAmount: number;
  nominalPercent: number;
}): CappedPromoPercentDisplay {
  const {
    listSubtotal,
    siteSaleSavings,
    siteSaleActive,
    discountCapped,
    rawAmount,
    appliedAmount,
    nominalPercent,
  } = params;

  const wasCut = rawAmount > appliedAmount + 0.5;
  if (!wasCut || !discountCapped || appliedAmount <= 0) {
    return { kind: 'nominal', percent: nominalPercent };
  }

  const effectivePercent =
    listSubtotal > 0 ? (appliedAmount / listSubtotal) * 100 : 0;
  const sitePercent =
    listSubtotal > 0 ? (siteSaleSavings / listSubtotal) * 100 : 0;
  const cutPercent =
    listSubtotal > 0
      ? Math.max(0, (rawAmount - appliedAmount) / listSubtotal) * 100
      : 0;

  if (siteSaleActive && siteSaleSavings > 0) {
    return { kind: 'capped_site', effectivePercent, sitePercent };
  }

  return {
    kind: 'capped_promo',
    effectivePercent,
    nominalPercent,
    cutPercent,
  };
}

export function maxOrderDiscountAmount(subtotal: number): number {
  if (!Number.isFinite(subtotal) || subtotal <= 0) return 0;
  return (subtotal * MAX_ORDER_DISCOUNT_PERCENT) / 100;
}

/** Cắt welcome/sinh nhật/hạng về tối đa maxPromoAmount (ưu tiên cắt loyalty trước). */
export function applyPromoDiscountCap(
  maxPromoAmount: number,
  welcome: number,
  birthday: number,
  loyalty: number,
): { welcome: number; birthday: number; loyalty: number; capped: boolean } {
  let w = Math.max(0, welcome);
  let b = Math.max(0, birthday);
  let l = Math.max(0, loyalty);
  const maxTotal = Math.max(0, maxPromoAmount);
  const rawTotal = w + b + l;
  if (rawTotal <= maxTotal) {
    return { welcome: w, birthday: b, loyalty: l, capped: false };
  }

  let overflow = rawTotal - maxTotal;
  for (const key of ['loyalty', 'birthday', 'welcome'] as const) {
    if (overflow <= 0) break;
    if (key === 'loyalty') {
      const cut = Math.min(l, overflow);
      l -= cut;
      overflow -= cut;
    } else if (key === 'birthday') {
      const cut = Math.min(b, overflow);
      b -= cut;
      overflow -= cut;
    } else {
      const cut = Math.min(w, overflow);
      w -= cut;
      overflow -= cut;
    }
  }
  return { welcome: w, birthday: b, loyalty: l, capped: true };
}

/** Cắt tổng promo về tối đa 15% subtotal (không tính site sale). */
export function applyTotalOrderDiscountCap(
  subtotal: number,
  welcome: number,
  birthday: number,
  loyalty: number,
): { welcome: number; birthday: number; loyalty: number; capped: boolean } {
  return applyPromoDiscountCap(maxOrderDiscountAmount(subtotal), welcome, birthday, loyalty);
}

/**
 * Trần 15% trên giá gốc: site sale + promo không vượt 15%.
 * Ví dụ sale 6% + sinh nhật 10% = 16% → chỉ còn 15%.
 */
export function applyGrandOrderDiscountCap(
  listSubtotal: number,
  siteSaleSavings: number,
  welcome: number,
  birthday: number,
  loyalty: number,
): { welcome: number; birthday: number; loyalty: number; capped: boolean } {
  const maxTotal = maxOrderDiscountAmount(listSubtotal);
  const promoBudget = Math.max(0, maxTotal - Math.max(0, siteSaleSavings));
  const rawPromo = Math.max(0, welcome) + Math.max(0, birthday) + Math.max(0, loyalty);
  const result = applyPromoDiscountCap(promoBudget, welcome, birthday, loyalty);
  const capped = result.capped || siteSaleSavings + rawPromo > maxTotal;
  return { ...result, capped };
}
