'use client';

import { useMemo, useState, useEffect } from 'react';
import type { SiteSaleCalendarState } from '@/types/api';
import { siteSaleBannerMessage } from '@/lib/site-sale';
import SiteSaleLiveCountdown from '@/components/SiteSaleLiveCountdown';

type Props = {
  state: SiteSaleCalendarState | null;
  className?: string;
};

export default function SiteSaleBanner({ state, className = '' }: Props) {
  const storageKey = useMemo(
    () => `188_site_sale_banner_${state?.event_date ?? 'none'}_${state?.phase ?? 'off'}`,
    [state?.event_date, state?.phase],
  );
  const [closed, setClosed] = useState(false);

  useEffect(() => {
    try {
      if (sessionStorage.getItem(storageKey) === '1') setClosed(true);
    } catch {
      /* noop */
    }
  }, [storageKey]);

  const message = siteSaleBannerMessage(state);

  if (!message || closed) return null;

  const isTeaser = state?.phase === 'teaser';

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
        <p className="font-semibold">{state?.event_label ?? 'Chương trình sale'}</p>
        <p className="text-xs sm:text-sm opacity-90">{message}</p>
        {state?.countdown_to && state?.phase ? (
          <SiteSaleLiveCountdown
            countdownTo={state.countdown_to}
            phase={state.phase}
            eventLabel={state.event_label}
            size="sm"
            inline
            className="mt-1 block opacity-95"
          />
        ) : null}
      </div>
    </div>
  );
}
