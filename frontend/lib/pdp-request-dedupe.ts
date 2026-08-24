import { apiClient } from '@/lib/api-client';
import type {
  PdpOutfitResponse,
  Product,
  ProductQuestionItem,
  SameAgeGenderCohortMode,
} from '@/types/api';

const outfitCache = new Map<string, PdpOutfitResponse>();
const outfitInflight = new Map<string, Promise<PdpOutfitResponse>>();

const questionsCache = new Map<string, ProductQuestionItem[]>();
const questionsInflight = new Map<string, Promise<ProductQuestionItem[]>>();

type AgeGenderSnap = { products: Product[]; cohort_mode: SameAgeGenderCohortMode };
const ageGenderCache = new Map<string, AgeGenderSnap>();
const ageGenderInflight = new Map<string, Promise<AgeGenderSnap>>();

const favoriteIdsCache = new Map<string, number[]>();
const favoriteIdsInflight = new Map<string, Promise<number[]>>();

const trackedOutfitViews = new Set<string>();

function inflightGet<K, V>(
  cache: Map<K, V>,
  inflight: Map<K, Promise<V>>,
  key: K,
  load: () => Promise<V>,
  force?: boolean,
): Promise<V> {
  if (!force) {
    const hit = cache.get(key);
    if (hit) return Promise.resolve(hit);
    const pending = inflight.get(key);
    if (pending) return pending;
  }
  const req = load()
    .then((value) => {
      cache.set(key, value);
      return value;
    })
    .finally(() => {
      inflight.delete(key);
    });
  inflight.set(key, req);
  return req;
}

export function loadPdpOutfitSuggestions(
  productId: number,
  limit: number,
  force = false,
): Promise<PdpOutfitResponse> {
  return inflightGet(outfitCache, outfitInflight, `${productId}:${limit}`, () =>
    apiClient.getPdpOutfitSuggestions(productId, { limit }),
    force,
  );
}

export function prefetchPdpOutfitSuggestions(productId: number, limit: number): void {
  if (!productId) return;
  void loadPdpOutfitSuggestions(productId, limit);
}

export function shouldTrackOutfitBlockView(productId: number, slot: string | null): boolean {
  const key = `${productId}:${slot ?? ''}`;
  if (trackedOutfitViews.has(key)) return false;
  trackedOutfitViews.add(key);
  return true;
}

function questionsCacheKey(productId: number, authKey: string): string {
  return `${productId}:${authKey}`;
}

export function loadPdpProductQuestions(
  productId: number,
  authKey = 'guest',
  force = false,
): Promise<ProductQuestionItem[]> {
  return inflightGet(
    questionsCache,
    questionsInflight,
    questionsCacheKey(productId, authKey),
    async () => {
      const list = await apiClient.getProductQuestions(productId);
      return Array.isArray(list) ? list : [];
    },
    force,
  );
}

export function invalidatePdpProductQuestions(productId: number): void {
  const prefix = `${productId}:`;
  for (const key of [...questionsCache.keys()]) {
    if (key.startsWith(prefix)) questionsCache.delete(key);
  }
}

export function loadSameAgeGenderRecommendations(
  limit: number,
  profileKey: string,
  force = false,
): Promise<AgeGenderSnap> {
  return inflightGet(
    ageGenderCache,
    ageGenderInflight,
    `${profileKey}:${limit}`,
    () => apiClient.getProductsViewedBySameAgeGender(limit),
    force,
  );
}

export function loadFavoriteProductIds(authKey: string, force = false): Promise<number[]> {
  return inflightGet(favoriteIdsCache, favoriteIdsInflight, authKey, async () => {
    const list = await apiClient.getFavorites();
    if (!Array.isArray(list)) return [];
    return list
      .map((x: { product_id?: number }) => x.product_id)
      .filter((n): n is number => typeof n === 'number');
  }, force);
}
