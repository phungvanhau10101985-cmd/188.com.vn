'use client';

import { useEffect, useMemo, useState } from 'react';
import type { SiteSaleProductPricing } from '@/types/api';

type Props = {
  siteSale?: SiteSaleProductPricing | null;
  className?: string;
};

function formatLiveCountdown(parts: {
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
}): string {
  const hms = `${String(parts.hours).padStart(2, '0')}:${String(parts.minutes).padStart(2, '0')}:${String(parts.seconds).padStart(2, '0')}`;
  if (parts.days > 0) return `${parts.days} ngày ${hms}`;
  return hms;
}

function saleEventLabel(siteSale: SiteSaleProductPricing): string {
  const raw = (siteSale.event_label ?? '').trim();
  if (raw) return raw;
  if (siteSale.event_date) {
    const [y, m, d] = siteSale.event_date.split('-').map(Number);
    if (m && d) return `Sale ${d}/${m}`;
  }
  return 'Sale';
}

/** Thanh đếm ngược — đặt dưới ảnh SP (teaser: bắt đầu sau; active: còn). */
export default function SiteSaleCountdownChip({ siteSale, className = '' }: Props) {
  /** null trên SSR + lần hydrate đầu — tránh lệch Date.now() server/client. */
  const [nowMs, setNowMs] = useState<number | null>(null);

  useEffect(() => {
    if (!siteSale?.countdown_to || !siteSale?.phase) return;
    const tick = () => setNowMs(Date.now());
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [siteSale?.countdown_to, siteSale?.phase]);

  const phase = siteSale?.phase;
  const targetIso = siteSale?.countdown_to;

  const parts = useMemo(() => {
    if (nowMs == null || !targetIso) return null;
    const target = new Date(targetIso).getTime();
    if (!Number.isFinite(target)) return null;
    const diff = target - nowMs;
    if (diff <= 0) return null;
    const totalSec = Math.floor(diff / 1000);
    return {
      days: Math.floor(totalSec / 86400),
      hours: Math.floor((totalSec % 86400) / 3600),
      minutes: Math.floor((totalSec % 3600) / 60),
      seconds: totalSec % 60,
    };
  }, [targetIso, nowMs]);

  if (!siteSale || !phase || nowMs == null || !parts) return null;

  const countdownLive = formatLiveCountdown(parts);
  const isTeaser = phase === 'teaser';
  const label = saleEventLabel(siteSale);
  const prefix = isTeaser ? `${label} bắt đầu sau` : `${label} — còn`;

  return (
    <div
      className={`pointer-events-none absolute inset-x-0 bottom-0 z-[3] ${className}`}
      role="timer"
      aria-live="polite"
      aria-atomic="true"
    >
      <div
        className={`flex w-full items-center justify-center gap-1.5 px-2 py-1.5 text-[10px] font-semibold leading-tight text-white sm:text-[11px] ${
          isTeaser ? 'bg-amber-700/95' : 'bg-red-700/95'
        }`}
      >
        <span aria-hidden>⏱</span>
        <span className="text-center">
          {prefix}{' '}
          <span
            key={`${parts.seconds}-${parts.minutes}-${parts.hours}-${parts.days}`}
            className="inline-block font-bold tabular-nums tracking-tight animate-[countdown-tick_0.3s_ease-out]"
          >
            {countdownLive}
          </span>
        </span>
      </div>
    </div>
  );
}
