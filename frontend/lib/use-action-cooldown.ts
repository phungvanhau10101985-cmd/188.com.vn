'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

/** Trích số giây chờ từ thông báo API (vd. "Thử lại sau 12 giây."). */
export function parseRetryAfterSeconds(message: string): number | null {
  const m = message.match(/(?:thử lại sau|retry(?:\s+\w+)*\s+after|chờ)\s*(\d+)\s*giây/i);
  if (!m) return null;
  const n = Number.parseInt(m[1], 10);
  return Number.isFinite(n) && n > 0 ? n : null;
}

export type ActionCooldownNotice = {
  key: string;
  until: number;
  label?: string;
};

export function useActionCooldown() {
  const untilRef = useRef<Record<string, number>>({});
  const [notice, setNotice] = useState<ActionCooldownNotice | null>(null);
  const [tick, setTick] = useState(0);

  const hasAnyActiveCooldown = Object.values(untilRef.current).some((until) => until > Date.now());

  const remainingSec = notice
    ? Math.max(0, Math.ceil((notice.until - Date.now()) / 1000))
    : 0;

  useEffect(() => {
    const active =
      (notice && remainingSec > 0) ||
      Object.values(untilRef.current).some((until) => until > Date.now());
    if (!active) return;
    const id = window.setInterval(() => setTick((t) => t + 1), 1000);
    return () => window.clearInterval(id);
  }, [notice, remainingSec, tick, hasAnyActiveCooldown]);

  useEffect(() => {
    if (notice && remainingSec <= 0) {
      setNotice(null);
    }
  }, [notice, remainingSec]);

  const getRemainingSec = useCallback((key: string): number => {
    void tick;
    const until = untilRef.current[key] ?? 0;
    return Math.max(0, Math.ceil((until - Date.now()) / 1000));
  }, [tick]);

  const isBlocked = useCallback(
    (key: string) => getRemainingSec(key) > 0,
    [getRemainingSec],
  );

  const imposeCooldown = useCallback((key: string, seconds: number) => {
    const sec = Math.max(1, Math.floor(seconds));
    untilRef.current[key] = Date.now() + sec * 1000;
    setTick((t) => t + 1);
  }, []);

  const showTooFast = useCallback((key: string, label?: string) => {
    const until = untilRef.current[key] ?? 0;
    if (until <= Date.now()) return;
    setNotice({ key, until, label });
  }, []);

  const runGuarded = useCallback(
    async (key: string, cooldownSec: number, fn: () => void | Promise<void>, label?: string) => {
      void tick;
      const rem = getRemainingSec(key);
      if (rem > 0) {
        showTooFast(key, label);
        return false;
      }
      imposeCooldown(key, cooldownSec);
      await fn();
      return true;
    },
    [getRemainingSec, imposeCooldown, showTooFast, tick],
  );

  const applyErrorCooldown = useCallback(
    (key: string, message: string, fallbackSec = 5, label?: string) => {
      const parsed = parseRetryAfterSeconds(message);
      if (parsed != null) {
        imposeCooldown(key, parsed);
        showTooFast(key, label);
        return parsed;
      }
      return null;
    },
    [imposeCooldown, showTooFast],
  );

  return {
    notice,
    remainingSec,
    isBlocked,
    getRemainingSec,
    imposeCooldown,
    showTooFast,
    runGuarded,
    applyErrorCooldown,
    dismissNotice: () => setNotice(null),
  };
}
