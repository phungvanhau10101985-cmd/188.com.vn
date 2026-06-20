'use client';

import { useCallback, useEffect, useState } from 'react';
import { RATE_LIMIT_EVENT, type RateLimitEventDetail } from '@/lib/rate-limit-notice';

export function RateLimitNotice() {
  const [untilMs, setUntilMs] = useState<number | null>(null);
  const [tick, setTick] = useState(0);

  const extendCooldown = useCallback((seconds: number) => {
    const nextUntil = Date.now() + Math.max(1, seconds) * 1000;
    setUntilMs((prev) => (prev != null && prev > nextUntil ? prev : nextUntil));
    setTick((t) => t + 1);
  }, []);

  useEffect(() => {
    const onRateLimit = (event: Event) => {
      const custom = event as CustomEvent<RateLimitEventDetail>;
      const seconds = custom.detail?.seconds;
      if (typeof seconds === 'number' && seconds > 0) {
        extendCooldown(seconds);
      }
    };
    window.addEventListener(RATE_LIMIT_EVENT, onRateLimit);
    return () => window.removeEventListener(RATE_LIMIT_EVENT, onRateLimit);
  }, [extendCooldown]);

  const remainingSec = untilMs ? Math.max(0, Math.ceil((untilMs - Date.now()) / 1000)) : 0;

  useEffect(() => {
    if (!untilMs || remainingSec <= 0) {
      if (untilMs != null && remainingSec <= 0) {
        setUntilMs(null);
      }
      return;
    }
    const id = window.setInterval(() => setTick((t) => t + 1), 1000);
    return () => window.clearInterval(id);
  }, [untilMs, remainingSec, tick]);

  if (!untilMs || remainingSec <= 0) return null;

  return (
    <div
      className="fixed inset-x-0 top-0 z-[250] border-b border-amber-300 bg-amber-50 px-4 py-3 text-amber-950 shadow-md"
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
    >
      <div className="mx-auto flex max-w-3xl items-start gap-3">
        <span className="text-2xl leading-none select-none animate-pulse" aria-hidden>
          ⏳
        </span>
        <div className="min-w-0 text-sm">
          <p className="font-semibold">Bạn đang thao tác quá nhanh</p>
          <p className="mt-0.5 text-amber-900">
            Vui lòng chờ{' '}
            <span className="inline-flex min-w-[2ch] font-bold tabular-nums text-amber-950">
              {remainingSec}s
            </span>{' '}
            rồi tiếp tục mua sắm hoặc chuyển trang.
          </p>
        </div>
      </div>
    </div>
  );
}
