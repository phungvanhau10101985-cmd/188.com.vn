// frontend/components/product-detail/RelatedProducts.tsx
'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
import { useNearViewport } from '@/lib/use-near-viewport';
import { useSearchParams } from 'next/navigation';
import { cdnUrl } from '@/lib/cdn-url';
import Image from 'next/image';
import Link from 'next/link';
import Button from '@/components/ui/Button';
import LoadingLink from '@/components/ui/LoadingLink';
import type { Product, ProductSearchParams } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { formatPrice, getProductMainImage } from '@/lib/utils';
import {
  parseRelatedTabFromSearch,
  excelCell,
  filtersFromProduct,
  buildHomeListingHref,
  listingParamsForPriceSiblingTab,
  listingParamsSameChineseShopCat2,
  type ProductRelatedTabId,
} from '@/lib/product-related-tabs';
import { productPathSlugFromApi } from '@/lib/product-path-slug';
import { applyBirthdayDiscount } from '@/lib/birthday-discount';
import { useBirthdayDiscount } from '@/lib/use-birthday-discount';
import { BirthdayPromoImageBadge, BirthdayPromoPriceCakeIcon } from '@/components/BirthdayPromoProductMarkers';
import ProductCardClearanceMeta from '@/components/ProductCardClearanceMeta';

/** Lấy đủ cho lưới 5 + «Xem thêm»; tránh limit=120 + COUNT(*) trên PDP. */
const RELATED_PDP_FETCH_LIMIT = 36;

const RELATED_LIST_BASE: Pick<ProductSearchParams, 'skip_total' | 'is_active'> = {
  skip_total: true,
  is_active: true,
};

interface RelatedProductsProps {
  currentProduct: Product;
}

function sectionTitle(tab: ProductRelatedTabId): string {
  switch (tab) {
    case 'bestselling':
      return 'Sản phẩm bán chạy tương tự';
    case 'same_price':
      return 'Sản phẩm cùng danh mục (cấp 2) — cùng shop Trung Quốc (AM / shop_name_chinese)';
    case 'lower_price':
      return 'Sản phẩm cùng danh mục (cấp 2) — giá thấp hơn (trong 300k)';
    case 'higher_price':
      return 'Sản phẩm cùng danh mục (cấp 2) — giá cao hơn (trong 300k)';
    default:
      return 'Sản phẩm liên quan';
  }
}

function emptyHint(tab: ProductRelatedTabId): string {
  switch (tab) {
    case 'bestselling':
      return 'Sản phẩm chưa có Style (AF) và danh mục cấp 2 — không lọc được nhóm bán chạy.';
    case 'same_price':
      return 'Thiếu danh mục cấp 2 hoặc tên shop Trung Quốc (shop_name_chinese) — không lọc được nhóm này.';
    case 'lower_price':
      return 'Thiếu danh mục cấp 2, giá hợp lệ hoặc không có khoảng giá thấp hơn — không lọc được.';
    case 'higher_price':
      return 'Thiếu danh mục cấp 2 hoặc giá hợp lệ — không lọc được nhóm giá cao hơn.';
    default:
      return 'Không có dữ liệu để hiển thị.';
  }
}

function ProductRelatedCard({ product, imageSizes }: { product: Product; imageSizes: string }) {
  const seg = productPathSlugFromApi(product.slug, product.product_id) || String(product.id);
  const birthdayDiscount = useBirthdayDiscount();
  const displayPrice = birthdayDiscount.active
    ? applyBirthdayDiscount(product.price || 0, birthdayDiscount.percent)
    : product.price || 0;
  return (
    <Link
      href={`/products/${seg}`}
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
        <BirthdayPromoImageBadge active={birthdayDiscount.active} percent={birthdayDiscount.percent} />
      </div>

      <div className="p-2">
        <h4 className="font-medium text-gray-900 line-clamp-2 text-xs leading-tight mb-1 group-hover:text-[#ea580c] transition-colors">
          {product.name}
        </h4>

        <div className="flex flex-wrap items-baseline gap-x-1 gap-y-0">
          <span className="text-sm font-bold text-[#ea580c]">{formatPrice(displayPrice)}</span>
          <BirthdayPromoPriceCakeIcon active={birthdayDiscount.active} percent={birthdayDiscount.percent} />
          {birthdayDiscount.active && displayPrice < (product.price || 0) ? (
            <span className="text-xs text-gray-500 line-through decoration-1 decoration-gray-400">{formatPrice(product.price)}</span>
          ) : product.original_price && product.original_price > product.price ? (
            <span className="text-xs text-gray-500 line-through decoration-1 decoration-gray-400">{formatPrice(product.original_price)}</span>
          ) : null}
        </div>

        <ProductCardClearanceMeta product={product} compact className="mt-1" />

        {typeof product.purchases === 'number' && product.purchases > 0 && (
          <div className="mt-1 text-[10px] text-gray-500">Đã bán {product.purchases}</div>
        )}
      </div>
    </Link>
  );
}

