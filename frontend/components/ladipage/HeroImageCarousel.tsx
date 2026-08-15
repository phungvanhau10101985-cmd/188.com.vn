'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Image from 'next/image';
import MobileProductMediaCarousel, {
  MobileProductMediaSlide,
  type MobileProductMediaCarouselHandle,
} from '@/components/product-detail/MobileProductMediaCarousel';
import { parseHeroObjectPosition } from '@/lib/ladipage-utils';

const HERO_AUTOPLAY_MS = 3500;

function useDesktopFinePointer(): boolean {
  const [isDesktop, setIsDesktop] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mq = window.matchMedia('(min-width: 768px) and (pointer: fine)');
    const update = () => setIsDesktop(mq.matches);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);

  return isDesktop;
}

interface HeroImageCarouselProps {
  images: string[];
  alt: string;
  objectPosition?: string | null;
  aspectClassName?: string;
}

/** Hero vuốt ngang — gallery SP + ảnh hero đã chọn. */
export default function HeroImageCarousel({
  images,
  alt,
  objectPosition,
  aspectClassName = 'aspect-[4/3]',
}: HeroImageCarouselProps) {
  const [index, setIndex] = useState(0);
  const [autoplayActive, setAutoplayActive] = useState(false);
  const [hoverPaused, setHoverPaused] = useState(false);
  const carouselRef = useRef<MobileProductMediaCarouselHandle>(null);
  const indexRef = useRef(0);
  const isDesktop = useDesktopFinePointer();
  const pos = parseHeroObjectPosition(objectPosition);
  const slides = images.filter((u) => u?.trim());

  indexRef.current = index;

  const goToSlide = useCallback((next: number, behavior: ScrollBehavior = 'smooth') => {
    setIndex(next);
    carouselRef.current?.scrollToIndex(next, behavior);
  }, []);

  const advanceSlide = useCallback(() => {
    if (slides.length <= 1) return;
    goToSlide((indexRef.current + 1) % slides.length);
  }, [goToSlide, slides.length]);

  useEffect(() => {
    if (!autoplayActive || hoverPaused || slides.length <= 1 || !isDesktop) return;
    const timer = window.setInterval(advanceSlide, HERO_AUTOPLAY_MS);
    return () => window.clearInterval(timer);
  }, [advanceSlide, autoplayActive, hoverPaused, isDesktop, slides.length]);

  const handleDesktopClick = useCallback(() => {
    if (!isDesktop || slides.length <= 1) return;
    setAutoplayActive(true);
    advanceSlide();
  }, [advanceSlide, isDesktop, slides.length]);

  if (slides.length === 0) {
    return (
      <div className={`relative overflow-hidden rounded-xl bg-gray-100 ${aspectClassName}`}>
        <div className="flex h-full w-full items-center justify-center px-4 text-center text-sm text-gray-400">
          Chưa có ảnh hero
        </div>
      </div>
    );
  }

  if (slides.length === 1) {
    return (
      <div className={`relative overflow-hidden rounded-xl bg-gray-100 ${aspectClassName}`}>
        <Image
          src={slides[0]}
          alt={alt}
          fill
          sizes="(max-width: 768px) 100vw, 50vw"
          className="object-cover"
          style={{ objectPosition: `${pos.x}% ${pos.y}%` }}
          priority
          fetchPriority="high"
        />
      </div>
    );
  }

  return (
    <div
      className={`relative overflow-hidden rounded-xl bg-gray-100 ${aspectClassName} ${
        isDesktop ? 'md:cursor-pointer' : ''
      }`}
      onClick={isDesktop ? handleDesktopClick : undefined}
      onMouseEnter={isDesktop ? () => setHoverPaused(true) : undefined}
      onMouseLeave={isDesktop ? () => setHoverPaused(false) : undefined}
      role={isDesktop ? 'group' : undefined}
      aria-label={isDesktop ? 'Gallery ảnh hero — bấm để xem ảnh tiếp theo' : undefined}
    >
      <MobileProductMediaCarousel
        ref={carouselRef}
        selectedIndex={index}
        onSelectedIndexChange={setIndex}
        slideCount={slides.length}
        fillHeight
        className="absolute inset-0 h-full w-full touch-pan-x"
      >
        {slides.map((src, i) => (
          <MobileProductMediaSlide key={`${src}-${i}`} className="relative h-full min-h-0">
            <Image
              src={src}
              alt={`${alt} — ${i + 1}/${slides.length}`}
              fill
              sizes="(max-width: 768px) 100vw, 50vw"
              className="object-cover"
              style={{ objectPosition: i === 0 ? `${pos.x}% ${pos.y}%` : '50% 50%' }}
              draggable={false}
              priority={i === 0}
              fetchPriority={i === 0 ? 'high' : undefined}
            />
          </MobileProductMediaSlide>
        ))}
      </MobileProductMediaCarousel>

      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 flex flex-col items-center gap-2 bg-gradient-to-t from-black/35 to-transparent px-3 pb-3 pt-10"
        aria-hidden
      >
        <div className="flex items-center gap-1.5">
          {slides.map((_, i) => (
            <span
              key={i}
              className={`block h-1.5 rounded-full transition-all ${
                i === index ? 'w-4 bg-white' : 'w-1.5 bg-white/55'
              }`}
            />
          ))}
        </div>
      </div>

      <div className="pointer-events-none absolute right-3 top-3 rounded-full bg-black/45 px-2.5 py-0.5 text-[11px] font-medium tabular-nums text-white">
        {index + 1}/{slides.length}
      </div>
    </div>
  );
}
