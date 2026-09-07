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
}

export default function BirthdaySavingsCard({
  active,
  percent,
  savings,
  nextBirthdayLabel,
  compact = false,
  className = '',
}: BirthdaySavingsCardProps) {
  const { state: siteSaleState } = useSiteSale();
  const stackedHint =
    siteSaleState?.enabled && (siteSaleState.phase === 'active' || siteSaleState.phase === 'teaser')
      ? `${FLASH_SALE_PROGRAM_NAME} / ${calendarSaleProgramLabel(null, siteSaleState)}`
      : FLASH_SALE_PROGRAM_NAME;

  if (!active || percent <= 0 || savings <= 0) return null;

  return (
    <div
      className={`rounded-2xl border border-pink-200 bg-gradient-to-r from-pink-50 via-rose-50 to-orange-50 p-3 shadow-sm ${className}`}
      role="note"
    >
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