type FetchPlan =
  | {
      ok: true;
      params: ProductSearchParams;
      sortPurchasesDesc?: boolean;
    }
  | { ok: false };

function productSearchParamsFromChineseShopCat2(product: Product): ProductSearchParams | null {
  const sibling = listingParamsSameChineseShopCat2(product);
  if (!sibling) return null;
  const { category, subcategory, ...rest } = sibling;
  return {
    ...rest,
    ...(category ? { category } : {}),
    ...(subcategory ? { subcategory } : {}),
  };
}

function buildFetchPlan(product: Product, tab: ProductRelatedTabId): FetchPlan {
  const base: ProductSearchParams = { ...RELATED_LIST_BASE, limit: RELATED_PDP_FETCH_LIMIT };

  switch (tab) {
    case 'bestselling': {
      const st = excelCell(product.style);
      if (st) {
        return {
          ok: true,
          params: { ...base, style: st, sort: 'purchases_desc' },
          sortPurchasesDesc: true,
        };
      }
      const sub2 = excelCell(product.subcategory);
      if (sub2) {
        const cat = excelCell(product.category);
        return {
          ok: true,
          params: {
            ...base,
            ...(cat ? { category: cat } : {}),
            subcategory: sub2,
            sort: 'purchases_desc',
          },
          sortPurchasesDesc: true,
        };
      }
      return { ok: false };
    }
    case 'same_price': {
      const sibling = listingParamsSameChineseShopCat2(product);
      if (!sibling) return { ok: false };
      const { category, subcategory, ...rest } = sibling;
      return {
        ok: true,
        params: {
          ...base,
          ...rest,
          ...(category ? { category } : {}),
          ...(subcategory ? { subcategory } : {}),
        },
      };
    }
    case 'lower_price': {
      const sibling = listingParamsForPriceSiblingTab('lower_price', product);
      if (!sibling) return { ok: false };
      const { category, subcategory, ...rest } = sibling;
      return {
        ok: true,
        params: {
          ...base,
          ...rest,
          ...(category ? { category } : {}),
          ...(subcategory ? { subcategory } : {}),
        },
      };
    }
    case 'higher_price': {
      const sibling = listingParamsForPriceSiblingTab('higher_price', product);
      if (!sibling) return { ok: false };
      const { category, subcategory, ...rest } = sibling;
      return {
        ok: true,
        params: {
          ...base,
          ...rest,
          ...(category ? { category } : {}),
          ...(subcategory ? { subcategory } : {}),
        },
      };
    }
    default:
      return { ok: false };
  }
}

/** Hai khối RelatedProducts trên cùng trang (tabs + cuối trang) chia sẻ một request — giảm TBT và gánh mạng. */
type RelatedFetchSnapshot = {
  relatedProducts: Product[];
  shopGroupProducts: Product[];
};

function relatedFetchDedupeKey(productId: number, tab: ProductRelatedTabId, plan: Extract<FetchPlan, { ok: true }>): string {
  return `${productId}:${tab}:${plan.sortPurchasesDesc ? '1' : '0'}:${JSON.stringify(plan.params)}`;
}

const inflightRelatedFetches = new Map<string, Promise<RelatedFetchSnapshot>>();

/** Tab bán chạy: lưới phụ cùng danh mục cấp 2 + shop Trung Quốc (`shop_name_chinese`). */
async function loadChineseShopGroupSnapshot(currentProduct: Product): Promise<Product[]> {
  const parallelParams = productSearchParamsFromChineseShopCat2(currentProduct);
  if (!parallelParams) return [];
  const shopGroupResponse = await apiClient.getProducts({
    ...RELATED_LIST_BASE,
    limit: RELATED_PDP_FETCH_LIMIT,
    sort: 'purchases_desc',
    ...parallelParams,
  });
  return (shopGroupResponse.products || []).filter((p) => p.id !== currentProduct.id);
}

