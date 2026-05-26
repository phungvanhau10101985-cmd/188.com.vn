'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { getOptimizedImage } from '@/lib/image-utils';
import { categorySegmentForUrl } from '@/lib/category-url';
import type { HeroCategoryTile } from '@/types/api';

function useGridCols(desktopCols: number): number {
  const [cols, setCols] = useState(2);
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mq = window.matchMedia('(min-width: 768px)');
    const update = () => setCols(mq.matches ? desktopCols : 2);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, [desktopCols]);
  return cols;
}

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

function chunkTiles(list: HeroCategoryTile[], cols: number, padLastRow: boolean): HeroCategoryTile[][] {
  if (list.length === 0) return [];
  const rows: HeroCategoryTile[][] = [];
  for (let i = 0; i < list.length; i += cols) {
    const row = list.slice(i, i + cols);
    if (padLastRow) {
      let pad = 0;
      while (row.length < cols) {
        row.push(list[pad % list.length]);
        pad += 1;
      }
    }
    rows.push(row);
  }
  return rows;
}

function CategoryGridTile({
  tile,
  isLastInRow,
  priorityImage = false,
}: {
  tile: HeroCategoryTile;
  isLastInRow?: boolean;
  priorityImage?: boolean;
}) {
  const href = categoryTileHref(tile);
  const title = tileTitle(tile);
  const itemCountLabel = formatItemCount(tile.product_count);
  const img = tile.image_url
    ? getOptimizedImage(tile.image_url, {
        width: 400,
        height: 400,
        quality: 82,
        fallbackStrategy: 'local',
      })
    : null;

  return (
    <Link
      href={href}
      title={itemCountLabel ? `${tile.name} · ${itemCountLabel}` : tile.name}
      className={`hero-category-tile group relative flex h-full min-w-0 flex-1 flex-col overflow-hidden border-r border-white/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-white active:brightness-105 ${isLastInRow ? 'border-r-0' : ''}`}
    >
      <div className="relative flex-1 min-h-0 overflow-hidden bg-gradient-to-br from-orange-600/95 via-orange-500/90 to-amber-700/95">
        {img ? (
          <Image
            src={img}
            alt={title}
            fill
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
    </Link>
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

export default function CategoryCatalogMarquee({
  tiles,
  maxTiles,
  ariaLabel = 'Danh mục sản phẩm',
  rowClassName = 'hero-category-grid-row flex h-[100px] sm:h-[112px] md:h-[148px] w-full shrink-0',
  viewportClassName = 'relative h-full w-full',
  manualScroll = false,
  desktopCols = 4,
}: CategoryCatalogMarqueeProps) {
  const gridCols = useGridCols(desktopCols);
  const [touchPaused, setTouchPaused] = useState(false);
  const [hoverPaused, setHoverPaused] = useState(false);
  const viewportRef = useRef<HTMLDivElement>(null);

  const displayTiles = useMemo(() => {
    const l23 = tiles.filter((t) => t.level === 2 || t.level === 3);
    const cap = maxTiles ?? l23.length;
    return l23.slice(0, cap);
  }, [tiles, maxTiles]);

  const rows = useMemo(() => {
    const chunked = chunkTiles(displayTiles, gridCols, !manualScroll);
    if (manualScroll || chunked.length === 0) return chunked;
    let expanded = [...chunked];
    while (expanded.length < 2) {
      expanded = expanded.concat(chunked);
    }
    return [...expanded, ...expanded];
  }, [displayTiles, gridCols, manualScroll]);

  const isPaused = touchPaused || hoverPaused;

  useEffect(() => {
    if (manualScroll) return;
    const el = viewportRef.current;
    if (!el) return;

    let raf = 0;
    const tick = () => {
      if (!isPaused) {
        el.scrollTop += 0.55;
        const half = el.scrollHeight / 2;
        if (half > 0 && el.scrollTop >= half - 1) {
          el.scrollTop = 0;
        }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [manualScroll, isPaused, rows.length]);

  if (rows.length === 0) return null;

  if (manualScroll) {
    return (
      <div
        className={`category-catalog-scroll relative w-full overflow-y-auto overflow-x-hidden overscroll-y-contain ${viewportClassName}`}
        aria-label={ariaLabel}
        style={{ WebkitOverflowScrolling: 'touch' }}
      >
        <div className="relative z-0 flex w-full flex-col">
          {rows.map((rowTiles, rowIndex) => (
            <div key={`row-${rowIndex}`} className={rowClassName}>
              {rowTiles.map((tile, colIndex) => (
                <CategoryGridTile
                  key={`${rowIndex}-${tile.level}-${tile.name}-${tile.category}`}
                  tile={tile}
                  isLastInRow={colIndex === rowTiles.length - 1}
                  priorityImage={rowIndex === 0 && colIndex === 0}
                />
              ))}
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div
      ref={viewportRef}
      className={`hero-category-viewport hero-category-viewport--scroll overflow-y-auto overflow-x-hidden overscroll-y-contain touch-pan-y ${viewportClassName} ${isPaused ? 'is-paused' : ''}`}
      aria-label={ariaLabel}
      style={{ WebkitOverflowScrolling: 'touch' }}
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
        {rows.map((rowTiles, rowIndex) => (
          <div key={`row-${rowIndex}`} className={rowClassName}>
            {rowTiles.map((tile, colIndex) => (
              <CategoryGridTile
                key={`${rowIndex}-${tile.level}-${tile.name}-${tile.category}`}
                tile={tile}
                isLastInRow={colIndex === rowTiles.length - 1}
                priorityImage={rowIndex === 0 && colIndex === 0}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
