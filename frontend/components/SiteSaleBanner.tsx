'use client';

import { useMemo, useState, useEffect } from 'react';
import type { SiteSaleCalendarState } from '@/types/api';
import { siteSaleBannerMessage, siteSaleProgramLabel } from '@/lib/site-sale';
import SiteSaleLiveCountdown from '@/components/SiteSaleLiveCountdown';

type Props = {
  state: SiteSaleCalendarState | null;
  loading?: boolean;
  /** Bản SSR — hiện ngay, không chờ client fetch (tránh đẩy layout). */
  initialState?: SiteSaleCalendarState | null;
  className?: string;
};

export default function SiteSaleBanner({
  state,
  loading = false,
  initialState = null,
  className = '',
}: Props) {
  const visibleState = loading ? initialState : state;
  const storageKey = useMemo(
    () =>
      `188_site_sale_banner_${visibleState?.event_date ?? 'none'}_${visibleState?.phase ?? 'off'}`,
    [visibleState?.event_date, visibleState?.phase],
  );
  const [closed, setClosed] = useState(false);

  useEffect(() => {
    try {
      if (sessionStorage.getItem(storageKey) === '1') setClosed(true);
    } catch {
      /* noop */
    }
  }, [storageKey]);

  const message = siteSaleBannerMessage(visibleState);

  if (!message || closed) return null;

  const isTeaser = visibleState?.phase === 'teaser';

  return (
    <div
      className={`relative border-b px-3 py-2 text-sm sm:px-4 ${
        isTeaser
          ? 'border-amber-200 bg-gradient-to-r from-amber-50 to-orange-50 text-amber-950'
          : 'border-orange-300 bg-gradient-to-r from-orange-100 to-red-50 text-orange-950'
      } ${className}`}
      role="status"
      aria-live="polite"
    >
      <button
        type="button"
        onClick={() => {
          setClosed(true);
          try {
            sessionStorage.setItem(storageKey, '1');
          } catch {
            /* noop */
          }
        }}
        className="absolute right-2 top-2 rounded p-1 text-current/70 hover:bg-white/60"
        aria-label="Đóng banner sale"
      >
        ×
      </button>
      <div className="pr-8">
        <p className="font-semibold">{siteSaleProgramLabel(null, visibleState)}</p>
        <p className="text-xs sm:text-sm opacity-90" suppressHydrationWarning>
          {message}
        </p>
        {visibleState?.countdown_to && visibleState?.phase ? (
          <div className="mt-1 min-h-[1.25rem]">
            <SiteSaleLiveCountdown
              countdownTo={visibleState.countdown_to}
              phase={visibleState.phase}
              eventLabel={siteSaleProgramLabel(null, visibleState)}
              size="sm"
              inline
              className="block opacity-95"
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
