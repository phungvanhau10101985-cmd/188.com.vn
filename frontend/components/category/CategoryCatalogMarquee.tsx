'use client';

import { useMemo, useState } from 'react';
import LoadingLink from '@/components/ui/LoadingLink';
import { useRouter } from 'next/navigation';
import { LISTING_CARD_IMAGE } from '@/lib/image-utils';
import CdnFillImage from '@/components/CdnFillImage';
import { categorySegmentForUrl } from '@/lib/category-url';
import type { HeroCategoryTile } from '@/types/api';

export function categoryTileHref(tile: HeroCategoryTile): string {
  const s1 = categorySegmentForUrl(tile.category);
  if (!s1) return '/';
  const s2 = categorySegmentForUrl(tile.subcategory || tile.name);
  if (tile.level === 2) return `/danh-muc/${s1}/${s2}`;
  const s3 = categorySegmentForUrl(tile.sub_subcategory || tile.name);
  return `/danh-muc/${s1}/${s2}/${s3}`;
}

export function tileTitle(tile: HeroCategoryTile): string {
  const raw = (tile.short_name || tile.name || '').trim();
  return raw.replace(/\s+(Nam|Nữ)$/i, '').trim();
}

export function formatItemCount(count: number): string {
  const n = Math.max(0, Math.floor(count));
  if (n <= 0) return '';
  return `${n.toLocaleString('vi-VN')} mặt`;
}

function desktopGridClass(desktopCols: number): string {
  if (desktopCols >= 5) return 'grid grid-cols-2 md:grid-cols-5';
  return 'grid grid-cols-2 md:grid-cols-4';
}

function lastColBorderClass(desktopCols: number): string {
  if (desktopCols >= 5) {
    return 'border-r border-white/10 [&:nth-child(2n)]:border-r-0 md:[&:nth-child(2n)]:border-r md:[&:nth-child(5n)]:border-r-0';
  }
  return 'border-r border-white/10 [&:nth-child(2n)]:border-r-0 md:[&:nth-child(2n)]:border-r md:[&:nth-child(4n)]:border-r-0';
}

function tileHeightFromRowClass(rowClassName: string): string {
  const parts = rowClassName.split(/\s+/).filter((c) => /^(h-|sm:h-|md:h-|lg:h-)/.test(c));
  return parts.join(' ') || 'h-[100px] sm:h-[112px] md:h-[148px]';
}

function CategoryGridTile({
  tile,
  priorityImage = false,
  heightClass,
  borderClass,
}: {
  tile: HeroCategoryTile;
  priorityImage?: boolean;
  heightClass: string;
  borderClass: string;
}) {
  const router = useRouter();
  const href = categoryTileHref(tile);
  const title = tileTitle(tile);
  const itemCountLabel = formatItemCount(tile.product_count);
  const img = (tile.image_url || '').trim();

  return (
    <LoadingLink
      href={href}
      title={itemCountLabel ? `${tile.name} · ${itemCountLabel}` : tile.name}
      onMouseEnter={() => router.prefetch(href)}
      onFocus={() => router.prefetch(href)}
      className={`hero-category-tile btn-interactive group relative flex min-w-0 flex-col overflow-hidden focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-white active:brightness-105 ${heightClass} ${borderClass}`}
    >
      <div className="relative flex-1 min-h-0 overflow-hidden bg-gradient-to-br from-orange-600/95 via-orange-500/90 to-amber-700/95">
        {img ? (
          <CdnFillImage
            rawSrc={img}
            widthHint={LISTING_CARD_IMAGE.width}
            heightHint={LISTING_CARD_IMAGE.height}
            quality={LISTING_CARD_IMAGE.quality}
            alt={title}
            sizes="(max-width: 767px) 50vw, 20vw"
            priority={priorityImage}
            fetchPriority={priorityImage ? 'high' : undefined}
            className="object-contain object-center p-1 transition-transform duration-500 ease-out group-hover:scale-105"
          />
        ) : (
          <div className="absolute inset-0 bg-gradient-to-br from-orange-500 to-amber-700" aria-hidden />
        )}
        {itemCountLabel ? (
          <span className="absolute top-1 right-1 z-10 max-w-[85%] truncate rounded bg-black/45 px-1 py-0.5 text-[9px] font-medium text-white/95 tabular-nums backdrop-blur-[2px] md:text-[10px]">
            {itemCountLabel}
          </span>
        ) : null}
      </div>
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 z-[1] h-9 bg-gradient-to-t from-black/65 to-transparent md:h-10"
        aria-hidden
      />
      <div className="absolute inset-x-0 bottom-0 z-10 px-1.5 py-1 md:px-2 md:py-1">
        <p className="text-[10px] font-bold leading-tight text-white line-clamp-1 drop-shadow-[0_1px_3px_rgba(0,0,0,0.85)] md:text-[11px]">
          {title}
        </p>
      </div>
    </LoadingLink>
  );
}

