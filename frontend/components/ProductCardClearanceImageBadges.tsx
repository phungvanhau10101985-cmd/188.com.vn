'use client';

import { useMemo } from 'react';
import type { Product } from '@/types/api';
import {
  getClearanceCardHero,
  productShowsClearanceOnCard,
  resolveClearanceCardHeroPercent,
} from '@/lib/warehouse-clearance';

type ProductCardClearanceImageBadgesProps = {
  product: Product;
  /** Thẻ lưới nhỏ — badge % và size nhỏ hơn một chút. */
  compact?: boolean;
  className?: string;
};

/** Badge % sale to + size trên góc ảnh thẻ SP (thanh lý xả kho). */
export default function ProductCardClearanceImageBadges({
  product,
  compact = false,
  className = '',
}: ProductCardClearanceImageBadgesProps) {
  const hero = useMemo(() => getClearanceCardHero(product), [product]);
  const discountPercent = useMemo(
    () => resolveClearanceCardHeroPercent(product),
    [product],
  );

  if (!productShowsClearanceOnCard(product) || discountPercent <= 0) return null;

  const pctClass = compact
    ? 'px-2.5 py-1.5 text-xl leading-none'
    : 'px-3 py-2 text-2xl sm:text-3xl leading-none';
  const sizeClass = compact
    ? 'px-2 py-0.5 text-[11px] sm:text-xs'
    : 'px-2.5 py-1 text-xs sm:text-sm';

  return (
    <div
      className={`pointer-events-none absolute left-2 top-2 z-[3] flex max-w-[calc(100%-3.5rem)] flex-col items-start gap-1 ${className}`}
      aria-label={`Giảm ${discountPercent}% thanh lý xả kho${hero?.sizeBadge ? `, size ${hero.sizeBadge}` : ''}`}
    >
      <span
        className={`inline-flex rounded-lg bg-gradient-to-br from-red-600 to-[#ea580c] font-black tracking-tight text-white shadow-lg ring-2 ring-white ${pctClass}`}
      >
        -{discountPercent}%
      </span>
      {hero?.sizeBadge ? (
        <span
          className={`inline-flex max-w-full truncate rounded-md bg-gray-900/88 font-bold uppercase tracking-wide text-white shadow-md ring-1 ring-white/40 ${sizeClass}`}
        >
          Size {hero.sizeBadge}
        </span>
      ) : null}
    </div>
  );
}