async function loadRelatedProductsSnapshot(
  currentProduct: Product,
  relatedTab: ProductRelatedTabId
): Promise<RelatedFetchSnapshot> {
  const plan = buildFetchPlan(currentProduct, relatedTab);
  if (!plan.ok) {
    return { relatedProducts: [], shopGroupProducts: [] };
  }

  const key = relatedFetchDedupeKey(currentProduct.id, relatedTab, plan);
  let batch = inflightRelatedFetches.get(key);
  if (!batch) {
    batch = (async () => {
      const shopPromise =
        relatedTab === 'bestselling' ? loadChineseShopGroupSnapshot(currentProduct) : Promise.resolve([]);

      const [response, sgList] = await Promise.all([
        apiClient.getProducts(plan.params),
        shopPromise,
      ]);

      const list = (response.products || []).filter((p) => p.id !== currentProduct.id);

      return { relatedProducts: list, shopGroupProducts: sgList };
    })().finally(() => {
      inflightRelatedFetches.delete(key);
    });
    inflightRelatedFetches.set(key, batch);
  }

  return batch;
}

const BESTSELLING_GRID_CLASS = 'grid grid-cols-2 lg:grid-cols-5 gap-4';
const BESTSELLING_IMAGE_SIZES = '(max-width: 1023px) 50vw, (min-width: 1024px) 20vw';

