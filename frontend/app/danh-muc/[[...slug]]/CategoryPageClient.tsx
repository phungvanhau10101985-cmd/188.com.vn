'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import ProductGrid from '@/components/ProductGrid';
import CategoryProductFilters from '@/components/CategoryProductFilters';
import type { CategoryProductFacets } from '@/lib/category-seo';
import { linkifySeoBody, type InternalLinkItem } from '@/lib/internal-links';
import { getListingFreshnessMonthLabel } from '@/lib/listing-freshness-label';
import type { Product } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import {
  buildCategoryListingClientCacheKey,
  readCategoryListingClientCache,
  writeCategoryListingClientCache,
} from '@/lib/category-listing-cache';

interface CategoryPageClientProps {
  breadcrumbNames: string[];
  pathSegments: string[];
  products: Product[];
  total: number;
  totalPages: number;
  currentPage: number;
  pageSize: number;
  seoBody: string | null;
  internalLinkMap?: InternalLinkItem[];
  error: string | null;
  facets: CategoryProductFacets | null;
  /** Query string hiện tại (không gồm ?) — dùng giữ bộ lọc khi phân trang. */
  listingQueryString: string;
}

function hasNonPageFilters(listingQs: string): boolean {
  const p = new URLSearchParams(listingQs);
  p.delete('page');
  return p.toString().length > 0;
}

