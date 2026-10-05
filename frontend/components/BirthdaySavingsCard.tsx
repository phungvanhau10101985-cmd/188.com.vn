'use client';

import { formatPrice } from '@/lib/utils';
import { BIRTHDAY_PROGRAM_NAME } from '@/lib/birthday-discount';
import { calendarSaleProgramLabel, FLASH_SALE_PROGRAM_NAME } from '@/lib/site-sale';
import { useSiteSale } from '@/lib/use-site-sale';

interface BirthdaySavingsCardProps {
  active: boolean;
  percent: number;
  savings: number;
  nextBirthdayLabel?: string | null;
  compact?: boolean;
  className?: string;
  /** Đóng thẻ giải thích — giá đã trừ CMSN vẫn giữ nguyên. */
  onDismiss?: () => void;
}

export default function BirthdaySavingsCard({
  active,
  percent,
  savings,
  nextBirthdayLabel,
  compact = false,
  className = '',
  onDismiss,
}: BirthdaySavingsCardProps) {
  const { state: siteSaleState } = useSiteSale();
  const stackedHint =
    siteSaleState?.enabled && (siteSaleState.phase === 'active' || siteSaleState.phase === 'teaser')
      ? `${FLASH_SALE_PROGRAM_NAME} / ${calendarSaleProgramLabel(null, siteSaleState)}`
      : FLASH_SALE_PROGRAM_NAME;

  if (!active || percent <= 0 || savings <= 0) return null;

  return (
    <div
      className={`relative rounded-2xl border border-pink-200 bg-gradient-to-r from-pink-50 via-rose-50 to-orange-50 py-3 pl-3 shadow-sm ${onDismiss ? 'pr-10' : 'pr-3'} ${className}`}
      role="note"
    >
      {onDismiss ? (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onDismiss();
          }}
          className="absolute right-1.5 top-1.5 flex h-7 w-7 items-center justify-center rounded-md bg-white/80 text-gray-600 shadow-sm hover:bg-white hover:text-gray-900 focus:outline-none focus:ring-2 focus:ring-orange-500"
          aria-label={`Đóng thông tin ${BIRTHDAY_PROGRAM_NAME}`}
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      ) : null}
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-pink-600 text-lg text-white shadow-sm" aria-hidden>
          🎁
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-pink-600 px-2.5 py-1 text-xs font-bold text-white">
              {BIRTHDAY_PROGRAM_NAME} -{percent}%
            </span>
            <span className="text-sm font-bold text-pink-700">
              {BIRTHDAY_PROGRAM_NAME}: tiết kiệm {formatPrice(savings)}
            </span>
          </div>
          <p className="mt-1 text-xs leading-5 text-gray-700 sm:text-sm">
            {BIRTHDAY_PROGRAM_NAME} đã được trừ vào giá hiển thị (tối đa 15% giá gốc khi cộng {stackedHint}) và tự áp dụng khi thanh toán.
            {!compact && nextBirthdayLabel ? ` Sinh nhật sắp tới: ${nextBirthdayLabel}.` : ''}
          </p>
        </div>
      </div>
    </div>
  );
}
