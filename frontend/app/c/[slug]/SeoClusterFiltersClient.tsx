'use client';

import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import CategoryProductFilters from '@/components/CategoryProductFilters';
import { getSeoClusterFacets, type SeoClusterProductFacets } from '@/lib/seo-cluster';

type Props = {
  slug: string;
};

export default function SeoClusterFiltersClient({ slug }: Props) {
  const searchParams = useSearchParams();
  const [facets, setFacets] = useState<SeoClusterProductFacets | null>(null);

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

  useEffect(() => {
    let cancelled = false;
    setFacets(null);
    getSeoClusterFacets(slug, filters)
      .then((next) => {
        if (!cancelled) setFacets(next);
      })
      .catch(() => {
        if (!cancelled) setFacets({ sizes: [], colors: [], style_tags: [], price_min: null, price_max: null });
      });
    return () => {
      cancelled = true;
    };
  }, [slug, filters]);

  return <CategoryProductFilters basePath={`/c/${slug}`} facets={facets} enableListingFacetShell compact />;
}
