'use client';

import { BirthdayPromoImageBadge } from '@/components/BirthdayPromoProductMarkers';
import SiteSaleProductBadge from '@/components/SiteSaleProductBadge';
import type { SiteSaleProductPricing } from '@/types/api';

type Props = {
  siteSale?: SiteSaleProductPricing | null;
  birthdayActive?: boolean;
  birthdayPercent?: number;
  className?: string;
};

/** Flash / sale trùng tháng + sinh nhật xếp cột, không đè nhau. */
export default function ProductCardPromoBadges({
  siteSale,
  birthdayActive = false,
  birthdayPercent = 0,
  className = '',
}: Props) {
  const hasSite = Boolean(siteSale?.phase && (siteSale.percent ?? 0) > 0);
  const hasBirthday = birthdayActive && birthdayPercent > 0;
  if (!hasSite && !hasBirthday) return null;

  return (
    <div
      className={`pointer-events-none absolute left-2 top-2 z-[2] flex max-w-[calc(100%-3.5rem)] flex-col items-start gap-1 ${className}`}
    >
      {hasSite ? (
        <SiteSaleProductBadge siteSale={siteSale} embedded />
      ) : null}
      {hasBirthday ? (
        <BirthdayPromoImageBadge
          active
          percent={birthdayPercent}
          embedded
        />
      ) : null}
    </div>
  );
}
