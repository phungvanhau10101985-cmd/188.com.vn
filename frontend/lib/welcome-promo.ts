export const WELCOME_PROMO_CODE = 'WELCOME188';
export const WELCOME_DISCOUNT_PERCENT = 10;
export const WELCOME_MAX_DISCOUNT = 200_000;

export interface AppliedWelcomePromo {
  code: string;
  discountPercent: number;
  maxDiscount: number;
}

export function calculateWelcomeDiscount(
  subtotal: number,
  promo: AppliedWelcomePromo | null
): number {
  if (!promo || subtotal <= 0) return 0;
  const raw = (subtotal * promo.discountPercent) / 100;
  return Math.min(raw, promo.maxDiscount);
}