export default function CategoryPageClient({
  breadcrumbNames,
  pathSegments,
  products,
  total,
  totalPages,
  currentPage,
  pageSize,
  seoBody,
  internalLinkMap = [],
  error,
  facets,
  listingQueryString,
}: CategoryPageClientProps) {
  const router = useRouter();
  const fullName = breadcrumbNames.join(' - ');
  const leafName = breadcrumbNames[breadcrumbNames.length - 1] || 'sản phẩm';
  const basePath = `/danh-muc/${pathSegments.join('/')}`;
  const category = breadcrumbNames[0];
  const subcategory = breadcrumbNames[1];
  const subSubcategory = breadcrumbNames[2];
  const pathKey = pathSegments.join('/');

  const monthLabel = getListingFreshnessMonthLabel();
  const h1Text = `${leafName} mới nhất ${monthLabel} | ${total} sản phẩm`;
  const [displayProducts, setDisplayProducts] = useState<Product[]>(products);
  const [displayTotal, setDisplayTotal] = useState(total);
  const [displayTotalPages, setDisplayTotalPages] = useState(totalPages);
  const [clientFacets, setClientFacets] = useState<CategoryProductFacets | null>(facets);
  const listingCacheKey = useMemo(
    () => buildCategoryListingClientCacheKey(pathKey, listingQueryString),
    [pathKey, listingQueryString],
  );
  const from = displayTotal === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const to = Math.min(currentPage * pageSize, displayTotal);

  useEffect(() => {
    setDisplayProducts(products);
    setDisplayTotal(total);
    setDisplayTotalPages(totalPages);
  }, [products, total, totalPages]);

  useEffect(() => {
    const cached = readCategoryListingClientCache(listingCacheKey);
    if (products.length > 0) return;
    if (!cached || cached.products.length === 0) return;
    setDisplayProducts(cached.products);
    setDisplayTotal(cached.total);
    setDisplayTotalPages(cached.totalPages);
  }, [listingCacheKey, products.length]);

  useEffect(() => {
    writeCategoryListingClientCache(listingCacheKey, {
      products,
      total,
      totalPages,
      currentPage,
      pageSize,
    });
  }, [currentPage, listingCacheKey, pageSize, products, total, totalPages]);

  const facetParams = useMemo(() => {
    const p = new URLSearchParams(listingQueryString);
    return {
      category,
      subcategory,
      sub_subcategory: subSubcategory,
      min_price: p.get('min_price'),
      max_price: p.get('max_price'),
      size: p.get('size'),
      color: p.get('color'),
      style_tag: p.get('style_tag'),
    };
  }, [category, subcategory, subSubcategory, listingQueryString]);

  const shouldRefreshRandomGrid = useMemo(() => {
    const p = new URLSearchParams(listingQueryString);
    p.delete('page');
    const sort = (p.get('sort') || '').trim().toLowerCase();
    p.delete('sort');
    return p.toString().length === 0 && (!sort || sort === 'random');
  }, [listingQueryString]);

  const warmupFilterParams = useMemo(() => {
    const p = new URLSearchParams(listingQueryString);
    const toNumber = (key: string) => {
      const raw = p.get(key);
      if (raw == null || raw.trim() === '') return null;
      const n = Number(raw);
      return Number.isFinite(n) && n >= 0 ? n : null;
    };
    return {
      min_price: toNumber('min_price'),
      max_price: toNumber('max_price'),
      size: p.get('size'),
      color: p.get('color'),
      style_tag: p.get('style_tag'),
      sort: (p.get('sort') || 'random').trim() || 'random',
    };
  }, [listingQueryString]);

  useEffect(() => {
    if (!shouldRefreshRandomGrid || !category) return;

    let cancelled = false;
    const seed =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

    apiClient
      .warmCategoryListingCache({
        limit: pageSize,
        skip: Math.max(0, (currentPage - 1) * pageSize),
        category,
        subcategory,
        sub_subcategory: subSubcategory,
        min_price: warmupFilterParams.min_price,
        max_price: warmupFilterParams.max_price,
        size: warmupFilterParams.size,
        color: warmupFilterParams.color,
        style_tag: warmupFilterParams.style_tag,
        sort: warmupFilterParams.sort,
        search_refresh: `category-client:${pathKey}:${seed}`,
      })
      .then(() => {
        if (cancelled) return;
      })
      .catch(() => {
        // Giữ lưới SSR/cache nếu warmup nền bị lỗi.
      });

    return () => {
      cancelled = true;
    };
  }, [category, currentPage, pageSize, pathKey, shouldRefreshRandomGrid, subSubcategory, subcategory, warmupFilterParams]);

  useEffect(() => {
    if (!category) return;
    let cancelled = false;
    setClientFacets(facets);
    if (facets != null) {
      return () => {
        cancelled = true;
      };
    }
    apiClient
      .getProductListingFacets(facetParams)
      .then((next) => {
        if (!cancelled) setClientFacets(next);
      })
      .catch(() => {
        if (!cancelled) setClientFacets({ sizes: [], colors: [], style_tags: [], price_min: null, price_max: null });
      });
    return () => {
      cancelled = true;
    };
  }, [category, facetParams, facets]);

  const queryWithPage = (nextPage: number) => {
    const p = new URLSearchParams(listingQueryString);
    if (nextPage <= 1) p.delete('page');
    else p.set('page', String(nextPage));
    const q = p.toString();
    return q ? `${basePath}?${q}` : basePath;
  };

  return (
    <main className="max-w-7xl mx-auto px-4 pt-4 pb-6 md:py-6" role="main" aria-label={fullName}>
      <nav className="text-sm text-gray-500 mb-4" aria-label="Breadcrumb">
        <Link href="/" className="hover:text-[#ea580c]">Trang chủ</Link>
        {breadcrumbNames.map((name, i) => (
          <span key={i}>
            <span className="mx-2">/</span>
            <Link
              href={`/danh-muc/${pathSegments.slice(0, i + 1).join('/')}`}
              className="hover:text-[#ea580c]"
            >
              {name}
            </Link>
          </span>
        ))}
      </nav>

      {/* H1 riêng; bộ lọc là sibling để sticky không bị giới hạn trong khối tiêu đề. */}
      <div className="mb-4">
        <h1 className="text-xl sm:text-2xl font-bold text-gray-900 leading-snug max-w-5xl">
          {h1Text}
        </h1>
      </div>

      {!error && (total > 0 || hasNonPageFilters(listingQueryString)) ? (
        <div className="sticky top-[var(--mobile-app-header-height)] z-40 mb-4 w-full border-b border-gray-200 bg-gray-50/95 px-1.5 py-1.5 shadow-sm backdrop-blur sm:px-3 md:top-[var(--listing-filter-sticky-top)] md:border-t-0 md:bg-gray-50 md:shadow-none md:backdrop-blur-none">
          <CategoryProductFilters basePath={basePath} facets={clientFacets} enableListingFacetShell compact />
        </div>
      ) : null}

      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 rounded-xl p-4 flex items-center justify-between">
          <p className="text-red-700 font-medium">{error}</p>
          <button
            onClick={() => router.push('/')}
            className="px-4 py-2 rounded-lg bg-red-500 text-white text-sm font-medium hover:bg-red-600"
          >
            Về trang chủ
          </button>
        </div>
      )}

      {!error && (
        <>
          <h2 className="text-lg font-semibold text-gray-800 mb-4">
            {displayTotal} {leafName} dành cho bạn
            {displayTotalPages > 1 && (
              <span className="text-gray-500 font-normal text-base ml-2">
                (trang {currentPage}/{displayTotalPages}, hiển thị {from}–{to})
              </span>
            )}
          </h2>
          <ProductGrid
            products={displayProducts}
            loading={false}
            selectedCategory={leafName}
            showFilters={false}
          />
          {displayTotalPages > 1 && (
            <nav className="mt-8 flex flex-wrap items-center justify-center gap-2" aria-label="Phân trang danh mục">
              {currentPage > 1 && (
                <Link
                  href={queryWithPage(currentPage - 1)}
                  className="px-4 py-2 rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 font-medium text-sm"
                >
                  ← Trang trước
                </Link>
              )}
              <span className="px-3 py-2 text-gray-600 text-sm">
                Trang {currentPage} / {displayTotalPages}
              </span>
              {currentPage < displayTotalPages && (
                <Link
                  href={queryWithPage(currentPage + 1)}
                  className="px-4 py-2 rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 font-medium text-sm"
                >
                  Trang sau →
                </Link>
              )}
            </nav>
          )}

          {seoBody && (
            <section
              className="mt-12 pt-8 border-t border-gray-200"
              aria-label="Giới thiệu danh mục"
            >
              <div
                className="prose prose-gray max-w-none text-gray-600 text-sm leading-relaxed"
                dangerouslySetInnerHTML={{
                  __html: linkifySeoBody(seoBody, internalLinkMap),
                }}
              />
            </section>
          )}
        </>
      )}
    </main>
  );
}
