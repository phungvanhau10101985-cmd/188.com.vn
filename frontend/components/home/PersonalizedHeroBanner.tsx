'use client';

import { useEffect, useMemo, useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import { getOptimizedImage } from '@/lib/image-utils';
import { categorySegmentForUrl } from '@/lib/category-url';
import type { HeroCategoryTile, HeroCategoryTilesResponse, Product } from '@/types/api';

export type HeroVariant = 'search' | 'categories' | 'brand';

export interface PersonalizedHeroBannerProps {
  apiStatus: 'checking' | 'online' | 'offline';
  sameShopTotal: number;
  sameShopLoading: boolean;
  shopName: string | null;
  previewProducts: Product[];
  behaviorKey: string;
  isAuthenticated: boolean;
  userGender: 'male' | 'female' | null;
  onVariantChange?: (variant: HeroVariant) => void;
}

const HERO_CATEGORY_TILE_COUNT = 16;

function useHeroGridCols(): number {
  const [cols, setCols] = useState(2);
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mq = window.matchMedia('(min-width: 768px)');
    const update = () => setCols(mq.matches ? 4 : 2);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);
  return cols;
}

function categoryTileHref(tile: HeroCategoryTile): string {
  const s1 = categorySegmentForUrl(tile.category);
  if (!s1) return '/';
  const s2 = categorySegmentForUrl(tile.subcategory || tile.name);
  if (tile.level === 2) return `/danh-muc/${s1}/${s2}`;
  const s3 = categorySegmentForUrl(tile.sub_subcategory || tile.name);
  return `/danh-muc/${s1}/${s2}/${s3}`;
}

function tileTitle(tile: HeroCategoryTile): string {
  const raw = (tile.short_name || tile.name || '').trim();
  return raw.replace(/\s+(Nam|Nữ)$/i, '').trim();
}

function formatItemCount(count: number): string {
  const n = Math.max(0, Math.floor(count));
  if (n <= 0) return '';
  return `${n.toLocaleString('vi-VN')} mặt`;
}

function BrandHeroContent({ apiStatus }: { apiStatus: PersonalizedHeroBannerProps['apiStatus'] }) {
  return (
    <div className="relative text-center px-4 md:px-6 max-w-2xl mx-auto">
      <h2 className="text-xl sm:text-2xl md:text-4xl font-bold tracking-tight mb-2 drop-shadow-sm">188.COM.VN</h2>
      <p className="text-base md:text-lg text-white/95 font-medium mb-1">Xem là thích — Click là mê</p>
      <p className="text-sm text-white">
        Mua sắm khám phá toàn cửa hàng
        {apiStatus === 'online' ? (
          <>
            {' '}
            <span aria-hidden className="text-white/95">
              ·
            </span>{' '}
            <span className="text-white/95">Kết nối ổn định</span>
          </>
        ) : null}
      </p>
    </div>
  );
}

function chunkTiles(list: HeroCategoryTile[], cols: number): HeroCategoryTile[][] {
  if (list.length === 0) return [];
  const rows: HeroCategoryTile[][] = [];
  for (let i = 0; i < list.length; i += cols) {
    const row = list.slice(i, i + cols);
    let pad = 0;
    while (row.length < cols) {
      row.push(list[pad % list.length]);
      pad += 1;
    }
    rows.push(row);
  }
  return rows;
}

