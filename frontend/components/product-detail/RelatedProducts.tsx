// frontend/components/product-detail/RelatedProducts.tsx
'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import { cdnUrl } from '@/lib/cdn-url';
import Image from 'next/image';
import Link from 'next/link';
import type { Product, ProductSearchParams } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { formatPrice, getProductMainImage } from '@/lib/utils';
import {
  parseRelatedTabFromSearch,
  excelCell,
  filtersFromProduct,
  buildHomeListingHref,
  type ProductRelatedTabId,
} from '@/lib/product-related-tabs';

interface RelatedProductsProps {
  currentProduct: Product;
}

function sectionTitle(tab: ProductRelatedTabId): string {
  switch (tab) {
    case 'bestselling':
      return 'Sản phẩm bán chạy — cùng shop_id';
    case 'same_price':
      return 'Sản phẩm cùng shop — cùng shop_name';
    case 'lower_price':
      return 'Sản phẩm cùng loại — cùng pro_lower_price';
    case 'higher_price':
      return 'Sản phẩm cùng loại — cùng pro_high_price';
    default:
      return 'Sản phẩm liên quan';
  }
}

function emptyHint(tab: ProductRelatedTabId): string {
  switch (tab) {
    case 'bestselling':
      return 'Sản phẩm này chưa có shop_id — không lọc được nhóm bán chạy theo cửa hàng.';
    case 'same_price':
      return 'Sản phẩm này chưa có shop_name — không lọc được nhóm cùng tên shop.';
    case 'lower_price':
      return 'Sản phẩm này chưa có pro_lower_price — không lọc được nhóm giá thấp.';
    case 'higher_price':
      return 'Sản phẩm này chưa có pro_high_price — không lọc được nhóm giá cao.';
    default:
      return 'Không có dữ liệu để hiển thị.';
  }
}

function ProductRelatedCard({ product, imageSizes }: { product: Product; imageSizes: string }) {
  return (
    <Link
      href={`/products/${product.slug || product.id}`}
      className="group block bg-white rounded-lg border border-gray-200 overflow-hidden hover:shadow-md transition-all"
    >
      <div className="aspect-square bg-gray-100 overflow-hidden relative">
        <Image
          src={getProductMainImage(product)}
          alt={product.name}
          fill
          sizes={imageSizes}
          className="object-cover group-hover:scale-110 transition-transform duration-300"
          onError={(e) => {
            (e.currentTarget as HTMLImageElement).src = cdnUrl('/images/placeholder.jpg');
          }}
        />
      </div>

      <div className="p-2">
        <h4 className="font-medium text-gray-900 line-clamp-2 text-xs leading-tight mb-1 group-hover:text-[#ea580c] transition-colors">
          {product.name}
        </h4>

        <div className="flex items-baseline justify-between">
          <span className="text-sm font-bold text-[#ea580c]">{formatPrice(product.price)}</span>
          {product.original_price && product.original_price > product.price && (
            <span className="text-xs text-gray-500 line-through">{formatPrice(product.original_price)}</span>
          )}
        </div>

        {typeof product.purchases === 'number' && product.purchases > 0 && (
          <div className="mt-1 text-[10px] text-gray-500">Đã bán {product.purchases}</div>
        )}
      </div>
    </Link>
  );
}

type FetchPlan =
  | { ok: true; params: ProductSearchParams; sortPurchasesDesc?: boolean }
  | { ok: false };

function buildFetchPlan(product: Product, tab: ProductRelatedTabId): FetchPlan {
  const shopId = excelCell(product.shop_id);
  const shopName = excelCell(product.shop_name);
  const proLower = excelCell(product.pro_lower_price);
  const proHigh = excelCell(product.pro_high_price);

  const base: ProductSearchParams = { limit: 120, is_active: true };

  switch (tab) {
    case 'bestselling':
      if (!shopId) return { ok: false };
      return {
        ok: true,
        params: { ...base, shop_id: shopId },
        sortPurchasesDesc: true,
      };
    case 'same_price':
      if (!shopName) return { ok: false };
      return { ok: true, params: { ...base, shop_name: shopName } };
    case 'lower_price':
      if (!proLower) return { ok: false };
      return { ok: true, params: { ...base, pro_lower_price: proLower } };
    case 'higher_price':
      if (!proHigh) return { ok: false };
      return { ok: true, params: { ...base, pro_high_price: proHigh } };
    default:
      return { ok: false };
  }
}

const BESTSELLING_GRID_CLASS = 'grid grid-cols-2 lg:grid-cols-5 gap-4';
const BESTSELLING_IMAGE_SIZES = '(max-width: 1023px) 50vw, (min-width: 1024px) 20vw';

