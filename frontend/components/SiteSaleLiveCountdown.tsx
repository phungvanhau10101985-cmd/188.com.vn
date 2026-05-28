'use client';

import { useEffect, useMemo, useState } from 'react';
import { formatCountdownParts } from '@/lib/site-sale';

type Props = {
  countdownTo?: string | null;
  phase?: 'teaser' | 'active' | null;
  eventLabel?: string | null;
  size?: 'sm' | 'md';
  inline?: boolean;
  className?: string;
};

function formatLiveHms(parts: {
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
}): string {
  const hms = `${String(parts.hours).padStart(2, '0')}:${String(parts.minutes).padStart(2, '0')}:${String(parts.seconds).padStart(2, '0')}`;
  if (parts.days > 0) return `${parts.days} ngày ${hms}`;
  return hms;
}

/** Countdown live giờ:phút:giây — teaser: «Sale X bắt đầu sau»; active: «Sale X — còn». */
export default function SiteSaleLiveCountdown({
  countdownTo,
  phase = null,
  eventLabel = null,
  size = 'md',
  inline = false,
  className = '',
}: Props) {
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!countdownTo || !phase) return;
    setNowMs(Date.now());
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [countdownTo, phase]);

  const countdownLive = useMemo(() => {
    if (!countdownTo) return '';
    const parts = formatCountdownParts(countdownTo);
    if (!parts || parts.expired) return '';
    return formatLiveHms(parts);
  }, [countdownTo, nowMs]);

  if (!phase || !countdownLive) return null;

  const label = eventLabel?.trim() || 'Sale';
  const prefix = phase === 'teaser' ? `${label} bắt đầu sau` : `${label} — còn`;
  const sizeClass =
    size === 'sm'
      ? 'text-[10px] leading-tight px-2 py-1 sm:text-[11px]'
      : 'text-xs leading-snug px-3 py-2 sm:text-sm';
  const toneClass =
    phase === 'teaser'
      ? 'border-amber-200 bg-amber-50 text-amber-900'
      : 'border-red-200 bg-red-50 text-red-900';

  if (inline) {
    return (
      <span
        className={`font-semibold tabular-nums ${className}`}
        role="timer"
        aria-live="polite"
        aria-atomic="true"
      >
        {prefix}{' '}
        <span className="font-bold tracking-tight">{countdownLive}</span>
      </span>
    );
  }

  return (
    <div
      className={`flex items-center gap-1.5 rounded-lg border font-semibold ${sizeClass} ${toneClass} ${className}`}
      role="timer"
      aria-live="polite"
      aria-atomic="true"
    >
      <span aria-hidden>⏱</span>
      <span>
        {prefix}{' '}
        <span className="font-bold tabular-nums tracking-tight">{countdownLive}</span>
      </span>
    </div>
  );
}
