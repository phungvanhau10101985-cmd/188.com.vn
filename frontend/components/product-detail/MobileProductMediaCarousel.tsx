'use client';

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type ReactNode,
} from 'react';

export type MobileProductMediaCarouselHandle = {
  scrollToIndex: (index: number, behavior?: ScrollBehavior) => void;
};

type MobileProductMediaCarouselProps = {
  selectedIndex: number;
  onSelectedIndexChange: (index: number) => void;
  slideCount: number;
  className?: string;
  children: ReactNode;
  /** Chỉ số hiện tại cho overlay (dots/counter) — cập nhật mượt trong carousel, không re-render parent. */
  renderOverlay?: (liveIndex: number) => ReactNode;
};

const SCROLL_END_FALLBACK_MS = 120;

const MobileProductMediaCarousel = forwardRef<
  MobileProductMediaCarouselHandle,
  MobileProductMediaCarouselProps
>(function MobileProductMediaCarousel(
  {
    selectedIndex,
    onSelectedIndexChange,
    slideCount,
    className = '',
    children,
    renderOverlay,
  },
  ref,
) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const selectedIndexRef = useRef(selectedIndex);
  const programmaticScrollRef = useRef(false);
  const userScrollingRef = useRef(false);
  const scrollEndTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const programmaticResetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const liveIndexRafRef = useRef<number | null>(null);
  const [liveIndex, setLiveIndex] = useState(selectedIndex);

  selectedIndexRef.current = selectedIndex;

  const readIndexFromScroll = useCallback(() => {
    const el = scrollerRef.current;
    if (!el || slideCount <= 0) return selectedIndexRef.current;
    const width = el.clientWidth;
    if (width <= 0) return selectedIndexRef.current;
    return Math.min(slideCount - 1, Math.max(0, Math.round(el.scrollLeft / width)));
  }, [slideCount]);

  const scrollToIndex = useCallback((index: number, behavior: ScrollBehavior = 'smooth') => {
    const el = scrollerRef.current;
    if (!el || slideCount <= 0) return;
    const clamped = Math.min(slideCount - 1, Math.max(0, index));
    const width = el.clientWidth;
    if (width <= 0) return;
    const targetLeft = clamped * width;
    if (Math.abs(el.scrollLeft - targetLeft) < 1) return;

    programmaticScrollRef.current = true;
    if (programmaticResetTimerRef.current) clearTimeout(programmaticResetTimerRef.current);
    setLiveIndex(clamped);
    el.scrollTo({ left: targetLeft, behavior });
    programmaticResetTimerRef.current = setTimeout(() => {
      programmaticScrollRef.current = false;
    }, behavior === 'smooth' ? 420 : 48);
  }, [slideCount]);

  useImperativeHandle(ref, () => ({ scrollToIndex }), [scrollToIndex]);

  const commitIndexFromScroll = useCallback(() => {
    userScrollingRef.current = false;
    if (programmaticScrollRef.current) return;
    const idx = readIndexFromScroll();
    setLiveIndex(idx);
    if (idx !== selectedIndexRef.current) onSelectedIndexChange(idx);
  }, [onSelectedIndexChange, readIndexFromScroll]);

  const scheduleScrollEndCommit = useCallback(() => {
    if (scrollEndTimerRef.current) clearTimeout(scrollEndTimerRef.current);
    scrollEndTimerRef.current = setTimeout(() => {
      scrollEndTimerRef.current = null;
      commitIndexFromScroll();
    }, SCROLL_END_FALLBACK_MS);
  }, [commitIndexFromScroll]);

  const updateLiveIndexDuringScroll = useCallback(() => {
    if (programmaticScrollRef.current) return;
    if (liveIndexRafRef.current !== null) return;
    liveIndexRafRef.current = requestAnimationFrame(() => {
      liveIndexRafRef.current = null;
      const idx = readIndexFromScroll();
      setLiveIndex((prev) => (prev === idx ? prev : idx));
    });
  }, [readIndexFromScroll]);

  const handleScroll = useCallback(() => {
    if (programmaticScrollRef.current) return;
    updateLiveIndexDuringScroll();
    scheduleScrollEndCommit();
  }, [scheduleScrollEndCommit, updateLiveIndexDuringScroll]);

  const handleTouchStart = useCallback(() => {
    userScrollingRef.current = true;
  }, []);

  useEffect(() => {
    setLiveIndex((prev) => (prev === selectedIndex ? prev : selectedIndex));
  }, [selectedIndex]);

  useEffect(() => {
    return () => {
      if (liveIndexRafRef.current !== null) cancelAnimationFrame(liveIndexRafRef.current);
      if (scrollEndTimerRef.current) clearTimeout(scrollEndTimerRef.current);
      if (programmaticResetTimerRef.current) clearTimeout(programmaticResetTimerRef.current);
    };
  }, []);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;

    scrollToIndex(selectedIndexRef.current, 'auto');

    const onScrollEnd = () => {
      if (scrollEndTimerRef.current) {
        clearTimeout(scrollEndTimerRef.current);
        scrollEndTimerRef.current = null;
      }
      commitIndexFromScroll();
    };

    el.addEventListener('scrollend', onScrollEnd);

    const ro = new ResizeObserver(() => {
      if (userScrollingRef.current) return;
      scrollToIndex(selectedIndexRef.current, 'auto');
    });
    ro.observe(el);

    return () => {
      el.removeEventListener('scrollend', onScrollEnd);
      ro.disconnect();
    };
  }, [commitIndexFromScroll, scrollToIndex]);

  if (slideCount <= 1) {
    return <div className={className}>{children}</div>;
  }

  return (
    <div className={`relative min-w-0 ${className}`}>
      <div
        ref={scrollerRef}
        className="product-gallery-media-carousel flex h-full min-w-0 w-full overflow-x-auto scrollbar-hide touch-pan-x"
        onScroll={handleScroll}
        onTouchStart={handleTouchStart}
        onPointerDown={(e) => {
          if (e.pointerType === 'touch') userScrollingRef.current = true;
        }}
        aria-label="Thư viện ảnh sản phẩm"
      >
        {children}
      </div>
      {renderOverlay?.(liveIndex)}
    </div>
  );
});

export default MobileProductMediaCarousel;

export function MobileProductMediaSlide({
  children,
  className = '',
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`product-gallery-media-slide min-w-full w-full flex-[0_0_100%] ${className}`}>
      {children}
    </div>
  );
}
