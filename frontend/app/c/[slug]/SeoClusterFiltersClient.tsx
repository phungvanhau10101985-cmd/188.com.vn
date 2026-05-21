'use client';

import { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import CategoryProductFilters from '@/components/CategoryProductFilters';
import { getSeoClusterFacets, type SeoClusterProductFacets } from '@/lib/seo-cluster';

type Props = {
  slug: string;
  /** Facets SSR từ trang — hiển thị ngay trên mobile, không phụ thuộc fetch trình duyệt. */
  initialFacets?: SeoClusterProductFacets | null;
};

function FiltersBarSkeleton() {
  return (
    <div
      className="grid grid-cols-3 gap-1.5 w-full min-h-[2rem] rounded-lg bg-gray-100 animate-pulse"
      aria-hidden
    />
  );
}

function SeoClusterFiltersClientInner({ slug, initialFacets = null }: Props) {
  const searchParams = useSearchParams();
  const [facets, setFacets] = useState<SeoClusterProductFacets | null>(initialFacets);
  const skipInitialClientFetch = useRef(initialFacets != null);

  const filters = useMemo(
    () => ({
      minPrice: searchParams.get('min_price') ? Number(searchParams.get('min_price')) : null,
      maxPrice: searchParams.get('max_price') ? Number(searchParams.get('max_price')) : null,
      size: searchParams.get('size'),
      color: searchParams.get('color'),
      styleTag: searchParams.get('style_tag'),
    }),
    [searchParams],
  );

  const filtersKey = useMemo(() => JSON.stringify(filters), [filters]);

  useEffect(() => {
    if (skipInitialClientFetch.current) {
      skipInitialClientFetch.current = false;
      return;
    }

    let cancelled = false;
    getSeoClusterFacets(slug, filters)
      .then((next) => {
        if (!cancelled && next) setFacets(next);
      })
      .catch(() => {
        /* Giữ facets SSR / lần trước — mobile hay lỗi CORS nếu gọi sai origin API. */
      });
    return () => {
      cancelled = true;
    };
  }, [slug, filtersKey, filters]);

  return <CategoryProductFilters basePath={`/c/${slug}`} facets={facets} enableListingFacetShell compact />;
}

/** Bọc Suspense vì dùng `useSearchParams` (Next.js App Router). */
export default function SeoClusterFiltersClient(props: Props) {
  return (
    <Suspense fallback={<FiltersBarSkeleton />}>
      <SeoClusterFiltersClientInner {...props} />
    </Suspense>
  );
}
