'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import ProductGrid from '@/components/ProductGrid';
import CategoryProductFilters from '@/components/CategoryProductFilters';
import type { CategoryProductFacets } from '@/lib/category-seo';
import { getListingFreshnessMonthLabel } from '@/lib/listing-freshness-label';
import type { Product } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { filterStorefrontVisibleProducts } from '@/lib/warehouse-clearance';

type Props = {
  initialProducts: Product[];
  initialTotal: number;
  initialPage: number;
  initialTotalPages: number;
  pageSize: number;
  listingQueryString: string;
};

function hasNonPageFilters(listingQs: string): boolean {
  const p = new URLSearchParams(listingQs);
  p.delete('page');
  return p.toString().length > 0;
}

export default function KhoSalePageClient({
  initialProducts,
  initialTotal,
  initialPage,
  initialTotalPages,
  pageSize,
  listingQueryString,
}: Props) {
  const basePath = '/kho-sale';
  const [products, setProducts] = useState<Product[]>(
    filterStorefrontVisibleProducts(initialProducts),
  );
  const [total, setTotal] = useState(initialTotal);
  const [totalPages, setTotalPages] = useState(initialTotalPages);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [facets, setFacets] = useState<CategoryProductFacets | null>(null);

  const currentPage = initialPage;
  const from = total === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const to = Math.min(currentPage * pageSize, total);
  const monthLabel = getListingFreshnessMonthLabel();

  const filterParams = useMemo(() => {
    const p = new URLSearchParams(listingQueryString);
    return {
      min_price: p.get('min_price'),
      max_price: p.get('max_price'),
      size: p.get('size'),
      color: p.get('color'),
      style_tag: p.get('style_tag'),
      sort: p.get('sort'),
    };
  }, [listingQueryString]);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const p = new URLSearchParams(listingQueryString);
      const skip = (currentPage - 1) * pageSize;
      const minRaw = p.get('min_price');
      const maxRaw = p.get('max_price');
      const res = await apiClient.getProducts({
        warehouse_clearance_only: true,
        is_active: true,
        limit: pageSize,
        skip,
        sort: p.get('sort') || 'newest',
        size: p.get('size') || undefined,
        color: p.get('color') || undefined,
        style_tag: p.get('style_tag') || undefined,
        min_price: minRaw ? parseFloat(minRaw) : undefined,
        max_price: maxRaw ? parseFloat(maxRaw) : undefined,
      });
      const visible = filterStorefrontVisibleProducts(res.products ?? []);
      setProducts(visible);
      setTotal(visible.length === 0 && (res.products?.length ?? 0) > 0 ? 0 : (res.total ?? 0));
      setTotalPages(res.total_pages ?? 1);
    } catch {
      setError('Không tải được danh sách kho sale. ');
      setProducts([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [listingQueryString, currentPage, pageSize]);

  useEffect(() => {
    if (!hasNonPageFilters(listingQueryString) && currentPage === initialPage) {
      setProducts(filterStorefrontVisibleProducts(initialProducts));
      setTotal(
        filterStorefrontVisibleProducts(initialProducts).length === 0 && initialProducts.length > 0
          ? 0
          : initialTotal,
      );
      setTotalPages(initialTotalPages);
      return;
    }
    void reload();
  }, [
    listingQueryString,
    currentPage,
    initialPage,
    initialProducts,
    initialTotal,
    initialTotalPages,
    reload,
  ]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await apiClient.getProductListingFacets({
          warehouse_clearance_only: 'true',
          is_active: 'true',
        });
        if (!cancelled) setFacets(data);
      } catch {
        if (!cancelled) setFacets(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mx-auto max-w-7xl px-3 py-6 sm:px-4 lg:px-6">
      <nav className="mb-3 text-sm text-gray-500" aria-label="Breadcrumb">
        <Link href="/" className="hover:text-gray-800">
          Trang chủ
        </Link>
        <span className="mx-2">/</span>
        <span className="text-gray-900 font-medium">Sale hàng hoàn</span>
      </nav>

      <header className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 sm:text-3xl">
          Sale hàng hoàn — thanh lý xả kho {monthLabel}
        </h1>
        <p className="mt-2 max-w-3xl text-sm text-gray-600 leading-relaxed">
          Hàng hoàn và tồn kho thanh lý — <strong className="text-amber-900">giá ưu đãi</strong>, thường chỉ còn
          một số size. Mỗi thẻ gắn loại <strong>hàng thanh lý kho</strong>; đặt hàng qua nút thanh lý trên trang
          chi tiết.
        </p>
        {total > 0 && (
          <p className="mt-2 text-sm text-gray-500">
            Hiển thị {from}–{to} / {total} sản phẩm
          </p>
        )}
      </header>

      {facets && (
        <div className="mb-4">
          <CategoryProductFilters
            facets={facets}
            basePath={basePath}
            enableListingFacetShell
            compact
          />
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
          <button type="button" onClick={() => void reload()} className="ml-2 font-medium underline">
            Thử lại
          </button>
        </div>
      )}

      {products.length === 0 && !loading ? (
        <p className="py-12 text-center text-gray-500">Chưa có sản phẩm kho sale đang hiển thị.</p>
      ) : (
        <ProductGrid
          products={products}
          loading={loading}
          selectedCategory="Kho sale — thanh lý"
          showFilters={false}
        />
      )}

      {totalPages > 1 && (
        <nav className="mt-8 flex justify-center gap-2" aria-label="Phân trang">
          {currentPage > 1 && (
            <Link
              href={`${basePath}?${new URLSearchParams({ ...Object.fromEntries(new URLSearchParams(listingQueryString)), page: String(currentPage - 1) }).toString()}`}
              className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50"
            >
              Trước
            </Link>
          )}
          <span className="flex items-center px-3 text-sm text-gray-600">
            Trang {currentPage} / {totalPages}
          </span>
          {currentPage < totalPages && (
            <Link
              href={`${basePath}?${new URLSearchParams({ ...Object.fromEntries(new URLSearchParams(listingQueryString)), page: String(currentPage + 1) }).toString()}`}
              className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50"
            >
              Sau
            </Link>
          )}
        </nav>
      )}
    </main>
  );
}
