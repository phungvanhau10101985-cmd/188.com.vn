'use client';

import { useMemo } from 'react';
import { useClientMounted } from '@/lib/use-client-mounted';
import { useCountdownNowMs } from '@/lib/use-countdown-now-ms';

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
  const clientMounted = useClientMounted();
  const hasCountdown = Boolean(countdownTo && phase);
  const nowMs = useCountdownNowMs(hasCountdown);
  const tickMs = clientMounted && hasCountdown ? nowMs : null;

  const countdownLive = useMemo(() => {
    if (tickMs == null || !countdownTo) return '';
    const target = new Date(countdownTo).getTime();
    if (!Number.isFinite(target)) return '';
    const diff = target - tickMs;
    if (diff <= 0) return '';
    const totalSec = Math.floor(diff / 1000);
    const parts = {
      days: Math.floor(totalSec / 86400),
      hours: Math.floor((totalSec % 86400) / 3600),
      minutes: Math.floor((totalSec % 3600) / 60),
      seconds: totalSec % 60,
    };
    return formatLiveHms(parts);
  }, [countdownTo, tickMs]);

  if (!clientMounted || !phase || !countdownLive) return null;

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
