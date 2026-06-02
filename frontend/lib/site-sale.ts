import type { Product, SiteSaleCalendarState, SiteSaleProductPricing } from '@/types/api';
import { applyBirthdayDiscount } from '@/lib/birthday-discount';
import {
  isWarehouseCartLine,
  resolveWarehouseCartLineUnitPricing,
} from '@/lib/warehouse-clearance';

type CartLinePricingInput = {
  product_price?: number;
  list_price?: number;
  original_price?: number;
  site_sale?: SiteSaleProductPricing | null;
  product_code?: string | null;
  product_data?: {
    original_price?: number;
    price?: number;
    list_price?: number;
    product_id?: string;
    is_warehouse_clearance?: boolean;
    warehouse_clearance_percent?: number;
  };
  quantity: number;
};

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

/** Nhãn live trên ảnh SP — luôn có giờ:phút:giây, kèm ngày nếu còn ≥ 1 ngày. */
export function formatCountdownCompact(targetIso: string | null | undefined): string {
  const parts = formatCountdownParts(targetIso);
  if (!parts || parts.expired) return '';
  const hms = `${String(parts.hours).padStart(2, '0')}:${String(parts.minutes).padStart(2, '0')}:${String(parts.seconds).padStart(2, '0')}`;
  if (parts.days > 0) {
    return `${parts.days} ngày ${hms}`;
  }
  return hms;
}

/** Gắn / bổ sung site_sale từ calendar khi SSR chưa có (vd. test sale sau đăng nhập). */
export function mergeProductSiteSaleFromCalendar(
  product: Product,
  calendar: SiteSaleCalendarState | null | undefined,
): Product {
  if (!calendar?.enabled || !calendar.phase) return product;

  const existing = product.site_sale;
  const pct = calendar.discount_percent ?? existing?.percent ?? 0;
  if (pct <= 0) return product;

  const base = Math.max(0, existing?.list_price ?? product.price ?? 0);
  const savings = Math.round(base * pct / 100);
  const salePrice = Math.max(0, base - savings);

  if (existing?.phase === calendar.phase && (existing.percent ?? 0) > 0) {
    const needsPatch =
      (!existing.countdown_to && calendar.countdown_to) ||
      (!existing.event_label && calendar.event_label) ||
      (!existing.event_date && calendar.event_date);
    if (!needsPatch) return product;
    return {
      ...product,
      site_sale: {
        ...existing,
        countdown_to: existing.countdown_to ?? calendar.countdown_to ?? null,
        event_label: existing.event_label ?? calendar.event_label ?? null,
        event_date: existing.event_date ?? calendar.event_date ?? null,
      },
    };
  }

  const siteSale: SiteSaleProductPricing = {
    list_price: base,
    display_price: calendar.phase === 'active' ? salePrice : base,
    savings_amount: savings,
    percent: pct,
    phase: calendar.phase,
    expected_sale_price: calendar.phase === 'teaser' ? salePrice : undefined,
    event_label: calendar.event_label ?? null,
    event_date: calendar.event_date ?? null,
    countdown_to: calendar.countdown_to ?? null,
  };

  const merged: Product = { ...product, site_sale: siteSale };
  if (calendar.phase === 'active' && savings > 0) {
    merged.original_price = base;
    merged.price = salePrice;
  }
  return merged;
}

/** Gắn site_sale cho dòng giỏ khi API thiếu — dùng trạng thái sale toàn giỏ. */
export function mergeCartLineSiteSaleFromCalendar<T extends CartLinePricingInput>(
  item: T,
  calendar: SiteSaleCalendarState | null | undefined,
): T {
  if (isWarehouseCartLine(item)) return item;
  if (!calendar?.enabled || !calendar.phase) return item;

  const existing = item.site_sale;
  const pct = calendar.discount_percent ?? existing?.percent ?? 0;
  if (pct <= 0) return item;

  const base = Math.max(
    0,
    existing?.list_price ??
      item.list_price ??
      item.product_data?.list_price ??
      item.product_data?.original_price ??
      item.product_price ??
      item.product_data?.price ??
      0,
  );
  const savings = Math.round(base * pct / 100);
  const salePrice = Math.max(0, base - savings);

  if (existing?.phase === calendar.phase && (existing.percent ?? 0) > 0) {
    const needsPatch =
      (!existing.countdown_to && calendar.countdown_to) ||
      (!existing.event_label && calendar.event_label) ||
      (!existing.event_date && calendar.event_date);
    if (!needsPatch) {
      return { ...item, list_price: base };
    }
    return {
      ...item,
      list_price: base,
      site_sale: {
        ...existing,
        countdown_to: existing.countdown_to ?? calendar.countdown_to ?? null,
        event_label: existing.event_label ?? calendar.event_label ?? null,
        event_date: existing.event_date ?? calendar.event_date ?? null,
      },
    };
  }

  const siteSale: SiteSaleProductPricing = {
    list_price: base,
    display_price: calendar.phase === 'active' ? salePrice : base,
    savings_amount: savings,
    percent: pct,
    phase: calendar.phase,
    expected_sale_price: calendar.phase === 'teaser' ? salePrice : undefined,
    event_label: calendar.event_label ?? null,
    event_date: calendar.event_date ?? null,
    countdown_to: calendar.countdown_to ?? null,
  };

  return {
    ...item,
    list_price: base,
    site_sale: siteSale,
    original_price: calendar.phase === 'active' && savings > 0 ? base : item.original_price,
    product_price: calendar.phase === 'active' ? salePrice : base,
  };
}

