'use client';

import { useEffect, useState, type RefObject } from 'react';

type UseNearViewportOptions = {
  rootMargin?: string;
  threshold?: number;
  /** Bật false để tắt observer (vd. đã fetch xong). */
  enabled?: boolean;
};

/**
 * true khi element sắp/chạm viewport — dùng lazy-load block dưới fold (SP liên quan, sidebar).
 */
export function useNearViewport(
  ref: RefObject<Element | null>,
  options: UseNearViewportOptions = {},
): boolean {
  const { rootMargin = '240px', threshold = 0, enabled = true } = options;
  const [isNear, setIsNear] = useState(false);

  useEffect(() => {
    if (!enabled || isNear) return;
    const el = ref.current;
    if (!el) return;

    if (typeof IntersectionObserver === 'undefined') {
      setIsNear(true);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setIsNear(true);
          observer.disconnect();
        }
      },
      { rootMargin, threshold },
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [ref, rootMargin, threshold, enabled, isNear]);

  return isNear;
}