/** Desktop lg: 5 ô / +5; mobile: 2 ô / +2 — dùng cho «bán chạy» và lưới phụ cùng shop TQ + cấp 2. */
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
  const containerRef = useRef<HTMLDivElement>(null);
  const isNear = useNearViewport(containerRef);
  const searchParams = useSearchParams();
  const relatedTab = parseRelatedTabFromSearch(searchParams.get('rt'));

  const title = useMemo(() => sectionTitle(relatedTab), [relatedTab]);
  const fullListingHref = useMemo(() => {
    const f = filtersFromProduct(currentProduct);
    return buildHomeListingHref(relatedTab, f);
  }, [relatedTab, currentProduct]);

  const [relatedProducts, setRelatedProducts] = useState<Product[]>([]);
  const [shopGroupProducts, setShopGroupProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [visibleCount, setVisibleCount] = useState(5);
  const [showAllLoading, setShowAllLoading] = useState(false);

  const [shopGroupVisibleCount, setShopGroupVisibleCount] = useState(2);
  const [shopGroupShowAllLoading, setShopGroupShowAllLoading] = useState(false);

  const chineseShopCat2GroupParams = useMemo(
    () => productSearchParamsFromChineseShopCat2(currentProduct),
    [currentProduct]
  );

  const sameChineseShopCat2GroupHref = useMemo(() => {
    return buildHomeListingHref('same_price', filtersFromProduct(currentProduct));
  }, [currentProduct]);

  useEffect(() => {
    if (!isNear) return;

    const ac = new AbortController();

    const applySnapshot = (list: Product[], sgList: Product[]) => {
      setRelatedProducts(list);
      setVisibleCount(relatedTab === 'bestselling' ? relatedStripInitialVisible(list.length) : 5);
      setShopGroupProducts(sgList);
      setShopGroupVisibleCount(relatedStripInitialVisible(sgList.length));
    };

    const runFetch = async () => {
      const plan = buildFetchPlan(currentProduct, relatedTab);
      const shopOnlyBestselling =
        relatedTab === 'bestselling' && !!productSearchParamsFromChineseShopCat2(currentProduct);

      if (!plan.ok) {
        if (shopOnlyBestselling) {
          try {
            setLoading(true);
            const sgList = await loadChineseShopGroupSnapshot(currentProduct);
            if (ac.signal.aborted) return;
            applySnapshot([], sgList);
          } catch (error) {
            console.error('Error fetching related products:', error);
            if (ac.signal.aborted) return;
            setRelatedProducts([]);
            setShopGroupProducts([]);
            setShopGroupVisibleCount(relatedStripInitialVisible(0));
          } finally {
            if (!ac.signal.aborted) setLoading(false);
          }
          return;
        }
        if (ac.signal.aborted) return;
        setRelatedProducts([]);
        setShopGroupProducts([]);
        setShopGroupVisibleCount(relatedStripInitialVisible(0));
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        const { relatedProducts: list, shopGroupProducts: sgList } =
          await loadRelatedProductsSnapshot(currentProduct, relatedTab);
        if (ac.signal.aborted) return;
        applySnapshot(list, sgList);
      } catch (error) {
        console.error('Error fetching related products:', error);
        if (ac.signal.aborted) return;
        setRelatedProducts([]);
        setShopGroupProducts([]);
        setShopGroupVisibleCount(relatedStripInitialVisible(0));
      } finally {
        if (!ac.signal.aborted) setLoading(false);
      }
    };

    void runFetch();

    return () => {
      ac.abort();
    };
  }, [isNear, currentProduct, relatedTab]);

  if (!isNear) {
    return (
      <div
        ref={containerRef}
        className="border-t border-gray-200 pt-5 min-h-[14rem]"
        aria-hidden="true"
      />
    );
  }

  if (loading) {
    const showShopGroupSkeleton = relatedTab === 'bestselling' && !!chineseShopCat2GroupParams;
    return (
      <div ref={containerRef} className="border-t border-gray-200 pt-5">
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
  const canShowShopGroupSection = relatedTab === 'bestselling' && !!chineseShopCat2GroupParams;
  const hasShopGroupProducts = shopGroupProducts.length > 0;

  if (!plan.ok && !canShowShopGroupSection) {
    return (
      <div className="border-t border-gray-200 pt-5">
        <h3 className="text-base font-bold text-gray-900 mb-2 uppercase">{title}</h3>
        <p className="text-sm text-gray-500">{emptyHint(relatedTab)}</p>
      </div>
    );
  }

  if (plan.ok && relatedProducts.length === 0 && !canShowShopGroupSection) {
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
        skip_total: false,
        limit: Math.min(120, 500),
        sort: p.sortPurchasesDesc ? 'purchases_desc' : p.params.sort,
      });
      const list = (response.products || []).filter((x) => x.id !== currentProduct.id);
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
    const extra = productSearchParamsFromChineseShopCat2(currentProduct);
    if (!extra) return;
    try {
      setShopGroupShowAllLoading(true);
      const response = await apiClient.getProducts({
        ...RELATED_LIST_BASE,
        skip_total: false,
        limit: Math.min(120, 500),
        sort: 'purchases_desc',
        ...extra,
      });
      const list = (response.products || []).filter((x) => x.id !== currentProduct.id);
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
            <LoadingLink
              href={fullListingHref}
              className="inline-flex shrink-0 items-center justify-center px-4 py-2 bg-[#ea580c] text-white rounded-lg text-sm font-medium hover:bg-orange-600"
            >
              Xem tất cả
            </LoadingLink>
          ) : (
            <Button
              type="button"
              variant="primary"
              onClick={handleShowAll}
              loading={showAllLoading}
              className="shrink-0"
            >
              Xem tất cả
            </Button>
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
          (sameChineseShopCat2GroupHref ? (
            <LoadingLink
              href={sameChineseShopCat2GroupHref}
              className="inline-flex shrink-0 items-center justify-center px-4 py-2 bg-[#ea580c] text-white rounded-lg text-sm font-medium hover:bg-orange-600"
            >
              Xem tất cả
            </LoadingLink>
          ) : (
            <Button
              type="button"
              variant="primary"
              onClick={handleShopGroupShowAll}
              loading={shopGroupShowAllLoading}
              className="shrink-0"
            >
              Xem tất cả
            </Button>
          ))}
      </div>
    ) : null;

  return (
    <div className="border-t border-gray-200 pt-5">
      {canShowShopGroupSection && (
        <section className="mb-8" aria-label="Sản phẩm tương tự">
          <h3 className="text-base font-bold text-gray-900 mb-3 uppercase">
            Sản phẩm tương tự
          </h3>
          {hasShopGroupProducts ? (
            shopGroupActionsRow ? (
              <>
                {shopGroupGrid}
                {shopGroupActionsRow}
              </>
            ) : (
              shopGroupGrid
            )
          ) : (
            <p className="text-sm text-gray-500">
              Không có sản phẩm khác cùng danh mục cấp 2 và cùng shop Trung Quốc.
            </p>
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
      ) : relatedTab === 'bestselling' ? (
        <>
          <h3 className="text-base font-bold text-gray-900 mb-2 uppercase">{title}</h3>
          <p className="text-sm text-gray-500">
            {!plan.ok
              ? emptyHint(relatedTab)
              : 'Không có sản phẩm khác trong nhóm bán chạy này.'}
          </p>
        </>
      ) : null}
    </div>
  );
}