export function resolveCartLineTotal(
  item: CartLinePricingInput,
  birthdayActive: boolean,
  birthdayPercent: number,
  calendar?: SiteSaleCalendarState | null,
): number {
  const merged = mergeCartLineSiteSaleFromCalendar(item, calendar);
  return resolveCartLineDisplayPricing(merged, birthdayActive, birthdayPercent).displayLineTotal;
}

/** Tổng tiền hàng sau site sale, trước sinh nhật / voucher — khớp backend cart subtotal. */
export function resolveCartLineCheckoutTotal(
  item: CartLinePricingInput,
  calendar?: SiteSaleCalendarState | null,
): number {
  return resolveCartLineTotal(item, false, 0, calendar);
}

export function sumCartLineCheckoutTotals(
  items: CartLinePricingInput[],
  calendar?: SiteSaleCalendarState | null,
): number {
  return items.reduce((sum, item) => sum + resolveCartLineCheckoutTotal(item, calendar), 0);
}

export function sumCartLineListSubtotal(
  items: CartLinePricingInput[],
  calendar?: SiteSaleCalendarState | null,
): number {
  return items.reduce((sum, item) => {
    const pricing = resolveCartLineDisplayPricing(
      mergeCartLineSiteSaleFromCalendar(item, calendar),
      false,
      0,
    );
    return sum + pricing.listPrice * Math.max(1, item.quantity || 1);
  }, 0);
}

/** Chỉ sale ngày trùng tháng — không gồm thanh lý kho. */
export function sumCartLineSiteSaleSavings(
  items: CartLinePricingInput[],
  calendar?: SiteSaleCalendarState | null,
): number {
  return items.reduce((sum, item) => {
    if (isWarehouseCartLine(item)) return sum;
    const pricing = resolveCartLineDisplayPricing(
      mergeCartLineSiteSaleFromCalendar(item, calendar),
      false,
      0,
    );
    return sum + pricing.siteLineSavings;
  }, 0);
}

/** Tiết kiệm từ giá thanh lý kho (độc lập sale site). */
export function sumCartLineClearanceSavings(items: CartLinePricingInput[]): number {
  return items.reduce((sum, item) => {
    if (!isWarehouseCartLine(item)) return sum;
    const pricing = resolveCartLineDisplayPricing(item, false, 0);
    return sum + pricing.lineSavings;
  }, 0);
}

/** Nhãn badge góc ảnh: «5/5 - 6%». */
export function siteSaleDateBadgeLabel(siteSale: SiteSaleProductPricing): string | null {
  const pct = siteSale.percent ?? 0;
  if (pct <= 0) return null;

  if (siteSale.event_date) {
    const parts = siteSale.event_date.slice(0, 10).split('-').map(Number);
    const m = parts[1];
    const d = parts[2];
    if (m && d) return `${d}/${m} - ${pct}%`;
  }

  const raw = (siteSale.event_label ?? '').trim();
  const fromLabel = raw.match(/(\d{1,2})\/(\d{1,2})/);
  if (fromLabel) return `${fromLabel[1]}/${fromLabel[2]} - ${pct}%`;

  return `-${pct}%`;
}

