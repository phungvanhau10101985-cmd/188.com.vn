'use client';

import Image from 'next/image';

import { parseHeroObjectPosition } from '@/lib/ladipage-utils';

interface HeroDisplayImageProps {
  src?: string | null;
  objectPosition?: string | null;
  alt: string;
  aspectClassName?: string;
  objectFit?: 'cover' | 'contain';
  /** Ảnh hero chính hiển thị ngay khi vào trang (LCP) — tải eager. */
  priority?: boolean;
}

/** Ảnh hero read-only — áp dụng object-position đã lưu từ admin. */
export default function HeroDisplayImage({
  src,
  objectPosition,
  alt,
  aspectClassName = 'aspect-[4/3]',
  objectFit = 'cover',
  priority = false,
}: HeroDisplayImageProps) {
  const pos = parseHeroObjectPosition(objectPosition);
  const fitClass = objectFit === 'contain' ? 'object-contain' : 'object-cover';

  return (
    <div className={`relative overflow-hidden rounded-xl bg-gray-100 ${aspectClassName}`}>
      {src ? (
        <Image
          src={src}
          alt={alt}
          fill
          sizes="(max-width: 768px) 100vw, 50vw"
          className={fitClass}
          style={{ objectPosition: `${pos.x}% ${pos.y}%` }}
          priority={priority}
          fetchPriority={priority ? 'high' : undefined}
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center px-4 text-center text-sm text-gray-400">
          Chưa có ảnh hero
        </div>
      )}
    </div>
  );
}
