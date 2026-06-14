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
  sidebarProducts: Product[];
};

const SIDEBAR_VISIBLE_COUNT = 8;

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

function relatedFetchCacheKey(productId: number, tab: ProductRelatedTabId): string {
  return `${productId}:${tab}`;
}

const inflightRelatedFetches = new Map<string, Promise<RelatedFetchSnapshot>>();
const relatedResultsCache = new Map<string, RelatedFetchSnapshot>();
const sidebarByProductId = new Map<number, Product[]>();

function applySidebarCache(productId: number, sidebarProducts: Product[]): void {
  if (sidebarProducts.length > 0) {
    sidebarByProductId.set(productId, sidebarProducts);
  }
}

/** Sidebar desktop — dùng payload đã gom từ GET /pdp-related (không gọi GET /products riêng). */
export function getCachedPdpSidebarProducts(productId: number): Product[] | null {
  const direct = sidebarByProductId.get(productId);
  if (direct && direct.length > 0) return direct;
  for (const tab of ['bestselling', 'same_price', 'lower_price', 'higher_price'] as const) {
    const snap = relatedResultsCache.get(relatedFetchCacheKey(productId, tab));
    if (snap?.sidebarProducts?.length) return snap.sidebarProducts;
  }
  return null;
}

export function pickRandomSidebarProducts(
  pool: Product[],
  count = SIDEBAR_VISIBLE_COUNT
): Product[] {
  const arr = [...pool];
  for (let i = arr.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr.slice(0, count);
}

export function getCachedRelatedProductsSnapshot(
  currentProduct: Product,
  relatedTab: ProductRelatedTabId
): RelatedFetchSnapshot | null {
  return relatedResultsCache.get(relatedFetchCacheKey(currentProduct.id, relatedTab)) ?? null;
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
  const key = relatedFetchCacheKey(currentProduct.id, relatedTab);
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
    const res = await apiClient.getPdpRelatedProducts(
      currentProduct.id,
      relatedTab,
      RELATED_PDP_FETCH_LIMIT
    );
    const snapshot: RelatedFetchSnapshot = {
      relatedProducts: res.related_products ?? [],
      shopGroupProducts: res.shop_group_products ?? [],
      sidebarProducts: res.sidebar_products ?? [],
    };
    applySidebarCache(currentProduct.id, snapshot.sidebarProducts);
    relatedResultsCache.set(key, snapshot);
    onPartial?.(snapshot);
    return snapshot;
  })().finally(() => {
    inflightRelatedFetches.delete(key);
  });

  inflightRelatedFetches.set(key, batch);
  return batch;
}