export function resolveProductDisplayPricing(
  product: Product,
  birthdayActive: boolean,
  birthdayPercent: number,
) {
  const whPct = Math.max(0, Math.min(100, product.warehouse_clearance?.discount_percent ?? 0));
  const isWhLine =
    product.is_warehouse_clearance === true ||
    String(product.product_id || '').includes('/');
  if (isWhLine && whPct > 0) {
    const listPrice = Math.max(
      0,
      Number(product.original_price ?? product.price ?? 0),
    );
    let beforeBirthday = Math.max(0, Number(product.price ?? listPrice));
    if (beforeBirthday >= listPrice || product.original_price == null) {
      beforeBirthday = Math.max(0, Math.round(listPrice * (1 - whPct / 100)));
    }
    const displayPrice = birthdayActive
      ? applyBirthdayDiscount(beforeBirthday, birthdayPercent)
      : beforeBirthday;
    const compareUnitPrice =
      listPrice > displayPrice ? listPrice : null;
    const savingsAmount = compareUnitPrice != null ? listPrice - displayPrice : 0;
    const birthdaySavingsAmount = birthdayActive
      ? Math.max(0, beforeBirthday - displayPrice)
      : 0;
    return {
      displayPrice,
      compareAt: compareUnitPrice,
      compareUnitPrice,
      savingsAmount,
      birthdaySavingsAmount,
      listPrice,
      sitePhase: null,
      siteSavings: 0,
      expectedSalePrice: null,
      sitePercent: 0,
      siteLabel: null,
      countdownTo: null,
      beforeBirthday,
    };
  }

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

  const sitePercent = site?.percent ?? 0;
  let siteSavings = site?.savings_amount ?? 0;
  let expectedSalePrice = site?.expected_sale_price ?? null;

  if (sitePhase === 'teaser' && sitePercent > 0 && siteSavings <= 0) {
    siteSavings = Math.round(listPrice * sitePercent / 100);
  }
  if (sitePhase === 'teaser' && expectedSalePrice == null && siteSavings > 0) {
    expectedSalePrice = Math.max(0, listPrice - siteSavings);
  }

  const compareUnitPrice = birthdayActive
    ? beforeBirthday > displayPrice
      ? beforeBirthday
      : null
    : compareAt != null && compareAt > displayPrice
      ? compareAt
      : null;

  const savingsAmount =
    compareUnitPrice != null ? Math.max(0, compareUnitPrice - displayPrice) : siteSavings;

  const birthdaySavingsAmount = birthdayActive
    ? Math.max(0, beforeBirthday - displayPrice)
    : 0;

  return {
    displayPrice,
    compareAt,
    compareUnitPrice,
    savingsAmount,
    birthdaySavingsAmount,
    listPrice,
    sitePhase,
    siteSavings,
    expectedSalePrice,
    sitePercent,
    siteLabel: site?.event_label ?? null,
    countdownTo: site?.countdown_to ?? null,
    beforeBirthday,
  };
}

