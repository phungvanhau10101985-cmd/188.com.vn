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
  /** SSR: tile cache DB — hiển thị ngay khi vào trang chủ */
  initialHeroCategories?: HeroCategoryTilesResponse | null;
  onVariantChange?: (variant: HeroVariant) => void;
}

const HERO_CATEGORY_TILE_COUNT = 16;

export default function PersonalizedHeroBanner({
  sameShopLoading,
  behaviorKey,
  isAuthenticated,
  userGender,
  initialHeroCategories = null,
  onVariantChange,
}: PersonalizedHeroBannerProps) {
  const [latestSearchQuery, setLatestSearchQuery] = useState<string | null>(null);
  const [searchResolved, setSearchResolved] = useState(false);
  const [heroCategories, setHeroCategories] = useState<HeroCategoryTilesResponse | null>(
    initialHeroCategories ?? null,
  );
  const [categoriesResolved, setCategoriesResolved] = useState(
    Boolean(initialHeroCategories?.tiles?.length),
  );

  const defaultGender: 'Nam' | 'Nữ' =
    userGender === 'female' ? 'Nữ' : userGender === 'male' ? 'Nam' : 'Nam';

  useEffect(() => {
    let cancelled = false;
    setSearchResolved(false);

    void apiClient
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
      });

    return () => {
      cancelled = true;
    };
  }, [behaviorKey]);

  useEffect(() => {
    let cancelled = false;

    const hasInitial =
      Boolean(initialHeroCategories?.tiles?.length) &&
      (initialHeroCategories?.gender_label === defaultGender ||
        userGender == null);

    if (hasInitial) {
      setHeroCategories(initialHeroCategories!);
      setCategoriesResolved(true);
    }

    void apiClient
      .getHeroCategoryTiles(HERO_CATEGORY_TILE_COUNT, 8)
      .then((res) => {
        if (cancelled) return;
        if (res.tiles?.length) {
          setHeroCategories(res);
        } else if (!hasInitial) {
          return apiClient.getHeroCategoryTilesCached(defaultGender, HERO_CATEGORY_TILE_COUNT);
        }
        return null;
      })
      .then((fallback) => {
        if (cancelled || !fallback?.tiles?.length) return;
        setHeroCategories(fallback);
      })
      .catch(() => {
        if (cancelled || hasInitial) return;
        return apiClient
          .getHeroCategoryTilesCached(defaultGender, HERO_CATEGORY_TILE_COUNT)
          .then((cached) => {
            if (!cancelled && cached.tiles?.length) setHeroCategories(cached);
          });
      })
      .finally(() => {
        if (!cancelled) setCategoriesResolved(true);
      });

    return () => {
      cancelled = true;
    };
  }, [behaviorKey, defaultGender, initialHeroCategories, userGender]);

  const l23Count = useMemo(
    () => heroCategories?.tiles.filter((t) => t.level === 2 || t.level === 3).length ?? 0,
    [heroCategories?.tiles],
  );

  const variant: HeroVariant = useMemo(() => {
    if (!searchResolved || !categoriesResolved) {
      return l23Count > 0 ? 'categories' : 'brand';
    }
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
        className="relative flex h-52 flex-col overflow-hidden bg-gradient-to-br from-[#ea580c] via-orange-500 to-amber-600 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.2)] sm:h-56 md:h-72"
        role="region"
      >
        <div className="relative min-h-0 flex-1">
          <CategoryCatalogMarquee
            tiles={heroCategories.tiles}
            maxTiles={HERO_CATEGORY_TILE_COUNT}
            ariaLabel={heroCategories.heading || 'Danh mục gợi ý'}
            viewportClassName="absolute inset-0"
            desktopCols={5}
            rowClassName="hero-category-grid-row flex h-[88px] sm:h-[96px] md:h-[115px] w-full shrink-0"
          />
          <div
            className="pointer-events-none absolute inset-x-0 bottom-0 z-20 h-10 bg-gradient-to-t from-black/35 to-transparent"
            aria-hidden
          />
        </div>
        <div className="relative z-30 flex shrink-0 items-center justify-center border-t border-white/15 bg-black/15 px-3 py-2 backdrop-blur-sm md:py-2.5">
          <Link
            href="/danh-muc"
            prefetch
            className="inline-flex min-h-[36px] items-center justify-center gap-1.5 rounded-full border border-white/40 bg-white/95 px-3.5 py-1.5 text-[11px] font-medium leading-none text-[#9a3412] shadow-sm ring-1 ring-black/5 transition-[background-color,transform,box-shadow] hover:bg-white hover:shadow active:scale-[0.98] md:min-h-[38px] md:gap-2 md:px-4 md:text-xs"
          >
            <span>Xem tất cả danh mục</span>
            <svg
              className="h-3.5 w-3.5 shrink-0 opacity-70"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2.5}
              aria-hidden
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
          </Link>
        </div>
      </div>
    </section>
  );
}
