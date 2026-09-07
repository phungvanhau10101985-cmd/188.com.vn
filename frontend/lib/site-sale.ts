import type { Product, SiteSaleCalendarState, SiteSaleProductPricing } from '@/types/api';
import { applyBirthdayDiscount, BIRTHDAY_PROGRAM_NAME } from '@/lib/birthday-discount';
import { isGoogleDiscountCartLine } from '@/lib/google-automated-discount';
import { applyCatalogStackedDiscount } from '@/lib/order-discount-limits';
import {
  isWarehouseCartLine,
  isWarehouseClearanceProduct,
  productShowsClearanceOnCard,
  resolveWarehouseCartLineUnitPricing,
} from '@/lib/warehouse-clearance';

/** Flash sale cá nhân hóa — không chồng sale lịch / không đụng hàng kho. */
export function isFlashSalePricing(
  sale?: SiteSaleProductPricing | null,
): boolean {
  if (!sale) return false;
  if (sale.kind === 'flash') return true;
  return (sale.event_label || '').trim().toLowerCase() === 'flash sale';
}

function productHasActiveFlash(product: Product): boolean {
  return (
    isFlashSalePricing(product.flash_sale) ||
    isFlashSalePricing(product.site_sale)
  );
}

/**
 * SSR/listing cache không có phiên khách — gắn flash từ block đã tải trên client.
 * Hàng kho và SP đã có flash từ API giữ nguyên.
 */
export function mergeProductFlashSale(
  product: Product,
  flashById?: Record<number, SiteSaleProductPricing> | null,
): Product {
  if (!flashById || isWarehouseClearanceProduct(product)) return product;
  if (productHasActiveFlash(product)) return product;
  const sale = flashById[product.id];
  if (!sale || !isFlashSalePricing(sale) || (sale.percent ?? 0) <= 0) return product;
  const listPrice = Math.max(
    0,
    sale.list_price ?? product.original_price ?? product.price ?? 0,
  );
  const displayPrice = Math.max(0, sale.display_price ?? product.price ?? 0);
  if (listPrice <= 0 || displayPrice <= 0) return product;
  return {
    ...product,
    price: displayPrice,
    original_price: listPrice,
    site_sale: sale,
    flash_sale: sale,
  };
}

export function cartLineHasActiveFlash(item: CartLinePricingInput): boolean {
  if (isFlashSalePricing(item.site_sale)) return true;
  const data = item.product_data as { flash_sale?: SiteSaleProductPricing } | undefined;
  return isFlashSalePricing(data?.flash_sale);
}

export const FLASH_SALE_PROGRAM_NAME = 'Flash sale';
export const WAREHOUSE_SALE_PROGRAM_NAME = 'Sale thanh lý kho';

/** Ngày sale trùng tháng dạng «9/9». */
export function calendarSaleDayMonth(
  sale?: SiteSaleProductPricing | null,
  calendar?: Pick<SiteSaleCalendarState, 'event_date' | 'event_label'> | null,
): string | null {
  const dateStr = String(sale?.event_date || calendar?.event_date || '').slice(0, 10);
  if (dateStr.includes('-')) {
    const parts = dateStr.split('-').map(Number);
    const month = parts[1];
    const day = parts[2];
    if (month && day) return `${day}/${month}`;
  }
  const raw = `${sale?.event_label ?? ''} ${calendar?.event_label ?? ''}`;
  const hit = raw.match(/(\d{1,2})\s*\/\s*(\d{1,2})/);
  if (hit) return `${Number(hit[1])}/${Number(hit[2])}`;
  return null;
}

/** «Sale 9/9» — luôn ghi rõ ngày trùng tháng. */
export function calendarSaleProgramLabel(
  sale?: SiteSaleProductPricing | null,
  calendar?: Pick<SiteSaleCalendarState, 'event_date' | 'event_label'> | null,
): string {
  const dayMonth = calendarSaleDayMonth(sale, calendar);
  if (dayMonth) return `Sale ${dayMonth}`;
  return 'Sale trùng ngày-tháng';
}

