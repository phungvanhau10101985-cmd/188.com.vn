export const MAX_ORDER_DISCOUNT_PERCENT = 15;

export function maxOrderDiscountAmount(subtotal: number): number {
  if (!Number.isFinite(subtotal) || subtotal <= 0) return 0;
  return (subtotal * MAX_ORDER_DISCOUNT_PERCENT) / 100;
}

/** Cắt tổng giảm về tối đa 15% — ưu tiên giảm loyalty trước. */
export function applyTotalOrderDiscountCap(
  subtotal: number,
  welcome: number,
  birthday: number,
  loyalty: number,
): { welcome: number; birthday: number; loyalty: number; capped: boolean } {
  let w = Math.max(0, welcome);
  let b = Math.max(0, birthday);
  let l = Math.max(0, loyalty);
  const maxTotal = maxOrderDiscountAmount(subtotal);
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
