'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

interface BirthdayPromoBannerProps {
  active: boolean;
  percent?: number;
  nextBirthdayLabel?: string | null;
  compact?: boolean;
  className?: string;
}

export default function BirthdayPromoBanner({
  active,
  percent = 10,
  nextBirthdayLabel,
  compact = false,
  className = '',
}: BirthdayPromoBannerProps) {
  const storageKey = useMemo(
    () => `188_birthday_promo_banner_closed_${nextBirthdayLabel || 'unknown'}_${percent}`,
    [nextBirthdayLabel, percent]
  );
  const [closed, setClosed] = useState(false);

  useEffect(() => {
    if (!active) return;
    try {
      setClosed(localStorage.getItem(storageKey) === '1');
    } catch {
      setClosed(false);
    }
  }, [active, storageKey]);

  const closeBanner = () => {
    setClosed(true);
    try {
      localStorage.setItem(storageKey, '1');
    } catch {
      /* noop */
    }
  };

  if (!active || closed) return null;

  return (
    <div
      className={`relative rounded-xl border border-pink-200 bg-gradient-to-r from-pink-50 via-orange-50 to-amber-50 p-3 pr-11 text-sm text-gray-800 shadow-sm sm:rounded-2xl sm:p-4 sm:pr-12 ${className}`}
      role="status"
      aria-live="polite"
    >
      <button
        type="button"
        onClick={closeBanner}
        className="absolute right-2 top-2 min-h-[44px] min-w-[44px] rounded-full p-2 text-gray-500 hover:bg-white/70 hover:text-gray-800 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2 sm:right-3 sm:top-3 sm:min-h-0 sm:min-w-0 sm:p-1.5"
        aria-label="Đóng banner ưu đãi sinh nhật"
      >
        <svg className="mx-auto h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
      <div className="flex items-start gap-2 sm:gap-3">
        <div
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-pink-600 text-xl text-white shadow-sm sm:h-12 sm:w-12 sm:text-2xl"
          aria-hidden
        >
          🎂
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-col gap-1.5 sm:flex-row sm:flex-wrap sm:items-center sm:gap-2">
            <p className="font-bold text-gray-900">
              Chúc mừng sinh nhật bạn!
            </p>
            <span className="w-fit shrink-0 rounded-full bg-pink-600 px-2.5 py-1 text-xs font-bold text-white">
              Đã kích hoạt -{percent}%
            </span>
          </div>
          <p className="mt-1 text-xs leading-snug text-gray-600 sm:mt-1 sm:leading-5 sm:text-sm">
            Giá sinh nhật đã được trừ trực tiếp trên website và tự áp dụng khi thanh toán, không cần mã.
            {nextBirthdayLabel ? ` Sinh nhật sắp tới: ${nextBirthdayLabel}.` : ''}
          </p>
          {!compact && (
            <Link
              href="/cart"
              className="mt-2 flex w-full items-center justify-center rounded-full bg-[#ea580c] px-4 py-2.5 text-xs font-semibold text-white hover:bg-[#c2410c] sm:mt-3 sm:inline-flex sm:w-auto sm:py-2"
            >
              Xem giỏ hàng ưu đãi
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