export function resolveCartLineDisplayPricing(
  item: {
    product_price?: number;
    list_price?: number;
    original_price?: number;
    site_sale?: SiteSaleProductPricing | null;
    product_data?: {
      original_price?: number;
      price?: number;
      list_price?: number;
      is_warehouse_clearance?: boolean;
      warehouse_clearance_percent?: number;
      product_id?: string;
    };
    product_code?: string | null;
    quantity: number;
  },
  birthdayActive: boolean,
  birthdayPercent: number,
) {
  if (isWarehouseCartLine(item)) {
    const wh = resolveWarehouseCartLineUnitPricing(item);
    const qty = Math.max(1, item.quantity || 1);
    const displayUnitPrice = birthdayActive
      ? applyBirthdayDiscount(wh.displayPrice, birthdayPercent)
      : wh.displayPrice;
    const compareUnitPrice = wh.hasDiscount ? wh.originalPrice : null;
    const displayLineTotal = displayUnitPrice * qty;
    const compareLineTotal = compareUnitPrice != null ? compareUnitPrice * qty : null;
    const lineSavings = compareLineTotal != null ? compareLineTotal - displayLineTotal : 0;
    return {
      displayUnitPrice,
      compareUnitPrice,
      displayLineTotal,
      compareLineTotal,
      lineSavings: Math.max(0, lineSavings),
      listPrice: wh.listPrice,
      sitePhase: null as string | null,
      sitePercent: wh.percent,
      siteLabel: 'Thanh lý kho',
      siteLineSavings: 0,
      siteUnitSavings: 0,
      teaserUnitSavings: 0,
      teaserLineSavings: 0,
      expectedSaleUnitPrice: null,
      expectedLineTotal: null,
      countdownTo: null,
      beforeBirthday: wh.displayPrice,
    };
  }

  const site = item.site_sale;
  const listPrice = site?.list_price ?? item.list_price ?? item.original_price ?? item.product_data?.original_price ?? item.product_price ?? 0;
  const sitePhase = site?.phase ?? null;
  const sitePercent = site?.percent ?? 0;
  let siteSavings = site?.savings_amount ?? 0;
  let expectedSalePrice = site?.expected_sale_price ?? null;

  if (sitePhase === 'teaser' && sitePercent > 0 && siteSavings <= 0) {
    siteSavings = Math.round(listPrice * sitePercent / 100);
  }
  if (sitePhase === 'teaser' && expectedSalePrice == null && siteSavings > 0) {
    expectedSalePrice = Math.max(0, listPrice - siteSavings);
  }

  const unitSalePrice = item.product_price ?? item.product_data?.price ?? 0;

  let siteSaleUnitPrice = unitSalePrice;
  if (sitePhase === 'active' && sitePercent > 0) {
    const computedSale = Math.max(0, Math.round(listPrice * (1 - sitePercent / 100)));
    if (siteSaleUnitPrice <= 0 || siteSaleUnitPrice >= listPrice) {
      siteSaleUnitPrice = computedSale;
    }
  } else if (sitePhase === 'teaser') {
    siteSaleUnitPrice = listPrice;
  } else if (siteSaleUnitPrice <= 0) {
    siteSaleUnitPrice = listPrice;
  }

  const beforeBirthday = siteSaleUnitPrice;
  let compareAt: number | null = listPrice > beforeBirthday ? listPrice : item.original_price ?? null;

  if (sitePhase === 'teaser') {
    compareAt = null;
  } else if (sitePhase !== 'active' && item.original_price && item.original_price > siteSaleUnitPrice) {
    compareAt = item.original_price;
  } else if (
    sitePhase !== 'active' &&
    item.product_data?.original_price &&
    item.product_data.original_price > siteSaleUnitPrice
  ) {
    compareAt = item.product_data.original_price;
  }

  const displayUnitPrice = birthdayActive
    ? applyBirthdayDiscount(beforeBirthday, birthdayPercent)
    : beforeBirthday;

  const qty = Math.max(1, item.quantity || 1);
  const displayLineTotal = displayUnitPrice * qty;

  const compareUnitPrice =
    listPrice > displayUnitPrice
      ? listPrice
      : compareAt != null && compareAt > displayUnitPrice
        ? compareAt
        : null;

  const compareLineTotal = compareUnitPrice != null ? compareUnitPrice * qty : null;
  const siteUnitSavings =
    sitePhase === 'active' && sitePercent > 0
      ? Math.max(0, listPrice - beforeBirthday)
      : 0;
  const birthdayUnitSavings = birthdayActive
    ? Math.max(0, beforeBirthday - displayUnitPrice)
    : 0;
  const totalUnitSavings =
    compareUnitPrice != null
      ? Math.max(0, compareUnitPrice - displayUnitPrice)
      : siteUnitSavings + birthdayUnitSavings;
  const lineSavings = totalUnitSavings * qty;
  const siteLineSavings = siteUnitSavings * qty;
  const birthdayLineSavings = birthdayUnitSavings * qty;

  const isTeaser = sitePhase === 'teaser' && sitePercent > 0 && !birthdayActive;
  const expectedSaleUnitPrice =
    isTeaser && expectedSalePrice != null && expectedSalePrice > 0
      ? expectedSalePrice
      : isTeaser && sitePercent > 0
        ? Math.max(0, Math.round(listPrice * (1 - sitePercent / 100)))
        : null;
  const teaserUnitSavings =
    isTeaser && expectedSaleUnitPrice != null
      ? Math.max(0, displayUnitPrice - expectedSaleUnitPrice)
      : isTeaser && siteSavings > 0
        ? siteSavings
        : 0;
  const teaserLineSavings = teaserUnitSavings * qty;
  const expectedLineTotal = expectedSaleUnitPrice != null ? expectedSaleUnitPrice * qty : null;

  return {
    displayUnitPrice,
    displayLineTotal,
    compareAt,
    compareUnitPrice,
    compareLineTotal,
    lineSavings,
    siteLineSavings,
    birthdayLineSavings,
    siteUnitSavings,
    birthdayUnitSavings,
    listPrice,
    siteSaleUnitPrice: beforeBirthday,
    sitePhase,
    sitePercent,
    siteLabel: site?.event_label ?? null,
    siteSavings,
    expectedSalePrice,
    expectedSaleUnitPrice,
    expectedLineTotal,
    teaserUnitSavings,
    teaserLineSavings,
    countdownTo: site?.countdown_to ?? null,
    beforeBirthday,
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