export function siteSaleProgramLabel(
  sale?: SiteSaleProductPricing | null,
  calendar?: Pick<SiteSaleCalendarState, 'event_date' | 'event_label'> | null,
): string {
  if (sale && isFlashSalePricing(sale)) return FLASH_SALE_PROGRAM_NAME;
  return calendarSaleProgramLabel(sale, calendar);
}

/** Ghép tên chương trình đang giảm giá: «Sale 9/9 + CMSN», «Flash sale», «Sale thanh lý kho». */
export function stackedSaleProgramLabel(opts: {
  isWarehouse?: boolean;
  isFlash?: boolean;
  siteLabel?: string | null;
  birthday?: boolean;
}): string {
  if (opts.isWarehouse) return WAREHOUSE_SALE_PROGRAM_NAME;
  const parts: string[] = [];
  if (opts.isFlash) parts.push(FLASH_SALE_PROGRAM_NAME);
  else if (opts.siteLabel?.trim()) parts.push(opts.siteLabel.trim());
  if (opts.birthday) parts.push(BIRTHDAY_PROGRAM_NAME);
  return parts.join(' + ');
}

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
    flash_sale?: SiteSaleProductPricing;
  };
  quantity: number;
};

export function formatCountdownParts(
  targetIso: string | null | undefined,
  nowMs?: number | null,
): {
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
  expired: boolean;
} | null {
  if (!targetIso) return null;
  const target = new Date(targetIso).getTime();
  if (!Number.isFinite(target)) return null;
  const now = nowMs ?? Date.now();
  const diff = target - now;
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

/**
 * Giá đầu thẻ SP có box kho: sale site trên giá list catalog (original_price / price gốc),
 * không dùng giá kho đã giảm 60%. Giá kho chỉ hiển thị trong ProductCardClearanceMeta.
 */
export function productForCatalogCardPricing(
  product: Product,
  calendar: SiteSaleCalendarState | null | undefined,
): Product {
  if (!productShowsClearanceOnCard(product)) {
    return mergeProductSiteSaleFromCalendar(product, calendar);
  }
  const listPrice =
    product.original_price != null && product.original_price > (product.price ?? 0)
      ? product.original_price
      : Math.max(0, Number(product.price ?? 0));
  const catalogStub: Product = {
    ...product,
    price: listPrice,
    original_price: undefined,
    is_warehouse_clearance: false,
    site_sale: undefined,
  };
  return mergeProductSiteSaleFromCalendar(catalogStub, calendar);
}

/** Gắn / bổ sung site_sale từ calendar khi SSR chưa có (vd. test sale sau đăng nhập). */
export function mergeProductSiteSaleFromCalendar(
  product: Product,
  calendar: SiteSaleCalendarState | null | undefined,
): Product {
  // Hàng kho thanh lý có giá riêng — không chồng Sale site (6/6, …) lên giá đã giảm kho.
  if (isWarehouseClearanceProduct(product)) return product;
  if (productHasActiveFlash(product)) return product;
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
  if (isGoogleDiscountCartLine(item)) return item;
  if (cartLineHasActiveFlash(item)) return item;
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

function sumCartLineSiteKindSavings(
  items: CartLinePricingInput[],
  calendar: SiteSaleCalendarState | null | undefined,
  kind: 'flash' | 'calendar' | 'all',
): number {
  return items.reduce((sum, item) => {
    if (isWarehouseCartLine(item)) return sum;
    const merged = mergeCartLineSiteSaleFromCalendar(item, calendar);
    const isFlash = cartLineHasActiveFlash(merged);
    if (kind === 'flash' && !isFlash) return sum;
    if (kind === 'calendar' && isFlash) return sum;
    const pricing = resolveCartLineDisplayPricing(merged, false, 0);
    return sum + pricing.siteLineSavings;
  }, 0);
}

/** Sale dòng (flash + trùng tháng) — không gồm thanh lý kho. */
export function sumCartLineSiteSaleSavings(
  items: CartLinePricingInput[],
  calendar?: SiteSaleCalendarState | null,
): number {
  return sumCartLineSiteKindSavings(items, calendar, 'all');
}

export function sumCartLineFlashSaleSavings(
  items: CartLinePricingInput[],
  calendar?: SiteSaleCalendarState | null,
): number {
  return sumCartLineSiteKindSavings(items, calendar, 'flash');
}

export function sumCartLineCalendarSaleSavings(
  items: CartLinePricingInput[],
  calendar?: SiteSaleCalendarState | null,
): number {
  return sumCartLineSiteKindSavings(items, calendar, 'calendar');
}

/** Tiết kiệm từ giá thanh lý kho (độc lập sale site). */
export function sumCartLineClearanceSavings(items: CartLinePricingInput[]): number {
  return items.reduce((sum, item) => {
    if (!isWarehouseCartLine(item)) return sum;
    const pricing = resolveCartLineDisplayPricing(item, false, 0);
    return sum + pricing.lineSavings;
  }, 0);
}

/** Nhãn badge góc ảnh: «Sale 9/9 -6%» / «Flash sale -6%». */
export function siteSaleDateBadgeLabel(siteSale: SiteSaleProductPricing): string | null {
  const pct = siteSale.percent ?? 0;
  if (pct <= 0) return null;

  if (isFlashSalePricing(siteSale)) {
    return `${FLASH_SALE_PROGRAM_NAME} -${pct}%`;
  }

  const dayMonth = calendarSaleDayMonth(siteSale);
  if (dayMonth) return `Sale ${dayMonth} -${pct}%`;

  return `${calendarSaleProgramLabel(siteSale)} -${pct}%`;
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
  const whListFromDb =
    product.original_price != null && product.original_price > (product.price ?? 0)
      ? product.original_price
      : null;
  if (isWhLine && whListFromDb != null) {
    const beforeBirthday = Math.max(0, Number(product.price ?? 0));
    const displayPrice = beforeBirthday;
    const compareUnitPrice = whListFromDb;
    const savingsAmount = Math.max(0, compareUnitPrice - displayPrice);
    const discountPercent =
      compareUnitPrice > 0
        ? Math.max(
            0,
            Math.min(100, Math.round((savingsAmount / compareUnitPrice) * 100)),
          )
        : 0;
    return {
      displayPrice,
      compareAt: compareUnitPrice,
      compareUnitPrice,
      savingsAmount,
      birthdaySavingsAmount: 0,
      listPrice: compareUnitPrice,
      sitePhase: null,
      siteSavings: 0,
      expectedSalePrice: null,
      sitePercent: discountPercent,
      siteLabel: WAREHOUSE_SALE_PROGRAM_NAME,
      countdownTo: null,
      beforeBirthday,
      discountPercent,
      isWarehouseClearance: true,
      isFlashSale: false,
      discountCapped: false,
      effectiveBirthdayPercent: 0,
    };
  }
  if (isWhLine && whPct > 0) {
    const listPrice = Math.max(
      0,
      Number(product.original_price ?? product.price ?? 0),
    );
    let beforeBirthday = Math.max(0, Number(product.price ?? listPrice));
    if (beforeBirthday >= listPrice || product.original_price == null) {
      beforeBirthday = Math.max(0, Math.round(listPrice * (1 - whPct / 100)));
    }
    const displayPrice = beforeBirthday;
    const compareUnitPrice =
      listPrice > displayPrice ? listPrice : null;
    const savingsAmount = compareUnitPrice != null ? listPrice - displayPrice : 0;
    return {
      displayPrice,
      compareAt: compareUnitPrice,
      compareUnitPrice,
      savingsAmount,
      birthdaySavingsAmount: 0,
      listPrice,
      sitePhase: null,
      siteSavings: 0,
      expectedSalePrice: null,
      sitePercent: 0,
      siteLabel: WAREHOUSE_SALE_PROGRAM_NAME,
      countdownTo: null,
      beforeBirthday,
      isFlashSale: false,
      isWarehouseClearance: true,
      discountCapped: false,
      effectiveBirthdayPercent: 0,
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

  const stacked = applyCatalogStackedDiscount({
    listPrice,
    afterLinePrograms: beforeBirthday,
    birthdayActive,
    birthdayPercent,
  });
  const displayPrice = stacked.displayPrice;
  const birthdaySavingsAmount = stacked.birthdaySavings;

  const sitePercent = site?.percent ?? 0;
  let siteSavings = site?.savings_amount ?? 0;
  let expectedSalePrice = site?.expected_sale_price ?? null;

  if (sitePhase === 'teaser' && sitePercent > 0 && siteSavings <= 0) {
    siteSavings = Math.round(listPrice * sitePercent / 100);
  }
  if (sitePhase === 'teaser' && expectedSalePrice == null && siteSavings > 0) {
    expectedSalePrice = Math.max(0, listPrice - siteSavings);
  }

  const compareUnitPrice =
    listPrice > displayPrice
      ? listPrice
      : compareAt != null && compareAt > displayPrice
        ? compareAt
        : null;

  const savingsAmount =
    compareUnitPrice != null ? Math.max(0, compareUnitPrice - displayPrice) : siteSavings;

  return {
    displayPrice,
    compareAt: compareUnitPrice ?? compareAt,
    compareUnitPrice,
    savingsAmount,
    birthdaySavingsAmount,
    listPrice,
    sitePhase,
    siteSavings,
    expectedSalePrice,
    sitePercent,
    siteLabel: isFlashSalePricing(site)
      ? FLASH_SALE_PROGRAM_NAME
      : sitePhase && sitePercent > 0
        ? calendarSaleProgramLabel(site)
        : null,
    countdownTo: site?.countdown_to ?? null,
    beforeBirthday,
    isFlashSale: isFlashSalePricing(site),
    isWarehouseClearance: false,
    discountCapped: stacked.capped,
    effectiveBirthdayPercent: stacked.effectiveBirthdayPercent,
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
    const displayUnitPrice = wh.displayPrice;
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
      siteLabel: WAREHOUSE_SALE_PROGRAM_NAME,
      siteLineSavings: 0,
      siteUnitSavings: 0,
      teaserUnitSavings: 0,
      teaserLineSavings: 0,
      expectedSaleUnitPrice: null,
      expectedLineTotal: null,
      countdownTo: null,
      beforeBirthday: wh.displayPrice,
      isFlashSale: false,
      birthdayLineSavings: 0,
      birthdayUnitSavings: 0,
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
  const googleLine = isGoogleDiscountCartLine(item);

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

  const displayUnitPrice =
    birthdayActive && !googleLine
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

  const isTeaser = sitePhase === 'teaser' && sitePercent > 0;
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
    siteLabel: isFlashSalePricing(site)
      ? FLASH_SALE_PROGRAM_NAME
      : sitePhase && sitePercent > 0
        ? calendarSaleProgramLabel(site)
        : null,
    siteSavings,
    expectedSalePrice,
    expectedSaleUnitPrice,
    expectedLineTotal,
    teaserUnitSavings,
    teaserLineSavings,
    countdownTo: site?.countdown_to ?? null,
    beforeBirthday,
    isFlashSale: isFlashSalePricing(site),
  };
}

export function siteSaleBannerMessage(state: SiteSaleCalendarState | null): string | null {
  if (!state?.enabled || !state.phase) return null;
  const pct = state.discount_percent ?? 0;
  const label = calendarSaleProgramLabel(null, state);
  if (state.phase === 'teaser') {
    return `${label} sắp diễn ra — giảm ${pct}% vào ${label}. Còn ${formatCountdownLabel(state.countdown_to)}`;
  }
  if (state.phase === 'active') {
    return `${label} đang diễn ra — giảm ${pct}% toàn website. Kết thúc sau ${formatCountdownLabel(state.countdown_to)}`;
  }
  return null;
}
