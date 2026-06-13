import { apiClient } from '@/lib/api-client';
import type { Product, ProductSearchParams } from '@/types/api';
import {
  excelCell,
  listingParamsForPriceSiblingTab,
  listingParamsSameChineseShopCat2,
  type ProductRelatedTabId,
} from '@/lib/product-related-tabs';

/** Đủ cho vài lần «Xem thêm» (5/lần desktop); nhẹ hơn 36 trên PDP. */
export const RELATED_PDP_FETCH_LIMIT = 20;

const RELATED_LIST_BASE: Pick<ProductSearchParams, 'skip_total' | 'is_active'> = {
  skip_total: true,
  is_active: true,
};

export type RelatedFetchSnapshot = {
  relatedProducts: Product[];
  shopGroupProducts: Product[];
};

type FetchPlan =
  | {
      ok: true;
      params: ProductSearchParams;
      sortPurchasesDesc?: boolean;
    }
  | { ok: false };

export function productSearchParamsFromChineseShopCat2(product: Product): ProductSearchParams | null {
  const sibling = listingParamsSameChineseShopCat2(product);
  if (!sibling) return null;
  const { category, subcategory, ...rest } = sibling;
  return {
    ...rest,
    ...(category ? { category } : {}),
    ...(subcategory ? { subcategory } : {}),
  };
}

export function buildRelatedFetchPlan(product: Product, tab: ProductRelatedTabId): FetchPlan {
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

function relatedFetchCacheKey(
  productId: number,
  tab: ProductRelatedTabId,
  plan: Extract<FetchPlan, { ok: true }> | null,
  shopGroup: boolean
): string {
  const planPart = plan ? `${plan.sortPurchasesDesc ? '1' : '0'}:${JSON.stringify(plan.params)}` : 'none';
  return `${productId}:${tab}:${shopGroup ? 'shop' : 'main'}:${planPart}`;
}

function snapshotCacheKey(productId: number, tab: ProductRelatedTabId, plan: Extract<FetchPlan, { ok: true }>): string {
  return `${productId}:${tab}:${plan.sortPurchasesDesc ? '1' : '0'}:${JSON.stringify(plan.params)}`;
}

const inflightRelatedFetches = new Map<string, Promise<RelatedFetchSnapshot>>();
const relatedResultsCache = new Map<string, RelatedFetchSnapshot>();

function filterOutCurrent(products: Product[] | undefined, currentProduct: Product): Product[] {
  return (products || []).filter((p) => p.id !== currentProduct.id);
}

async function loadChineseShopGroupSnapshot(currentProduct: Product): Promise<Product[]> {
  const parallelParams = productSearchParamsFromChineseShopCat2(currentProduct);
  if (!parallelParams) return [];
  const shopGroupResponse = await apiClient.getProducts({
    ...RELATED_LIST_BASE,
    limit: RELATED_PDP_FETCH_LIMIT,
    sort: 'purchases_desc',
    ...parallelParams,
  });
  return filterOutCurrent(shopGroupResponse.products, currentProduct);
}

export function getCachedRelatedProductsSnapshot(
  currentProduct: Product,
  relatedTab: ProductRelatedTabId
): RelatedFetchSnapshot | null {
  const plan = buildRelatedFetchPlan(currentProduct, relatedTab);
  if (!plan.ok) {
    if (relatedTab === 'bestselling' && productSearchParamsFromChineseShopCat2(currentProduct)) {
      const shopKey = relatedFetchCacheKey(currentProduct.id, relatedTab, null, true);
      const shopOnly = relatedResultsCache.get(shopKey);
      return shopOnly ? { relatedProducts: [], shopGroupProducts: shopOnly.shopGroupProducts } : null;
    }
    return null;
  }
  return relatedResultsCache.get(snapshotCacheKey(currentProduct.id, relatedTab, plan)) ?? null;
}

/** Gọi sớm từ PDP — làm ấm cache trước khi user scroll tới khối SP liên quan. */
export function prefetchRelatedProductsForPdp(
  currentProduct: Product,
  relatedTab: ProductRelatedTabId = 'bestselling'
): void {
  if (!currentProduct?.id) return;
  void loadRelatedProductsSnapshot(currentProduct, relatedTab).catch(() => {});
}

export async function loadRelatedProductsSnapshot(
  currentProduct: Product,
  relatedTab: ProductRelatedTabId,
  onPartial?: (snapshot: RelatedFetchSnapshot) => void
): Promise<RelatedFetchSnapshot> {
  const plan = buildRelatedFetchPlan(currentProduct, relatedTab);
  const shopParams = relatedTab === 'bestselling' ? productSearchParamsFromChineseShopCat2(currentProduct) : null;

  if (!plan.ok) {
    if (shopParams) {
      const shopKey = relatedFetchCacheKey(currentProduct.id, relatedTab, null, true);
      const cachedShop = relatedResultsCache.get(shopKey);
      if (cachedShop) {
        onPartial?.(cachedShop);
        return cachedShop;
      }
      let inflight = inflightRelatedFetches.get(shopKey);
      if (!inflight) {
        inflight = (async () => {
          const sgList = await loadChineseShopGroupSnapshot(currentProduct);
          const snapshot = { relatedProducts: [] as Product[], shopGroupProducts: sgList };
          relatedResultsCache.set(shopKey, snapshot);
          return snapshot;
        })().finally(() => {
          inflightRelatedFetches.delete(shopKey);
        });
        inflightRelatedFetches.set(shopKey, inflight);
      }
      const result = await inflight;
      onPartial?.(result);
      return result;
    }
    return { relatedProducts: [], shopGroupProducts: [] };
  }

  const key = snapshotCacheKey(currentProduct.id, relatedTab, plan);
  const cached = relatedResultsCache.get(key);
  if (cached) {
    onPartial?.(cached);
    return cached;
  }

  let batch = inflightRelatedFetches.get(key);
  if (batch) {
    if (!onPartial) return batch;
    return batch.then((snapshot) => {
      onPartial(snapshot);
      return snapshot;
    });
  }
  batch = (async () => {
      let relatedProducts: Product[] = [];
      let shopGroupProducts: Product[] = [];

      const emit = () => {
        onPartial?.({ relatedProducts, shopGroupProducts });
      };

      const relatedPromise = apiClient.getProducts(plan.params).then((response) => {
        relatedProducts = filterOutCurrent(response.products, currentProduct);
        emit();
        return relatedProducts;
      });

      const shopPromise =
        relatedTab === 'bestselling' && shopParams
          ? loadChineseShopGroupSnapshot(currentProduct).then((sgList) => {
              shopGroupProducts = sgList;
              emit();
              return sgList;
            })
          : Promise.resolve([] as Product[]);

      await Promise.all([relatedPromise, shopPromise]);
      const snapshot = { relatedProducts, shopGroupProducts };
      relatedResultsCache.set(key, snapshot);
      return snapshot;
    })().finally(() => {
      inflightRelatedFetches.delete(key);
    });
  inflightRelatedFetches.set(key, batch);

  return batch;
}
