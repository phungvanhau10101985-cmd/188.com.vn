'use client';

import type { SiteSaleProductPricing } from '@/types/api';
import { siteSaleDateBadgeLabel } from '@/lib/site-sale';

type Props = {
  siteSale?: SiteSaleProductPricing | null;
  className?: string;
  /** Nằm trong cột badge (không absolute). */
  embedded?: boolean;
};

/** Badge góc ảnh — «Sale 9/9 -6%» / «Flash sale -6%». */
export default function SiteSaleProductBadge({ siteSale, className = '', embedded = false }: Props) {
  const phase = siteSale?.phase;
  if (!phase || !siteSale) return null;

  const label = siteSaleDateBadgeLabel(siteSale);
  if (!label) return null;

  const isTeaser = phase === 'teaser';

  return (
    <div
      className={`${embedded ? 'relative' : 'pointer-events-none absolute left-2 top-2 z-[2]'} rounded-md px-2 py-1 text-[10px] font-bold tracking-tight text-white shadow-md sm:text-xs ${
        isTeaser ? 'bg-amber-600' : 'bg-red-600'
      } ${className}`}
      aria-hidden
    >
      {label}
    </div>
  );
}