export interface CategoryCatalogMarqueeProps {
  tiles: HeroCategoryTile[];
  maxTiles?: number;
  ariaLabel?: string;
  rowClassName?: string;
  viewportClassName?: string;
  /** Trang /danh-muc: vuốt tay, không auto trượt */
  manualScroll?: boolean;
  /** Số cột desktop (mặc định 4; trang /danh-muc dùng 5) */
  desktopCols?: number;
}

function TileGrid({
  tiles,
  desktopCols,
  heightClass,
  borderClass,
  duplicateKey,
  priorityFirst,
}: {
  tiles: HeroCategoryTile[];
  desktopCols: number;
  heightClass: string;
  borderClass: string;
  duplicateKey: string;
  priorityFirst: boolean;
}) {
  return (
    <div className={`${desktopGridClass(desktopCols)} w-full`}>
      {tiles.map((tile, index) => (
        <CategoryGridTile
          key={`${duplicateKey}-${tile.level}-${tile.name}-${tile.category}-${index}`}
          tile={tile}
          heightClass={heightClass}
          borderClass={borderClass}
          priorityImage={priorityFirst && index === 0}
        />
      ))}
    </div>
  );
}

export default function CategoryCatalogMarquee({
  tiles,
  maxTiles,
  ariaLabel = 'Danh mục sản phẩm',
  rowClassName = 'hero-category-grid-row flex h-[100px] sm:h-[112px] md:h-[148px] w-full shrink-0',
  viewportClassName = 'relative h-full w-full',
  manualScroll = false,
  desktopCols = 4,
}: CategoryCatalogMarqueeProps) {
  const [touchPaused, setTouchPaused] = useState(false);
  const [hoverPaused, setHoverPaused] = useState(false);

  const displayTiles = useMemo(() => {
    const l23 = tiles.filter((t) => t.level === 2 || t.level === 3);
    const cap = maxTiles ?? l23.length;
    return l23.slice(0, cap);
  }, [tiles, maxTiles]);

  const heightClass = tileHeightFromRowClass(rowClassName);
  const borderClass = lastColBorderClass(desktopCols);
  const isPaused = touchPaused || hoverPaused;

  if (displayTiles.length === 0) return null;

  if (manualScroll) {
    return (
      <div
        className={`category-catalog-scroll relative w-full overflow-y-auto overflow-x-hidden overscroll-y-contain ${viewportClassName}`}
        aria-label={ariaLabel}
        style={{ WebkitOverflowScrolling: 'touch' }}
      >
        <TileGrid
          tiles={displayTiles}
          desktopCols={desktopCols}
          heightClass={heightClass}
          borderClass={borderClass}
          duplicateKey="manual"
          priorityFirst
        />
      </div>
    );
  }

  return (
    <div
      className={`hero-category-viewport overflow-hidden ${viewportClassName} ${isPaused ? 'is-paused' : ''}`}
      aria-label={ariaLabel}
      onMouseEnter={() => setHoverPaused(true)}
      onMouseLeave={() => setHoverPaused(false)}
      onTouchStart={() => setTouchPaused(true)}
      onTouchEnd={() => setTouchPaused(false)}
      onTouchCancel={() => setTouchPaused(false)}
    >
      <div
        className="pointer-events-none absolute inset-0 z-[1] bg-[radial-gradient(ellipse_80%_60%_at_50%_0%,rgba(255,255,255,0.14),transparent_55%)]"
        aria-hidden
      />
      <div className="hero-category-marquee-vertical relative z-0 flex w-full flex-col">
        <TileGrid
          tiles={displayTiles}
          desktopCols={desktopCols}
          heightClass={heightClass}
          borderClass={borderClass}
          duplicateKey="a"
          priorityFirst
        />
        <TileGrid
          tiles={displayTiles}
          desktopCols={desktopCols}
          heightClass={heightClass}
          borderClass={borderClass}
          duplicateKey="b"
          priorityFirst={false}
        />
      </div>
    </div>
  );
}
