'use client';

import type { SiteSaleProductPricing } from '@/types/api';

type Props = {
  siteSale?: SiteSaleProductPricing | null;
  className?: string;
};

/** Badge góc ảnh — teaser / active site sale. */
export default function SiteSaleProductBadge({ siteSale, className = '' }: Props) {
  const phase = siteSale?.phase;
  if (!phase) return null;

  const isTeaser = phase === 'teaser';
  const pct = siteSale?.percent ?? 0;

  return (
    <div
      className={`pointer-events-none absolute left-2 top-2 z-[2] rounded-md px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-white shadow-md sm:text-xs ${
        isTeaser ? 'bg-amber-600' : 'bg-red-600'
      } ${className}`}
      aria-hidden
    >
      {isTeaser ? `Sắp -${pct}%` : `Sale -${pct}%`}
    </div>
  );
}
