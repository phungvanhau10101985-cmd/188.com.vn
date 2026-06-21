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
  const selectedIndexRef = useRef(selectedIndex);
  const programmaticScrollRef = useRef(false);
  const rafRef = useRef<number | null>(null);
  const programmaticResetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  selectedIndexRef.current = selectedIndex;

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
    el.scrollTo({ left: targetLeft, behavior });
    programmaticResetTimerRef.current = setTimeout(() => {
      programmaticScrollRef.current = false;
    }, behavior === 'smooth' ? 420 : 48);
  }, [slideCount]);

  useImperativeHandle(ref, () => ({ scrollToIndex }), [scrollToIndex]);

  const syncIndexFromScroll = useCallback(() => {
    const el = scrollerRef.current;
    if (!el || slideCount <= 0) return;
    const width = el.clientWidth;
    if (width <= 0) return;
    const idx = Math.min(slideCount - 1, Math.max(0, Math.round(el.scrollLeft / width)));
    if (idx !== selectedIndexRef.current) onSelectedIndexChange(idx);
  }, [onSelectedIndexChange, slideCount]);

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
    scrollToIndex(selectedIndexRef.current, 'auto');
    const ro = new ResizeObserver(() => {
      scrollToIndex(selectedIndexRef.current, 'auto');
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [scrollToIndex]);

  if (slideCount <= 1) {
    return <div className={className}>{children}</div>;
  }

  return (
    <div
      ref={scrollerRef}
      className={`product-gallery-media-carousel flex min-w-0 overflow-x-auto snap-x snap-mandatory scrollbar-hide ${className}`}
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
    <div
      className={`min-w-full w-full flex-[0_0_100%] snap-center snap-always ${className}`}
      style={{ scrollSnapStop: 'always' }}
    >
      {children}
    </div>
  );
}
