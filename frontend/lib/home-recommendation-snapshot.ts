import type { Product, SameAgeGenderCohortMode } from '@/types/api';
import { getGuestSessionId } from '@/lib/guest-session';
import {
  HOME_COHORT_MIX_POOL_SIZE,
  mixShopAndCohortProducts,
} from '@/lib/home-recommendation-mixed-products';
import { inferSameShopLoadMoreAvailable } from '@/lib/same-shop-pagination';

const STORAGE_PREFIX = '188-home-snap:v1';
/** Snapshot khách — đủ mới cho giá/sale, không quá ngắn để tránh skeleton liên tục. */
export const GUEST_HOME_SNAPSHOT_TTL_MS = 30 * 60 * 1000;

export const HOME_MIX_INITIAL_LIMIT = 24;

export type HomeRecommendationSnapshotMainFeed = {
  products: Product[];
  total: number;
  personalized: boolean;
  page: number;
  size: number;
};

export type HomeRecommendationSnapshotBlock = {
  sameShopProducts: Product[];
  sameShopTotal: number;
  sameShopSeed: number | null;
  sameShopCanLoadMore: boolean;
  sameAgeGenderProducts: Product[];
  sameAgeGenderCohortMode: SameAgeGenderCohortMode;
  mixedRecommendationProducts: Product[];
  cohortBadgeProductIds: number[];
};

export type HomeRecommendationSnapshot = {
  versionKey: string;
  computedAt: number;
  mainFeed: HomeRecommendationSnapshotMainFeed | null;
  recommendation: HomeRecommendationSnapshotBlock | null;
};

type StoredGuestPayload = {
  versionKey: string;
  computedAt: number;
  snapshot: {
    main_feed?: ApiSnapshotMainFeed | null;
    recommendation?: ApiSnapshotRecommendation | null;
  };
};

type ApiSnapshotMainFeed = {
  products?: Product[];
  total?: number;
  personalized?: boolean;
  page?: number;
  size?: number;
};

type ApiSnapshotRecommendation = {
  same_shop_products?: Product[];
  same_shop_total?: number;
  same_shop_seed?: number | null;
  same_shop_can_load_more?: boolean;
  same_age_gender_products?: Product[];
  same_age_gender_cohort_mode?: SameAgeGenderCohortMode;
  mixed_recommendation_products?: Product[];
  cohort_badge_product_ids?: number[];
};

export function buildHomeSnapshotVersionKey(params: {
  isAuthenticated: boolean;
  userId?: number | null;
  gender?: string | null;
  dateOfBirth?: string | null;
}): string {
  if (params.isAuthenticated && params.userId != null) {
    return `${params.userId}:${params.gender ?? ''}:${params.dateOfBirth ?? ''}`;
  }
  const guestId = getGuestSessionId();
  return guestId ? `guest:${guestId}` : 'guest:anonymous';
}

function guestStorageKey(versionKey: string): string {
  return `${STORAGE_PREFIX}:${versionKey}`;
}

function parseApiSnapshotBody(
  versionKey: string,
  computedAt: string | number | null | undefined,
  raw: {
    main_feed?: ApiSnapshotMainFeed | null;
    recommendation?: ApiSnapshotRecommendation | null;
  } | null | undefined
): HomeRecommendationSnapshot | null {
  if (!raw) return null;
  const ts =
    typeof computedAt === 'number'
      ? computedAt
      : computedAt
        ? Date.parse(computedAt)
        : Date.now();
  if (!Number.isFinite(ts)) return null;

  let mainFeed: HomeRecommendationSnapshotMainFeed | null = null;
  if (raw.main_feed && Array.isArray(raw.main_feed.products)) {
    mainFeed = {
      products: raw.main_feed.products,
      total: raw.main_feed.total ?? raw.main_feed.products.length,
      personalized: Boolean(raw.main_feed.personalized),
      page: raw.main_feed.page ?? 1,
      size: raw.main_feed.size ?? raw.main_feed.products.length,
    };
  }

  let recommendation: HomeRecommendationSnapshotBlock | null = null;
  const rec = raw.recommendation;
  if (rec && Array.isArray(rec.mixed_recommendation_products)) {
    recommendation = {
      sameShopProducts: rec.same_shop_products ?? [],
      sameShopTotal: rec.same_shop_total ?? 0,
      sameShopSeed: rec.same_shop_seed ?? null,
      sameShopCanLoadMore: Boolean(rec.same_shop_can_load_more),
      sameAgeGenderProducts: rec.same_age_gender_products ?? [],
      sameAgeGenderCohortMode: rec.same_age_gender_cohort_mode ?? 'requires_login',
      mixedRecommendationProducts: rec.mixed_recommendation_products,
      cohortBadgeProductIds: rec.cohort_badge_product_ids ?? [],
    };
  }

  if (!mainFeed && !recommendation) return null;
  return { versionKey, computedAt: ts, mainFeed, recommendation };
}

