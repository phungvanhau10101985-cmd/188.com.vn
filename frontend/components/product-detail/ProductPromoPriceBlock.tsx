'use client';

import { useEffect, useMemo, useState } from 'react';
import { useClientMounted } from '@/lib/use-client-mounted';
import { formatCountdownParts } from '@/lib/site-sale';
import { formatPrice } from '@/lib/utils';

export interface ProductPromoPriceBlockProps {
  displayPrice: number;
  compareUnitPrice?: number | null;
  savingsAmount?: number;
  expectedSalePrice?: number | null;
  sitePhase?: 'active' | 'teaser' | null;
  sitePercent?: number;
  siteLabel?: string | null;
  countdownTo?: string | null;
  birthdayActive?: boolean;
  birthdayPercent?: number;
  quantity?: number;
  size?: 'sm' | 'md' | 'lg';
  showQuantityTotal?: boolean;
  /** Nhãn badge % giảm (vd. «Thanh lý kho») — mặc định «Giảm giá». */
  promoLabel?: string | null;
  /** SP kho thanh lý — badge % nổi bật hơn. */
  clearanceHighlight?: boolean;
  className?: string;
}

export default function ProductPromoPriceBlock({
  displayPrice,
  compareUnitPrice = null,
  savingsAmount = 0,
  expectedSalePrice = null,
  sitePhase = null,
  sitePercent = 0,
  siteLabel = null,
  countdownTo = null,
  birthdayActive = false,
  birthdayPercent = 0,
  quantity = 1,
  size = 'md',
  showQuantityTotal = false,
  promoLabel = null,
  clearanceHighlight = false,
  className = '',
}: ProductPromoPriceBlockProps) {
  const clientMounted = useClientMounted();
  const [nowMs, setNowMs] = useState<number | null>(null);

  useEffect(() => {
    if (!clientMounted || !countdownTo || !sitePhase) return;
    const tick = () => setNowMs(Date.now());
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [clientMounted, countdownTo, sitePhase]);

  const countdownLive = useMemo(() => {
    if (!clientMounted || nowMs == null || !countdownTo) return '';
    const parts = formatCountdownParts(countdownTo, nowMs);
    if (!parts || parts.expired) return '';
    const hms = `${String(parts.hours).padStart(2, '0')}:${String(parts.minutes).padStart(2, '0')}:${String(parts.seconds).padStart(2, '0')}`;
    if (parts.days > 0) return `${parts.days} ngày ${hms}`;
    return hms;
  }, [countdownTo, nowMs]);

  const qty = Math.max(1, quantity);
  const unitSavings = Math.max(0, savingsAmount);
  const isTeaser = sitePhase === 'teaser' && sitePercent > 0 && !birthdayActive;
  const computedExpected =
    isTeaser && sitePercent > 0
      ? Math.max(0, Math.round(displayPrice * (1 - sitePercent / 100)))
      : null;
  const teaserExpected =
    expectedSalePrice != null && expectedSalePrice > 0
      ? expectedSalePrice
      : computedExpected;
  const teaserSavings =
    isTeaser && teaserExpected != null
      ? Math.max(0, displayPrice - teaserExpected)
      : isTeaser && sitePercent > 0
        ? Math.round(displayPrice * sitePercent / 100)
        : 0;
  const showActivePromo =
    !isTeaser &&
    compareUnitPrice != null &&
    compareUnitPrice > displayPrice &&
    unitSavings > 0;
  const showTeaserPromo = isTeaser && teaserSavings > 0;

  const activeDiscountPercent = useMemo(() => {
    if (showTeaserPromo && sitePercent > 0) return sitePercent;
    if (
      showActivePromo &&
      compareUnitPrice != null &&
      compareUnitPrice > displayPrice
    ) {
      return Math.max(
        1,
        Math.min(
          100,
          Math.round(((compareUnitPrice - displayPrice) / compareUnitPrice) * 100),
        ),
      );
    }
    return 0;
  }, [
    showTeaserPromo,
    showActivePromo,
    sitePercent,
    compareUnitPrice,
    displayPrice,
  ]);

  const showPercentBadge = activeDiscountPercent > 0 && (showActivePromo || showTeaserPromo);
  const percentBadgeClass = clearanceHighlight
    ? size === 'lg'
      ? 'min-w-[4.5rem] rounded-xl bg-red-600 px-3.5 py-2 text-lg font-extrabold text-white shadow-md ring-2 ring-red-400/40'
      : 'min-w-[3.5rem] rounded-lg bg-red-600 px-2.5 py-1.5 text-sm font-extrabold text-white shadow-md'
    : 'rounded bg-red-500 px-1.5 py-0.5 text-xs font-bold text-white';

  const priceClass =
    size === 'lg' ? 'text-3xl' : size === 'sm' ? 'text-2xl' : 'text-2xl md:text-3xl';
  const compareClass =
    size === 'sm'
      ? 'px-2.5 py-1 text-xs'
      : 'px-3 py-1 text-sm';

  const saleLabel = siteLabel?.trim() || 'Sale';
  const countdownPrefix =
    sitePhase === 'teaser'
      ? `${saleLabel} bắt đầu sau`
      : sitePhase === 'active'
        ? `${saleLabel} — còn`
        : null;

  return (
    <div className={`space-y-2 ${className}`}>
      {birthdayActive && unitSavings > 0 ? (
        <div className="inline-flex items-center gap-1.5 rounded-full bg-pink-600 px-3 py-1 text-xs font-bold text-white shadow-sm">
          <span aria-hidden>🎂</span>
          Giá sinh nhật đã giảm {birthdayPercent}%
        </div>
      ) : null}

      {sitePhase === 'active' && sitePercent > 0 && !birthdayActive ? (
        <div className="inline-flex items-center gap-1.5 rounded-full bg-red-600 px-3 py-1 text-xs font-bold text-white shadow-sm">
          <span aria-hidden>🔥</span>
          {siteLabel ?? 'Sale ngày trùng tháng'} — giảm {sitePercent}%
        </div>
      ) : null}

      {showTeaserPromo ? (
        <div className="inline-flex items-center gap-1.5 rounded-full bg-amber-500 px-3 py-1 text-xs font-bold text-white shadow-sm">
          <span aria-hidden>⏳</span>
          {siteLabel ?? 'Sắp sale'} — giảm {sitePercent}% trong ngày sale
        </div>
      ) : null}

      {showActivePromo &&
      activeDiscountPercent > 0 &&
      sitePhase !== 'active' &&
      !birthdayActive ? (
        <div
          className={`inline-flex items-center gap-2 rounded-full font-bold text-white shadow-sm ${
            clearanceHighlight
              ? 'bg-gradient-to-r from-red-600 to-orange-600 px-4 py-1.5 text-sm'
              : 'bg-red-600 px-3 py-1 text-xs'
          }`}
        >
          <span aria-hidden>{clearanceHighlight ? '🏷️' : '🔥'}</span>
          <span>
            {promoLabel?.trim() || (clearanceHighlight ? 'Thanh lý kho' : 'Giảm giá')} —{' '}
            <span className="tabular-nums">-{activeDiscountPercent}%</span>
          </span>
        </div>
      ) : null}

      {countdownPrefix && countdownLive ? (
        <div
          className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold sm:text-sm ${
            sitePhase === 'teaser'
              ? 'border border-amber-200 bg-amber-50 text-amber-900'
              : 'border border-red-200 bg-red-50 text-red-900'
          }`}
          role="timer"
          aria-live="polite"
          aria-atomic="true"
        >
          <span aria-hidden>⏱</span>
          <span>
            {countdownPrefix}{' '}
            <span className="font-bold tabular-nums tracking-tight">{countdownLive}</span>
          </span>
        </div>
      ) : null}

      <div
        className={`flex flex-wrap items-center gap-x-3 gap-y-2 ${
          clearanceHighlight && showActivePromo ? 'sm:items-center' : 'items-baseline'
        }`}
      >
        {showPercentBadge && clearanceHighlight && showActivePromo ? (
          <span
            className={percentBadgeClass}
            aria-label={`Giảm ${activeDiscountPercent} phần trăm`}
          >
            -{activeDiscountPercent}%
          </span>
        ) : null}

        <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2 gap-y-1">
          {showTeaserPromo ? (
            <span className="w-full text-[11px] font-semibold uppercase tracking-wide text-gray-500">
              Giá gốc
            </span>
          ) : null}
          {showActivePromo && !showTeaserPromo ? (
            <span className="w-full text-[11px] font-semibold uppercase tracking-wide text-gray-500">
              Giá thanh lý
            </span>
          ) : null}
          <span className={`${priceClass} font-extrabold text-[#ea580c]`}>
            {formatPrice(displayPrice)}
          </span>

          {showTeaserPromo ? (
            <>
              <span
                className={`inline-flex items-baseline gap-1 rounded-full border border-emerald-200 bg-emerald-50 font-semibold text-emerald-800 shadow-sm ${compareClass}`}
              >
                <span className="text-[10px] font-medium text-emerald-700">Giá sale dự kiến</span>
                <span>{formatPrice(teaserExpected!)}</span>
              </span>
              <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-amber-800 ring-1 ring-amber-200 sm:text-xs">
                Tiết kiệm dự kiến ~{formatPrice(teaserSavings)}
              </span>
              {!clearanceHighlight ? (
                <span className={percentBadgeClass}>-{activeDiscountPercent}%</span>
              ) : null}
            </>
          ) : null}

          {showActivePromo ? (
            <>
              <span
                className={`inline-flex items-baseline gap-1 rounded-full border border-gray-300 bg-white font-semibold text-gray-700 shadow-sm ${compareClass}`}
              >
                <span className="text-[10px] font-medium text-gray-500">Giá gốc</span>
                <span className="text-gray-800 line-through decoration-1 decoration-gray-400">
                  {formatPrice(compareUnitPrice!)}
                </span>
              </span>
              <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-emerald-700 ring-1 ring-emerald-200 sm:text-xs">
                Tiết kiệm {formatPrice(unitSavings)}
              </span>
              {showPercentBadge && !(clearanceHighlight && showActivePromo) ? (
                <span className={percentBadgeClass}>-{activeDiscountPercent}%</span>
              ) : null}
            </>
          ) : null}
        </div>
      </div>

      {showQuantityTotal ? (
        <div className="flex items-baseline justify-between text-sm">
          <span className="font-semibold text-gray-900">Tổng số:</span>
          <div className="text-right">
            <span className="text-lg font-bold text-[#ea580c]">
              {formatPrice(displayPrice * qty)}
            </span>
            {showActivePromo || showTeaserPromo ? (
              <p className="text-[11px] font-medium text-emerald-600">
                {showTeaserPromo
                  ? `Tiết kiệm dự kiến ~${formatPrice(teaserSavings * qty)}`
                  : `Tiết kiệm ${formatPrice(unitSavings * qty)}`}
              </p>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