/** Desktop lg: 5 ô / +5; mobile: 2 ô / +2 — dùng cho «bán chạy» và «nhóm cùng shop». */
function relatedStripInitialVisible(len: number): number {
  if (typeof window === 'undefined') return Math.min(2, len);
  const lg = window.matchMedia('(min-width: 1024px)').matches;
  return Math.min(lg ? 5 : 2, len);
}

function relatedStripStep(): number {
  if (typeof window === 'undefined') return 2;
  return window.matchMedia('(min-width: 1024px)').matches ? 5 : 2;
}

export default function RelatedProducts({ currentProduct }: RelatedProductsProps) {
  const searchParams = useSearchParams();
  const relatedTab = parseRelatedTabFromSearch(searchParams.get('rt'));

  const title = useMemo(() => sectionTitle(relatedTab), [relatedTab]);
  const fullListingHref = useMemo(
    () => buildHomeListingHref(relatedTab, filtersFromProduct(currentProduct)),
    [
      relatedTab,
      currentProduct.shop_id,
      currentProduct.shop_name,
      currentProduct.pro_lower_price,
      currentProduct.pro_high_price,
    ]
  );

  const [relatedProducts, setRelatedProducts] = useState<Product[]>([]);
  const [shopGroupProducts, setShopGroupProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [visibleCount, setVisibleCount] = useState(5);
  const [showAllLoading, setShowAllLoading] = useState(false);

  const [shopGroupVisibleCount, setShopGroupVisibleCount] = useState(2);
  const [shopGroupShowAllLoading, setShopGroupShowAllLoading] = useState(false);

  const shopNameFilter = useMemo(() => excelCell(currentProduct.shop_name), [currentProduct.shop_name]);
  const sameShopGroupHref = useMemo(
    () => buildHomeListingHref('same_price', filtersFromProduct(currentProduct)),
    [
      currentProduct.shop_name,
      currentProduct.shop_id,
      currentProduct.pro_lower_price,
      currentProduct.pro_high_price,
    ]
  );

  const fetchRelatedProducts = useCallback(async () => {
    const plan = buildFetchPlan(currentProduct, relatedTab);
    if (!plan.ok) {
      setRelatedProducts([]);
      setShopGroupProducts([]);
      setShopGroupVisibleCount(relatedStripInitialVisible(0));
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      const shopName = excelCell(currentProduct.shop_name);
      const fetchSameShopNameGroup =
        relatedTab === 'bestselling' && shopName
          ? apiClient.getProducts({
              limit: 120,
              is_active: true,
              shop_name: shopName,
            })
          : Promise.resolve({ products: [] as Product[] });

      const [response, shopGroupResponse] = await Promise.all([
        apiClient.getProducts(plan.params),
        fetchSameShopNameGroup,
      ]);

      let list = (response.products || []).filter((p) => p.id !== currentProduct.id);
      if (plan.sortPurchasesDesc) {
        list = [...list].sort((a, b) => (b.purchases ?? 0) - (a.purchases ?? 0));
      }

      setRelatedProducts(list);
      setVisibleCount(relatedTab === 'bestselling' ? relatedStripInitialVisible(list.length) : 5);

      let sgList = (shopGroupResponse.products || []).filter((p) => p.id !== currentProduct.id);
      sgList = [...sgList].sort((a, b) => (b.purchases ?? 0) - (a.purchases ?? 0));
      setShopGroupProducts(sgList);
      setShopGroupVisibleCount(relatedStripInitialVisible(sgList.length));
    } catch (error) {
      console.error('Error fetching related products:', error);
      setRelatedProducts([]);
      setShopGroupProducts([]);
      setShopGroupVisibleCount(relatedStripInitialVisible(0));
    } finally {
      setLoading(false);
    }
  }, [
    currentProduct.id,
    currentProduct.shop_id,
    currentProduct.shop_name,
    currentProduct.pro_lower_price,
    currentProduct.pro_high_price,
    relatedTab,
  ]);

  useEffect(() => {
    fetchRelatedProducts();
  }, [fetchRelatedProducts]);

  if (loading) {
    const showShopGroupSkeleton = relatedTab === 'bestselling' && !!shopNameFilter;
    return (
      <div className="border-t border-gray-200 pt-5">
        {showShopGroupSkeleton && (
          <div className="mb-8">
            <div className="h-6 bg-gray-200 rounded w-72 mb-3 animate-pulse max-w-full" />
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
              {[...Array(5)].map((_, index) => (
                <div key={index} className="animate-pulse">
                  <div className="aspect-square bg-gray-200 rounded-lg mb-2"></div>
                  <div className="h-4 bg-gray-200 rounded mb-1"></div>
                  <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                </div>
              ))}
            </div>
            <div className="mt-4 flex w-full justify-between gap-4 lg:justify-center">
              <div className="h-9 w-24 rounded bg-gray-100 animate-pulse" />
              <div className="h-9 w-28 rounded bg-gray-200 animate-pulse" />
            </div>
          </div>
        )}
        <h3 className="text-lg font-bold text-gray-900 mb-3">{title}</h3>
        {relatedTab === 'bestselling' ? (
          <>
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
              {[...Array(5)].map((_, index) => (
                <div key={index} className="animate-pulse">
                  <div className="aspect-square bg-gray-200 rounded-lg mb-2"></div>
                  <div className="h-4 bg-gray-200 rounded mb-1"></div>
                  <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                </div>
              ))}
            </div>
            <div className="mt-4 flex w-full justify-between gap-4 lg:justify-center">
              <div className="h-9 w-24 rounded bg-gray-100 animate-pulse" />
              <div className="h-9 w-28 rounded bg-gray-200 animate-pulse" />
            </div>
          </>
        ) : (
          <div className="grid gap-3 grid-cols-2 md:grid-cols-4">
            {[...Array(4)].map((_, index) => (
              <div key={index} className="animate-pulse">
                <div className="aspect-square bg-gray-200 rounded-lg mb-2"></div>
                <div className="h-4 bg-gray-200 rounded mb-1"></div>
                <div className="h-4 bg-gray-200 rounded w-3/4"></div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  const plan = buildFetchPlan(currentProduct, relatedTab);
  if (!plan.ok) {
    return (
      <div className="border-t border-gray-200 pt-5">
        <h3 className="text-base font-bold text-gray-900 mb-2 uppercase">{title}</h3>
        <p className="text-sm text-gray-500">{emptyHint(relatedTab)}</p>
      </div>
    );
  }

  const showShopGroupBlock =
    relatedTab === 'bestselling' && !!shopNameFilter && shopGroupProducts.length > 0;

  if (relatedProducts.length === 0 && !showShopGroupBlock) {
    return (
      <div className="border-t border-gray-200 pt-5">
        <h3 className="text-base font-bold text-gray-900 mb-2 uppercase">{title}</h3>
        <p className="text-sm text-gray-500">Không có sản phẩm khác trong nhóm này.</p>
      </div>
    );
  }

  const visibleProducts = relatedProducts.slice(0, visibleCount);
  const canLoadMore = visibleCount < relatedProducts.length;
  const canShowAll = relatedProducts.length > 0 && visibleCount < relatedProducts.length;

  const handleLoadMore = () => {
    const step = relatedTab === 'bestselling' ? relatedStripStep() : 5;
    setVisibleCount((prev) => Math.min(prev + step, relatedProducts.length));
  };

  const handleShowAll = async () => {
    if (visibleCount >= relatedProducts.length) return;
    try {
      setShowAllLoading(true);
      const p = buildFetchPlan(currentProduct, relatedTab);
      if (!p.ok) return;
      const response = await apiClient.getProducts({
        ...p.params,
        limit: Math.min(500, 1000),
      });
      let list = (response.products || []).filter((x) => x.id !== currentProduct.id);
      if (p.sortPurchasesDesc) {
        list = [...list].sort((a, b) => (b.purchases ?? 0) - (a.purchases ?? 0));
      }
      setRelatedProducts(list);
      setVisibleCount(list.length);
    } catch (error) {
      console.error('Error fetching all related products:', error);
      setVisibleCount(relatedProducts.length);
    } finally {
      setShowAllLoading(false);
    }
  };

  const isBestselling = relatedTab === 'bestselling';
  const gridClassName = isBestselling
    ? BESTSELLING_GRID_CLASS
    : 'grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4';

  const imageSizes = isBestselling
    ? BESTSELLING_IMAGE_SIZES
    : '(min-width: 1024px) 20vw, (min-width: 640px) 25vw, 50vw';

  const shopGroupVisibleProducts = shopGroupProducts.slice(0, shopGroupVisibleCount);
  const shopGroupCanLoadMore = shopGroupVisibleCount < shopGroupProducts.length;
  const shopGroupCanShowAll =
    shopGroupProducts.length > 0 && shopGroupVisibleCount < shopGroupProducts.length;

  const handleShopGroupLoadMore = () => {
    const step = relatedStripStep();
    setShopGroupVisibleCount((prev) => Math.min(prev + step, shopGroupProducts.length));
  };

  const handleShopGroupShowAll = async () => {
    if (shopGroupVisibleCount >= shopGroupProducts.length) return;
    const shopName = excelCell(currentProduct.shop_name);
    if (!shopName) return;
    try {
      setShopGroupShowAllLoading(true);
      const response = await apiClient.getProducts({
        limit: Math.min(500, 1000),
        is_active: true,
        shop_name: shopName,
      });
      let list = (response.products || []).filter((x) => x.id !== currentProduct.id);
      list = [...list].sort((a, b) => (b.purchases ?? 0) - (a.purchases ?? 0));
      setShopGroupProducts(list);
      setShopGroupVisibleCount(list.length);
    } catch (error) {
      console.error('Error fetching shop group products:', error);
      setShopGroupVisibleCount(shopGroupProducts.length);
    } finally {
      setShopGroupShowAllLoading(false);
    }
  };

  const productGrid = (
    <div className={gridClassName}>
      {visibleProducts.map((product) => (
        <ProductRelatedCard key={product.id} product={product} imageSizes={imageSizes} />
      ))}
    </div>
  );

  const actionsRow =
    (canLoadMore || canShowAll) ? (
      <div
        className={`flex items-center gap-4 ${
          isBestselling
            ? 'mt-4 w-full justify-between lg:w-auto lg:justify-center lg:flex-wrap'
            : 'justify-center mt-4'
        }`}
      >
        {canLoadMore && (
          <button
            type="button"
            onClick={handleLoadMore}
            className="inline-flex shrink-0 items-center justify-center gap-2 text-sm text-gray-700 hover:text-[#ea580c]"
          >
            <span className="inline-flex items-center justify-center w-7 h-7 rounded-full border border-gray-300">
              ↻
            </span>
            Xem thêm
          </button>
        )}
        {canShowAll &&
          (fullListingHref ? (
            <Link
              href={fullListingHref}
              className="inline-flex shrink-0 items-center justify-center px-4 py-2 bg-[#ea580c] text-white rounded-lg text-sm font-medium hover:bg-orange-600"
            >
              Xem tất cả
            </Link>
          ) : (
            <button
              type="button"
              onClick={handleShowAll}
              disabled={showAllLoading}
              className="shrink-0 px-4 py-2 bg-[#ea580c] text-white rounded-lg text-sm font-medium disabled:opacity-60"
            >
              {showAllLoading ? 'Đang tải...' : 'Xem tất cả'}
            </button>
          ))}
      </div>
    ) : null;

  const shopGroupGrid = (
    <div className={BESTSELLING_GRID_CLASS}>
      {shopGroupVisibleProducts.map((product) => (
        <ProductRelatedCard key={product.id} product={product} imageSizes={BESTSELLING_IMAGE_SIZES} />
      ))}
    </div>
  );

  const shopGroupActionsRow =
    shopGroupCanLoadMore || shopGroupCanShowAll ? (
      <div className="flex items-center gap-4 mt-4 w-full justify-between lg:w-auto lg:justify-center lg:flex-wrap">
        {shopGroupCanLoadMore && (
          <button
            type="button"
            onClick={handleShopGroupLoadMore}
            className="inline-flex shrink-0 items-center justify-center gap-2 text-sm text-gray-700 hover:text-[#ea580c]"
          >
            <span className="inline-flex items-center justify-center w-7 h-7 rounded-full border border-gray-300">
              ↻
            </span>
            Xem thêm
          </button>
        )}
        {shopGroupCanShowAll &&
          (sameShopGroupHref ? (
            <Link
              href={sameShopGroupHref}
              className="inline-flex shrink-0 items-center justify-center px-4 py-2 bg-[#ea580c] text-white rounded-lg text-sm font-medium hover:bg-orange-600"
            >
              Xem tất cả
            </Link>
          ) : (
            <button
              type="button"
              onClick={handleShopGroupShowAll}
              disabled={shopGroupShowAllLoading}
              className="shrink-0 px-4 py-2 bg-[#ea580c] text-white rounded-lg text-sm font-medium disabled:opacity-60"
            >
              {shopGroupShowAllLoading ? 'Đang tải...' : 'Xem tất cả'}
            </button>
          ))}
      </div>
    ) : null;

  return (
    <div className="border-t border-gray-200 pt-5">
      {showShopGroupBlock && (
        <section className="mb-8" aria-label="Nhóm sản phẩm cùng shop">
          <h3 className="text-base font-bold text-gray-900 mb-3 uppercase">Nhóm sản phẩm cùng shop</h3>
          {shopGroupActionsRow ? (
            <>
              {shopGroupGrid}
              {shopGroupActionsRow}
            </>
          ) : (
            shopGroupGrid
          )}
        </section>
      )}

      {relatedProducts.length > 0 ? (
        <>
          <h3 className="text-base font-bold text-gray-900 mb-3 uppercase">{title}</h3>

          {isBestselling ? (
            actionsRow ? (
              <>
                {productGrid}
                {actionsRow}
              </>
            ) : (
              productGrid
            )
          ) : (
            <>
              {productGrid}
              {actionsRow}
            </>
          )}
        </>
      ) : relatedTab === 'bestselling' && showShopGroupBlock ? (
        <>
          <h3 className="text-base font-bold text-gray-900 mb-2 uppercase">{title}</h3>
          <p className="text-sm text-gray-500">
            Không có sản phẩm bán chạy khác theo shop_id trong nhóm này.
          </p>
        </>
      ) : null}
    </div>
  );
}
