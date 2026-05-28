import type { Product, SiteSaleCalendarState } from '@/types/api';
import { applyBirthdayDiscount } from '@/lib/birthday-discount';

export function formatCountdownParts(targetIso: string | null | undefined): {
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
  expired: boolean;
} | null {
  if (!targetIso) return null;
  const target = new Date(targetIso).getTime();
  if (!Number.isFinite(target)) return null;
  const diff = target - Date.now();
  if (diff <= 0) return { days: 0, hours: 0, minutes: 0, seconds: 0, expired: true };
  const totalSec = Math.floor(diff / 1000);
  const days = Math.floor(totalSec / 86400);
  const hours = Math.floor((totalSec % 86400) / 3600);
  const minutes = Math.floor((totalSec % 3600) / 60);
  const seconds = totalSec % 60;
  return { days, hours, minutes, seconds, expired: false };
}

export function formatCountdownLabel(targetIso: string | null | undefined): string {
  const parts = formatCountdownParts(targetIso);
  if (!parts) return '';
  if (parts.expired) return 'Đã kết thúc';
  if (parts.days > 0) return `${parts.days} ngày ${parts.hours} giờ`;
  if (parts.hours > 0) return `${parts.hours} giờ ${parts.minutes} phút`;
  return `${parts.minutes} phút ${parts.seconds} giây`;
}

export function resolveProductDisplayPricing(
  product: Product,
  birthdayActive: boolean,
  birthdayPercent: number,
) {
  const site = product.site_sale;
  const listPrice = site?.list_price ?? product.original_price ?? product.price ?? 0;
  const sitePhase = site?.phase ?? null;

  let beforeBirthday = product.price ?? 0;
  let compareAt: number | null = null;

  if (sitePhase === 'active') {
    beforeBirthday = product.price ?? listPrice;
    compareAt = listPrice > beforeBirthday ? listPrice : product.original_price ?? null;
  } else if (sitePhase === 'teaser') {
    beforeBirthday = listPrice;
    compareAt = null;
  } else if (product.original_price && product.original_price > product.price) {
    beforeBirthday = product.price;
    compareAt = product.original_price;
  }

  const displayPrice = birthdayActive
    ? applyBirthdayDiscount(beforeBirthday, birthdayPercent)
    : beforeBirthday;

  const siteSavings = site?.savings_amount ?? 0;
  const expectedSalePrice = site?.expected_sale_price ?? null;

  return {
    displayPrice,
    compareAt,
    listPrice,
    sitePhase,
    siteSavings,
    expectedSalePrice,
    sitePercent: site?.percent ?? 0,
    siteLabel: site?.event_label ?? null,
  };
}

export function siteSaleBannerMessage(state: SiteSaleCalendarState | null): string | null {
  if (!state?.enabled || !state.phase) return null;
  const pct = state.discount_percent ?? 0;
  const label = state.event_label ?? 'Sale';
  if (state.phase === 'teaser') {
    return `${label} sắp diễn ra — giảm ${pct}% trong ngày sale. Còn ${formatCountdownLabel(state.countdown_to)}`;
  }
  if (state.phase === 'active') {
    return `${label} đang diễn ra — giảm ${pct}% toàn website. Kết thúc sau ${formatCountdownLabel(state.countdown_to)}`;
  }
  return null;
}
