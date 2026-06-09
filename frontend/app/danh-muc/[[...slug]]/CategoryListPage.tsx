'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import Button from '@/components/ui/Button';
import { apiClient } from '@/lib/api-client';
import { sortCategoryTiles } from '@/lib/category-tree-sort';
import CategoryCatalogMarquee from '@/components/category/CategoryCatalogMarquee';
import type {
  CategoryLevel1,
  CategoryLevel2,
  CategoryLevel3,
  HeroCategoryTile,
} from '@/types/api';

interface CategoryListPageProps {
  categoryTree: CategoryLevel1[];
  /** SSR từ catalog-tiles — hiển thị ngay, không chờ fetch client. */
  initialTiles?: HeroCategoryTile[];
}

const EXTRA_LINKS = [{ label: 'SALE SỐC', href: '/deals' }];

/** Dự phòng khi API catalog-tiles lỗi — dùng cây SSR (không có ảnh / số mặt). */
function tilesFromCategoryTree(tree: CategoryLevel1[]): HeroCategoryTile[] {
  const out: HeroCategoryTile[] = [];
  for (const l1 of tree) {
    const cat1 = l1.name?.trim();
    if (!cat1) continue;
    for (const l2 of (l1.children || []) as CategoryLevel2[]) {
      const sub = l2.name?.trim();
      if (!sub) continue;
      out.push({
        level: 2,
        name: sub,
        category: cat1,
        subcategory: sub,
        product_count: 0,
        purchases: 0,
        ctr_hint: '',
        aspect_ratio: 'square',
      });
      for (const l3 of (l2.children || []) as CategoryLevel3[]) {
        const subsub = l3.name?.trim();
        if (!subsub) continue;
        out.push({
          level: 3,
          name: subsub,
          category: cat1,
          subcategory: sub,
          sub_subcategory: subsub,
          product_count: 0,
          purchases: 0,
          ctr_hint: '',
          aspect_ratio: 'square',
        });
      }
    }
  }
  return out;
}

export default function CategoryListPage({
  categoryTree,
  initialTiles = [],
}: CategoryListPageProps) {
  const hasInitialTiles = initialTiles.length > 0;

  const [tiles, setTiles] = useState<HeroCategoryTile[]>(initialTiles);
  const [genderSuffix, setGenderSuffix] = useState<string | null>(null);
  const [loading, setLoading] = useState(!hasInitialTiles);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const loadGender = () =>
      apiClient.getInferredCategoryGender(8).then((gender) => {
        if (!cancelled) setGenderSuffix(gender.gender_suffix);
      });

    if (hasInitialTiles && reloadKey === 0) {
      void loadGender().catch(() => {});
      return () => {
        cancelled = true;
      };
    }

    setLoading(true);
    setError(null);

    void Promise.all([apiClient.getCategoryCatalogTiles(120), apiClient.getInferredCategoryGender(8)])
      .then(([catalog, gender]) => {
        if (cancelled) return;
        const apiTiles = catalog.tiles;
        setTiles(apiTiles.length > 0 ? apiTiles : tilesFromCategoryTree(categoryTree));
        setGenderSuffix(gender.gender_suffix);
      })
      .catch(() => {
        if (!cancelled) {
          setTiles(tilesFromCategoryTree(categoryTree));
          setError('Không tải được danh mục. Vui lòng thử lại.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [reloadKey, categoryTree, hasInitialTiles]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onView = () => setReloadKey((k) => k + 1);
    window.addEventListener('188-product-viewed', onView);
    return () => window.removeEventListener('188-product-viewed', onView);
  }, []);

  const sortedTiles = useMemo(
    () => sortCategoryTiles(tiles, genderSuffix),
    [tiles, genderSuffix],
  );

  const hasGrid = sortedTiles.length > 0;

  return (
    <div className="min-h-screen w-full bg-white pb-16 md:pb-8">
      <h1 className="sr-only">Tất cả danh mục</h1>

      {loading ? (
        <div
          className="relative left-1/2 h-[min(72vh,640px)] w-screen max-w-[100vw] -translate-x-1/2 overflow-hidden bg-gradient-to-br from-orange-100 to-amber-50 md:left-0 md:h-[min(78vh,720px)] md:w-full md:max-w-7xl md:translate-x-0 md:mx-auto"
          aria-busy="true"
          aria-label="Đang tải danh mục"
        >
          <div className="absolute inset-0 animate-pulse bg-gradient-to-br from-orange-200/40 via-orange-100/30 to-amber-100/40" />
        </div>
      ) : null}

      {error && !loading ? (
        <div className="mx-4 mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 md:mx-auto md:max-w-7xl">
          {error}{' '}
          <Button
            type="button"
            variant="ghost"
            size="inline"
            onClick={() => {
              setError(null);
              setLoading(true);
              setReloadKey((k) => k + 1);
            }}
            className="underline font-medium text-red-700 hover:bg-transparent"
          >
            Thử lại
          </Button>
        </div>
      ) : null}

      {!loading && !error && hasGrid ? (
        <section
          className="relative left-1/2 w-screen max-w-[100vw] -translate-x-1/2 overflow-hidden md:left-0 md:w-full md:max-w-7xl md:translate-x-0 md:mx-auto"
          aria-label="Lưới danh mục"
        >
          <div
            className="relative h-[min(72vh,640px)] overflow-hidden bg-gradient-to-br from-[#ea580c] via-orange-500 to-amber-600 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.2)] md:h-[min(78vh,720px)]"
            role="region"
          >
            <CategoryCatalogMarquee
              tiles={sortedTiles}
              manualScroll
              desktopCols={5}
              rowClassName="hero-category-grid-row flex h-[108px] sm:h-[120px] md:h-[156px] w-full shrink-0"
            />
          </div>
        </section>
      ) : null}

      {!loading && !error && !hasGrid ? (
        <p className="px-4 py-8 text-center text-sm text-gray-500">Chưa có danh mục để hiển thị.</p>
      ) : null}

      <nav className="mt-4 border-t border-gray-100 px-4 md:mx-auto md:max-w-7xl" aria-label="Liên kết đặc biệt">
        {EXTRA_LINKS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="flex min-h-[48px] items-center justify-between border-b border-gray-200 py-3 text-sm font-semibold uppercase text-gray-900 active:bg-gray-50 hover:text-[#ea580c]"
          >
            {item.label}
            <svg className="h-5 w-5 flex-shrink-0 text-[#ea580c]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </Link>
        ))}
      </nav>

      <div className="hidden border-t border-gray-100 px-4 py-4 md:mx-auto md:block md:max-w-7xl">
        <Link href="/" className="text-sm font-medium text-[#ea580c] hover:underline">
          ← Về trang chủ
        </Link>
      </div>
    </div>
  );
}
