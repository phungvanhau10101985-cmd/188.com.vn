'use client';

import { useState } from 'react';
import Image from 'next/image';
import MobileProductMediaCarousel, {
  MobileProductMediaSlide,
} from '@/components/product-detail/MobileProductMediaCarousel';
import { parseHeroObjectPosition } from '@/lib/ladipage-utils';

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
  const pos = parseHeroObjectPosition(objectPosition);
  const slides = images.filter((u) => u?.trim());

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
        />
      </div>
    );
  }

  return (
    <div className={`relative overflow-hidden rounded-xl bg-gray-100 ${aspectClassName}`}>
      <MobileProductMediaCarousel
        selectedIndex={index}
        onSelectedIndexChange={setIndex}
        slideCount={slides.length}
        className="absolute inset-0 h-full w-full touch-pan-x"
      >
        {slides.map((src, i) => (
          <MobileProductMediaSlide key={`${src}-${i}`} className="relative h-full min-h-full">
            <Image
              src={src}
              alt={`${alt} — ${i + 1}/${slides.length}`}
              fill
              sizes="(max-width: 768px) 100vw, 50vw"
              className="object-cover"
              style={{ objectPosition: i === 0 ? `${pos.x}% ${pos.y}%` : '50% 50%' }}
              draggable={false}
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
