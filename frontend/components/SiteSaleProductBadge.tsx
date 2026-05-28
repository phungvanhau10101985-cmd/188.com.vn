'use client';

import type { SiteSaleProductPricing } from '@/types/api';
import { siteSaleDateBadgeLabel } from '@/lib/site-sale';

type Props = {
  siteSale?: SiteSaleProductPricing | null;
  className?: string;
};

/** Badge góc ảnh — «28/5 - 6%» (teaser / active). */
export default function SiteSaleProductBadge({ siteSale, className = '' }: Props) {
  const phase = siteSale?.phase;
  if (!phase || !siteSale) return null;

  const label = siteSaleDateBadgeLabel(siteSale);
  if (!label) return null;

  const isTeaser = phase === 'teaser';

  return (
    <div
      className={`pointer-events-none absolute left-2 top-2 z-[2] rounded-md px-2 py-1 text-[10px] font-bold tracking-tight text-white shadow-md sm:text-xs ${
        isTeaser ? 'bg-amber-600' : 'bg-red-600'
      } ${className}`}
      aria-hidden
    >
      {label}
    </div>
  );
}