function CategoryGridTile({ tile }: { tile: HeroCategoryTile }) {
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
      className="hero-category-tile group relative flex h-full min-w-0 flex-1 flex-col overflow-hidden border-r border-white/10 [&:nth-child(2n)]:border-r-0 md:[&:nth-child(2n)]:border-r md:[&:nth-child(4n)]:border-r-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-white active:brightness-105"
    >
      <div className="relative flex-1 min-h-0 overflow-hidden bg-gradient-to-br from-orange-600/95 via-orange-500/90 to-amber-700/95">
        {img ? (
          <Image
            src={img}
            alt={title}
            fill
            sizes="200px"
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

function CategoriesHeroContent({ data }: { data: HeroCategoryTilesResponse }) {
  const gridCols = useHeroGridCols();
  const [touchPaused, setTouchPaused] = useState(false);
  const tiles = useMemo(
    () => data.tiles.filter((t) => t.level === 2 || t.level === 3).slice(0, HERO_CATEGORY_TILE_COUNT),
    [data.tiles],
  );

  const loopRows = useMemo(() => {
    const rows = chunkTiles(tiles, gridCols);
    if (rows.length === 0) return [];
    let expanded = [...rows];
    while (expanded.length < 2) {
      expanded = expanded.concat(rows);
    }
    return [...expanded, ...expanded];
  }, [tiles, gridCols]);

  if (loopRows.length === 0) return null;

  return (
    <div
      className={`hero-category-viewport absolute inset-0 overflow-hidden touch-pan-y ${touchPaused ? 'is-paused' : ''}`}
      aria-label={data.heading || 'Danh mục gợi ý'}
      onTouchStart={() => setTouchPaused(true)}
      onTouchEnd={() => setTouchPaused(false)}
      onTouchCancel={() => setTouchPaused(false)}
    >
      <div
        className="pointer-events-none absolute inset-0 z-[1] bg-[radial-gradient(ellipse_80%_60%_at_50%_0%,rgba(255,255,255,0.14),transparent_55%)]"
        aria-hidden
      />
      <div className="hero-category-marquee-vertical relative z-0 flex w-full flex-col">
        {loopRows.map((rowTiles, rowIndex) => (
          <div
            key={`row-${rowIndex}`}
            className="hero-category-grid-row flex h-[92px] sm:h-[104px] md:h-[144px] w-full shrink-0"
          >
            {rowTiles.map((tile) => (
              <CategoryGridTile
                key={`${rowIndex}-${tile.level}-${tile.name}-${tile.category}`}
                tile={tile}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function SearchHeroContent({ query }: { query: string }) {
  const href = `/?q=${encodeURIComponent(query)}`;
  return (
    <div className="relative text-center px-6 max-w-2xl mx-auto">
      <p className="text-xs md:text-sm font-semibold uppercase tracking-wider text-white/85 mb-1">
        Tiếp tục tìm kiếm
      </p>
      <h2 className="text-xl md:text-3xl font-bold tracking-tight mb-2 drop-shadow-sm">
        Bạn đang quan tâm «{query}»
      </h2>
      <p className="text-sm md:text-base text-white/90 mb-4">
        Xem lại kết quả và sản phẩm liên quan trong kho 188.COM.VN
      </p>
      <Link
        href={href}
        className="inline-flex min-h-[44px] items-center justify-center rounded-xl bg-white text-[#c2410c] font-semibold text-sm px-6 py-2.5 shadow-md hover:bg-white/95 transition-colors focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-orange-500"
      >
        Xem kết quả tìm kiếm
      </Link>
    </div>
  );
}

export default function PersonalizedHeroBanner({
  apiStatus,
  sameShopLoading,
  behaviorKey,
  onVariantChange,
}: PersonalizedHeroBannerProps) {
  const [latestSearchQuery, setLatestSearchQuery] = useState<string | null>(null);
  const [searchResolved, setSearchResolved] = useState(false);
  const [heroCategories, setHeroCategories] = useState<HeroCategoryTilesResponse | null>(null);
  const [categoriesResolved, setCategoriesResolved] = useState(false);

  useEffect(() => {
    if (sameShopLoading) return;

    let cancelled = false;
    setSearchResolved(false);
    setCategoriesResolved(false);

    void Promise.all([
      apiClient
        .getSearchHistory(1)
        .then((rows) => {
          if (cancelled) return;
          setLatestSearchQuery(rows[0]?.search_query?.trim() || null);
        })
        .catch(() => {
          if (!cancelled) setLatestSearchQuery(null);
        })
        .finally(() => {
          if (!cancelled) setSearchResolved(true);
        }),
      apiClient
        .getHeroCategoryTiles(HERO_CATEGORY_TILE_COUNT, 8)
        .then((res) => {
          if (!cancelled) setHeroCategories(res);
        })
        .catch(() => {
          if (!cancelled) setHeroCategories(null);
        })
        .finally(() => {
          if (!cancelled) setCategoriesResolved(true);
        }),
    ]);

    return () => {
      cancelled = true;
    };
  }, [sameShopLoading, behaviorKey]);

  const l23Count = useMemo(
    () => heroCategories?.tiles.filter((t) => t.level === 2 || t.level === 3).length ?? 0,
    [heroCategories?.tiles],
  );

  const variant: HeroVariant = useMemo(() => {
    if (!searchResolved || !categoriesResolved) return 'brand';
    if (l23Count > 0) return 'categories';
    if (latestSearchQuery) return 'search';
    return 'brand';
  }, [searchResolved, categoriesResolved, latestSearchQuery, l23Count]);

  useEffect(() => {
    onVariantChange?.(variant);
  }, [variant, onVariantChange]);

  return (
    <div className="mx-3 mb-4 md:mx-0 md:mb-10 rounded-xl md:rounded-2xl overflow-hidden shadow-lg md:shadow-xl border border-white/20 ring-1 ring-black/5">
      <div
        className={`relative bg-gradient-to-br from-[#ea580c] via-orange-500 to-amber-600 text-white overflow-hidden ${variant === 'categories' ? 'h-44 sm:h-52 md:h-72 p-0' : 'min-h-[104px] h-auto py-6 md:py-0 md:h-52 flex items-center justify-center'} ${variant === 'categories' ? 'shadow-[inset_0_1px_0_rgba(255,255,255,0.2)]' : ''}`}
        role="region"
        aria-label={
          variant === 'search'
            ? 'Tiếp tục tìm kiếm'
            : variant === 'categories'
              ? heroCategories?.heading || 'Danh mục gợi ý'
              : '188.COM.VN'
        }
      >
        {variant === 'categories' && heroCategories && l23Count > 0 ? (
          <CategoriesHeroContent data={heroCategories} />
        ) : variant === 'search' && latestSearchQuery ? (
          <SearchHeroContent query={latestSearchQuery} />
        ) : (
          <BrandHeroContent apiStatus={apiStatus} />
        )}
      </div>
    </div>
  );
}