export function parseHomeSnapshotApiResponse(res: {
  version_key?: string | null;
  computed_at?: string | null;
  snapshot?: {
    main_feed?: ApiSnapshotMainFeed | null;
    recommendation?: ApiSnapshotRecommendation | null;
  } | null;
} | null | undefined): HomeRecommendationSnapshot | null {
  if (!res?.snapshot || !res.version_key) return null;
  return parseApiSnapshotBody(res.version_key, res.computed_at, res.snapshot);
}

export function readGuestHomeSnapshot(versionKey: string): HomeRecommendationSnapshot | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(guestStorageKey(versionKey));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredGuestPayload;
    if (parsed.versionKey !== versionKey) return null;
    if (Date.now() - parsed.computedAt > GUEST_HOME_SNAPSHOT_TTL_MS) {
      localStorage.removeItem(guestStorageKey(versionKey));
      return null;
    }
    return parseApiSnapshotBody(parsed.versionKey, parsed.computedAt, parsed.snapshot);
  } catch {
    return null;
  }
}

export function writeGuestHomeSnapshot(snapshot: HomeRecommendationSnapshot): void {
  if (typeof window === 'undefined') return;
  try {
    const payload: StoredGuestPayload = {
      versionKey: snapshot.versionKey,
      computedAt: snapshot.computedAt,
      snapshot: {
        main_feed: snapshot.mainFeed
          ? {
              products: snapshot.mainFeed.products,
              total: snapshot.mainFeed.total,
              personalized: snapshot.mainFeed.personalized,
              page: snapshot.mainFeed.page,
              size: snapshot.mainFeed.size,
            }
          : null,
        recommendation: snapshot.recommendation
          ? {
              same_shop_products: snapshot.recommendation.sameShopProducts,
              same_shop_total: snapshot.recommendation.sameShopTotal,
              same_shop_seed: snapshot.recommendation.sameShopSeed,
              same_shop_can_load_more: snapshot.recommendation.sameShopCanLoadMore,
              same_age_gender_products: snapshot.recommendation.sameAgeGenderProducts,
              same_age_gender_cohort_mode: snapshot.recommendation.sameAgeGenderCohortMode,
              mixed_recommendation_products: snapshot.recommendation.mixedRecommendationProducts,
              cohort_badge_product_ids: snapshot.recommendation.cohortBadgeProductIds,
            }
          : null,
      },
    };
    localStorage.setItem(guestStorageKey(snapshot.versionKey), JSON.stringify(payload));
  } catch {
    /* quota / private mode */
  }
}

export function buildGuestHomeSnapshot(params: {
  versionKey: string;
  mainFeed: HomeRecommendationSnapshotMainFeed | null;
  sameShopProducts: Product[];
  sameShopTotal: number;
  sameShopSeed: number | null;
  sameShopCanLoadMore: boolean;
  sameAgeGenderProducts: Product[];
  sameAgeGenderCohortMode: SameAgeGenderCohortMode;
}): HomeRecommendationSnapshot {
  const cohortForMix =
    params.sameAgeGenderCohortMode === 'requires_login' ||
    params.sameAgeGenderCohortMode === 'profile_incomplete'
      ? []
      : params.sameAgeGenderProducts;

  const mixed = mixShopAndCohortProducts(
    params.sameShopProducts,
    cohortForMix,
    params.sameShopSeed
  );
  const shopIds = new Set(params.sameShopProducts.map((p) => p.id));
  const cohortBadgeProductIds = cohortForMix.filter((p) => !shopIds.has(p.id)).map((p) => p.id);

  return {
    versionKey: params.versionKey,
    computedAt: Date.now(),
    mainFeed: params.mainFeed,
    recommendation: {
      sameShopProducts: params.sameShopProducts,
      sameShopTotal: params.sameShopTotal,
      sameShopSeed: params.sameShopSeed,
      sameShopCanLoadMore: params.sameShopCanLoadMore,
      sameAgeGenderProducts: params.sameAgeGenderProducts,
      sameAgeGenderCohortMode: params.sameAgeGenderCohortMode,
      mixedRecommendationProducts: mixed,
      cohortBadgeProductIds,
    },
  };
}

/** Áp dụng block gợi ý từ snapshot — giữ nguyên logic hiển thị hiện tại. */
export function cohortBadgeIdsFromSnapshot(
  recommendation: HomeRecommendationSnapshotBlock
): Set<number> {
  return new Set(recommendation.cohortBadgeProductIds);
}

export function canPersistGuestRecommendation(
  sameShopTotal: number,
  mixedLength: number
): boolean {
  return sameShopTotal > 0 || mixedLength > 0;
}

export { HOME_COHORT_MIX_POOL_SIZE };
