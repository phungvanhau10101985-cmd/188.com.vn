'use client';

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
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
};

const MobileProductMediaCarousel = forwardRef<
  MobileProductMediaCarouselHandle,
  MobileProductMediaCarouselProps
>(function MobileProductMediaCarousel(
  { selectedIndex, onSelectedIndexChange, slideCount, className = '', children },
  ref,
) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const programmaticScrollRef = useRef(false);
  const rafRef = useRef<number | null>(null);
  const programmaticResetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scrollToIndex = useCallback((index: number, behavior: ScrollBehavior = 'smooth') => {
    const el = scrollerRef.current;
    if (!el || slideCount <= 0) return;
    const clamped = Math.min(slideCount - 1, Math.max(0, index));
    const width = el.clientWidth;
    if (width <= 0) return;
    programmaticScrollRef.current = true;
    if (programmaticResetTimerRef.current) clearTimeout(programmaticResetTimerRef.current);
    el.scrollTo({ left: clamped * width, behavior });
    programmaticResetTimerRef.current = setTimeout(() => {
      programmaticScrollRef.current = false;
    }, behavior === 'smooth' ? 420 : 0);
  }, [slideCount]);

  useImperativeHandle(ref, () => ({ scrollToIndex }), [scrollToIndex]);

  const syncIndexFromScroll = useCallback(() => {
    const el = scrollerRef.current;
    if (!el || slideCount <= 0) return;
    const width = el.clientWidth;
    if (width <= 0) return;
    const idx = Math.min(slideCount - 1, Math.max(0, Math.round(el.scrollLeft / width)));
    if (idx !== selectedIndex) onSelectedIndexChange(idx);
  }, [onSelectedIndexChange, selectedIndex, slideCount]);

  const handleScroll = useCallback(() => {
    if (programmaticScrollRef.current) return;
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      syncIndexFromScroll();
    });
  }, [syncIndexFromScroll]);

  useEffect(() => {
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      if (programmaticResetTimerRef.current) clearTimeout(programmaticResetTimerRef.current);
    };
  }, []);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      scrollToIndex(selectedIndex, 'auto');
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [scrollToIndex, selectedIndex]);

  if (slideCount <= 1) {
    return <div className={className}>{children}</div>;
  }

  return (
    <div
      ref={scrollerRef}
      className={`flex overflow-x-auto snap-x snap-mandatory scrollbar-hide touch-pan-y ${className}`}
      style={{ WebkitOverflowScrolling: 'touch' }}
      onScroll={handleScroll}
      aria-label="Thư viện ảnh sản phẩm"
    >
      {children}
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
    <div className={`flex-shrink-0 w-full snap-center snap-always ${className}`}>
      {children}
    </div>
  );
}
