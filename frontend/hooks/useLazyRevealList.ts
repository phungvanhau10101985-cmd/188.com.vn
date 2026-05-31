import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

export type UseLazyRevealListOptions = {
  initial?: number;
  step?: number;
  /** Khoảng đệm dưới viewport trước khi kích hoạt tải thêm */
  rootMargin?: string;
};

/**
 * Hiển thị dần phần tử khi cuộn (giả lập lazy load) — dùng khi API trả full danh sách một lần.
 */
export function useLazyRevealList<T>(
  items: T[],
  { initial = 8, step = 8, rootMargin = '280px' }: UseLazyRevealListOptions = {}
) {
  const [visibleCount, setVisibleCount] = useState(0);

  useEffect(() => {
    if (items.length === 0) {
      setVisibleCount(0);
      return;
    }
    setVisibleCount(Math.min(initial, items.length));
  }, [items, initial]);

  const revealed = useMemo(() => items.slice(0, visibleCount), [items, visibleCount]);
  const hasMore = visibleCount < items.length;

  const loadMore = useCallback(() => {
    setVisibleCount((c) => Math.min(c + step, items.length));
  }, [items.length, step]);

  const sentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!hasMore) return;
    const el = sentinelRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) loadMore();
      },
      { root: null, rootMargin, threshold: 0 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [hasMore, loadMore, rootMargin, visibleCount, items.length]);

  return { revealed, hasMore, sentinelRef, total: items.length };
}
