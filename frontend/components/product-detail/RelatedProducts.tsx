// frontend/components/product-detail/RelatedProducts.tsx
'use client';

import { useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import { cdnUrl } from '@/lib/cdn-url';
import Image from 'next/image';
import Link from 'next/link';
import ProductPdpLink from '@/components/ProductPdpLink';
import Button from '@/components/ui/Button';
import LoadingLink from '@/components/ui/LoadingLink';
import type { Product, ProductSearchParams } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { formatPrice, getProductMainImage } from '@/lib/utils';
import {
  parseRelatedTabFromSearch,
  filtersFromProduct,
  buildHomeListingHref,
  type ProductRelatedTabId,
} from '@/lib/product-related-tabs';
import {
  buildRelatedFetchPlan,
  getCachedRelatedProductsSnapshot,
  loadRelatedProductsSnapshot,
  productSearchParamsFromChineseShopCat2,
} from '@/lib/related-products-pdp-fetch';
import { productPdpHref } from '@/lib/product-path-slug';
import { applyBirthdayDiscount } from '@/lib/birthday-discount';
import { useBirthdayDiscount } from '@/lib/use-birthday-discount';
import { BirthdayPromoImageBadge, BirthdayPromoPriceCakeIcon } from '@/components/BirthdayPromoProductMarkers';
import ProductCardClearanceMeta from '@/components/ProductCardClearanceMeta';

const RELATED_LIST_BASE: Pick<ProductSearchParams, 'skip_total' | 'is_active'> = {
  skip_total: true,
  is_active: true,
};

type PdpStripLayout = 'mobile' | 'desktop';

interface RelatedProductsProps {
  currentProduct: Product;
  /** Khớp khung PDP: mobile luôn 2 ô / desktop luôn 5 ô. */
  layout?: PdpStripLayout;
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
  const href = productPdpHref(product.slug, product.product_id) ?? `/products/${product.id}`;
  const birthdayDiscount = useBirthdayDiscount();
  const displayPrice = birthdayDiscount.active
    ? applyBirthdayDiscount(product.price || 0, birthdayDiscount.percent)
    : product.price || 0;
  return (
    <ProductPdpLink
      href={href}
      className="group block bg-white rounded-lg border border-gray-200 overflow-hidden hover:shadow-md transition-all"
    >
      <div className="aspect-square bg-gray-100 overflow-hidden relative">
        <Image
          src={getProductMainImage(product)}
          alt={product.name}
          fill
          sizes={imageSizes}
          loading="lazy"
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
    </ProductPdpLink>
  );
}

function stripInitialVisible(len: number, layout: PdpStripLayout): number {
  return Math.min(layout === 'desktop' ? 5 : 2, len);
}

function stripStep(layout: PdpStripLayout): number {
  return layout === 'desktop' ? 5 : 2;
}

export default function RelatedProducts({
  currentProduct,
  layout = 'mobile',
}: RelatedProductsProps) {
  const gridClassName = layout === 'desktop' ? 'grid grid-cols-5 gap-4' : 'grid grid-cols-2 gap-4';
  const imageSizes = layout === 'desktop' ? '20vw' : '50vw';
  const initialVisible = layout === 'desktop' ? 5 : 2;
  const actionsRowClass =
    layout === 'desktop'
      ? 'mt-4 flex w-full items-center justify-center gap-4'
      : 'mt-4 flex w-full items-center justify-between gap-4';
  const searchParams = useSearchParams();
  const relatedTab = parseRelatedTabFromSearch(searchParams.get('rt'));

  const title = useMemo(() => sectionTitle(relatedTab), [relatedTab]);
  const fullListingHref = useMemo(() => {
    const f = filtersFromProduct(currentProduct);
    return buildHomeListingHref(relatedTab, f);
  }, [relatedTab, currentProduct]);

  const [relatedProducts, setRelatedProducts] = useState<Product[]>([]);
  const [shopGroupProducts, setShopGroupProducts] = useState<Product[]>([]);
  const [loadingRelated, setLoadingRelated] = useState(true);
  const [loadingShopGroup, setLoadingShopGroup] = useState(true);
  const [visibleCount, setVisibleCount] = useState(initialVisible);
  const [showAllLoading, setShowAllLoading] = useState(false);

  const [shopGroupVisibleCount, setShopGroupVisibleCount] = useState(initialVisible);
  const [shopGroupShowAllLoading, setShopGroupShowAllLoading] = useState(false);

  const chineseShopCat2GroupParams = useMemo(
    () => productSearchParamsFromChineseShopCat2(currentProduct),
    [currentProduct]
  );

  const sameChineseShopCat2GroupHref = useMemo(() => {
    return buildHomeListingHref('same_price', filtersFromProduct(currentProduct));
  }, [currentProduct]);

  useEffect(() => {
    const ac = new AbortController();
    const plan = buildRelatedFetchPlan(currentProduct, relatedTab);
    const shopOnlyBestselling =
      relatedTab === 'bestselling' && !!productSearchParamsFromChineseShopCat2(currentProduct);

    const applySnapshot = (list: Product[], sgList: Product[]) => {
      setRelatedProducts(list);
      setVisibleCount(stripInitialVisible(list.length, layout));
      setShopGroupProducts(sgList);
      setShopGroupVisibleCount(stripInitialVisible(sgList.length, layout));
    };

    const cached = getCachedRelatedProductsSnapshot(currentProduct, relatedTab);
    if (cached) {
      applySnapshot(cached.relatedProducts, cached.shopGroupProducts);
      setLoadingRelated(false);
      setLoadingShopGroup(false);
      return () => {
        ac.abort();
      };
    }

    setLoadingRelated(!!plan.ok);
    setLoadingShopGroup(!!shopOnlyBestselling);

    if (!plan.ok && !shopOnlyBestselling) {
      applySnapshot([], []);
      setLoadingRelated(false);
      setLoadingShopGroup(false);
      return () => {
        ac.abort();
      };
    }

    void loadRelatedProductsSnapshot(currentProduct, relatedTab, (partial) => {
      if (ac.signal.aborted) return;
      applySnapshot(partial.relatedProducts, partial.shopGroupProducts);
      if (partial.shopGroupProducts.length > 0 || !shopOnlyBestselling) {
        setLoadingShopGroup(false);
      }
      if (partial.relatedProducts.length > 0 || !plan.ok) {
        setLoadingRelated(false);
      }
    })
      .then((final) => {
        if (ac.signal.aborted) return;
        applySnapshot(final.relatedProducts, final.shopGroupProducts);
      })
      .catch((error) => {
        console.error('Error fetching related products:', error);
        if (ac.signal.aborted) return;
        setRelatedProducts([]);
        setShopGroupProducts([]);
        setShopGroupVisibleCount(stripInitialVisible(0, layout));
      })
      .finally(() => {
        if (!ac.signal.aborted) {
          setLoadingRelated(false);
          setLoadingShopGroup(false);
        }
      });

    return () => {
      ac.abort();
    };
  }, [currentProduct, relatedTab, layout]);

  const plan = buildRelatedFetchPlan(currentProduct, relatedTab);
  const canShowShopGroupSection = relatedTab === 'bestselling' && !!chineseShopCat2GroupParams;
  const showShopGroupSkeleton = loadingShopGroup && canShowShopGroupSection;
  const showRelatedSkeleton = loadingRelated && plan.ok;

  const relatedSkeleton = (
    <>
      <div className={gridClassName}>
        {[...Array(initialVisible)].map((_, index) => (
          <div key={index} className="animate-pulse">
            <div className="aspect-square bg-gray-200 rounded-lg mb-2"></div>
            <div className="h-4 bg-gray-200 rounded mb-1"></div>
            <div className="h-4 bg-gray-200 rounded w-3/4"></div>
          </div>
        ))}
      </div>
      <div className={actionsRowClass}>
        <div className="h-9 w-24 rounded bg-gray-100 animate-pulse" />
        <div className="h-9 w-28 rounded bg-gray-200 animate-pulse" />
      </div>
    </>
  );

  if (showShopGroupSkeleton && showRelatedSkeleton && !canShowShopGroupSection) {
    return (
      <div className="border-t border-gray-200 pt-5">
        <h3 className="text-lg font-bold text-gray-900 mb-3">{title}</h3>
        {relatedSkeleton}
      </div>
    );
  }

  if (showShopGroupSkeleton && showRelatedSkeleton) {
    return (
      <div className="border-t border-gray-200 pt-5">
        <div className="mb-8">
          <div className="h-6 bg-gray-200 rounded w-72 mb-3 animate-pulse max-w-full" />
          <div className={gridClassName}>
            {[...Array(initialVisible)].map((_, index) => (
              <div key={index} className="animate-pulse">
                <div className="aspect-square bg-gray-200 rounded-lg mb-2"></div>
                <div className="h-4 bg-gray-200 rounded mb-1"></div>
                <div className="h-4 bg-gray-200 rounded w-3/4"></div>
              </div>
            ))}
          </div>
          <div className={actionsRowClass}>
            <div className="h-9 w-24 rounded bg-gray-100 animate-pulse" />
            <div className="h-9 w-28 rounded bg-gray-200 animate-pulse" />
          </div>
        </div>
        <h3 className="text-lg font-bold text-gray-900 mb-3">{title}</h3>
        {relatedSkeleton}
      </div>
    );
  }

  const hasShopGroupProducts = shopGroupProducts.length > 0;

  if (!loadingRelated && !loadingShopGroup && !plan.ok && !canShowShopGroupSection) {
    return (
      <div className="border-t border-gray-200 pt-5">
        <h3 className="text-base font-bold text-gray-900 mb-2 uppercase">{title}</h3>
        <p className="text-sm text-gray-500">{emptyHint(relatedTab)}</p>
      </div>
    );
  }

  if (
    !loadingRelated &&
    plan.ok &&
    relatedProducts.length === 0 &&
    !canShowShopGroupSection
  ) {
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
    setVisibleCount((prev) => Math.min(prev + stripStep(layout), relatedProducts.length));
  };

  const handleShowAll = async () => {
    if (visibleCount >= relatedProducts.length) return;
    try {
      setShowAllLoading(true);
      const p = buildRelatedFetchPlan(currentProduct, relatedTab);
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

  const shopGroupVisibleProducts = shopGroupProducts.slice(0, shopGroupVisibleCount);
  const shopGroupCanLoadMore = shopGroupVisibleCount < shopGroupProducts.length;
  const shopGroupCanShowAll =
    shopGroupProducts.length > 0 && shopGroupVisibleCount < shopGroupProducts.length;

  const handleShopGroupLoadMore = () => {
    setShopGroupVisibleCount((prev) => Math.min(prev + stripStep(layout), shopGroupProducts.length));
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
      <div className={actionsRowClass}>
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
    <div className={gridClassName}>
      {shopGroupVisibleProducts.map((product) => (
        <ProductRelatedCard key={product.id} product={product} imageSizes={imageSizes} />
      ))}
    </div>
  );

  const shopGroupActionsRow =
    shopGroupCanLoadMore || shopGroupCanShowAll ? (
      <div className={actionsRowClass}>
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
          {showShopGroupSkeleton ? (
            <>
              <div className={gridClassName}>
                {[...Array(initialVisible)].map((_, index) => (
                  <div key={index} className="animate-pulse">
                    <div className="aspect-square bg-gray-200 rounded-lg mb-2"></div>
                    <div className="h-4 bg-gray-200 rounded mb-1"></div>
                    <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                  </div>
                ))}
              </div>
              <div className={actionsRowClass}>
                <div className="h-9 w-24 rounded bg-gray-100 animate-pulse" />
                <div className="h-9 w-28 rounded bg-gray-200 animate-pulse" />
              </div>
            </>
          ) : hasShopGroupProducts ? (
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

      {showRelatedSkeleton ? (
        <>
          <h3 className="text-base font-bold text-gray-900 mb-3 uppercase">{title}</h3>
          {relatedSkeleton}
        </>
      ) : relatedProducts.length > 0 ? (
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
      ) : !loadingRelated && relatedTab === 'bestselling' ? (
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
