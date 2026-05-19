'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import CategoryCatalogMarquee from '@/components/category/CategoryCatalogMarquee';
import type { HeroCategoryTilesResponse, Product } from '@/types/api';

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

export default function PersonalizedHeroBanner({
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

  const showCategoryGrid =
    variant === 'categories' && heroCategories != null && l23Count > 0;

  if (!showCategoryGrid) {
    return null;
  }

  return (
    <section
      className="relative left-1/2 mb-4 w-screen max-w-[100vw] -translate-x-1/2 overflow-hidden rounded-none shadow-lg md:left-0 md:mb-10 md:w-full md:max-w-none md:translate-x-0 md:rounded-2xl md:border md:border-white/20 md:shadow-xl md:ring-1 md:ring-black/5"
      aria-label="Danh mục gợi ý"
    >
      <div
        className="relative h-48 sm:h-52 md:h-72 overflow-hidden bg-gradient-to-br from-[#ea580c] via-orange-500 to-amber-600 text-white p-0 shadow-[inset_0_1px_0_rgba(255,255,255,0.2)]"
        role="region"
      >
        <CategoryCatalogMarquee
          tiles={heroCategories.tiles}
          maxTiles={HERO_CATEGORY_TILE_COUNT}
          ariaLabel={heroCategories.heading || 'Danh mục gợi ý'}
          viewportClassName="absolute inset-0"
          desktopCols={5}
          rowClassName="hero-category-grid-row flex h-[88px] sm:h-[96px] md:h-[115px] w-full shrink-0"
        />
        <Link
          href="/danh-muc"
          className="absolute bottom-2.5 left-1/2 z-30 flex min-h-[40px] -translate-x-1/2 items-center justify-center whitespace-nowrap rounded-full bg-white px-4 py-2 text-xs font-semibold text-[#c2410c] shadow-md active:scale-[0.98] md:bottom-3 md:min-h-[44px] md:px-5 md:text-sm"
        >
          Xem tất cả danh mục
        </Link>
      </div>
    </section>
  );
}
