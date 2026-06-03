// frontend/app/HomePageClient.tsx — logic trang chủ (client); dữ liệu khởi đầu từ SSR qua `initialPlainHome`.
'use client';

import dynamic from 'next/dynamic';
import { useState, useEffect, useCallback, useRef, useLayoutEffect, useMemo } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { SimpleProductCard } from '@/components/ProductCard';

const NanoaiSimilarProductCard = dynamic(() => import('@/components/NanoaiSimilarProductCard'));
const CategoryProductFilters = dynamic(() => import('@/components/CategoryProductFilters'));
import PersonalizedHeroBanner from '@/components/home/PersonalizedHeroBanner';
import SameShopRecommendationHeader from '@/components/home/SameShopRecommendationHeader';
import HomeProductPagination from '@/components/home/HomeProductPagination';
import { apiClient, NANOAI_TEXT_SEARCH_LIMIT } from '@/lib/api-client';
import { getGuestSessionId } from '@/lib/guest-session';
import { useLazyRevealList } from '@/hooks/useLazyRevealList';
import { trackEvent } from '@/lib/analytics';
import type {
  Product,
  ProductListResponse,
  NanoaiSearchProduct,
  SameAgeGenderCohortMode,
  HeroCategoryTilesResponse,
} from '@/types/api';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useFavorites } from '@/features/favorites/hooks/useFavorites';
import {
  readSearchResultCache,
  searchRequestCacheFingerprint,
  writeSearchResultCache,
} from '@/lib/search-result-cache';
import {
  cloneUrlSearchParams,
  searchParamsToEncodedQueryString,
  urlSearchParamsSemanticsEqual,
  shopNameChineseFromListingUrlQuery,
} from '@/lib/product-related-tabs';
import type { CategoryProductFacets } from '@/lib/category-seo';
import {
  inferSameShopLoadMoreAvailable,
  mergeSameShopProductBatch,
  normalizeSameShopTotal,
  sameShopTotalWhenExhausted,
} from '@/lib/same-shop-pagination';
import {
  appendNewShopProductsToMix,
  HOME_COHORT_MIX_POOL_SIZE,
  mixShopAndCohortProducts,
} from '@/lib/home-recommendation-mixed-products';

/** Lần đầu block «CÓ THỂ BẠN THÍCH» — ít SP hơn để luôn có «Xem thêm» khi còn dữ liệu. */
const HOME_MIX_INITIAL_LIMIT = 24;
const HOME_MIX_LOAD_MORE_LIMIT = 24;

function favoritePayloadFromProduct(p: Product): Record<string, unknown> {
  return {
    name: p.name,
    main_image: p.main_image,
    price: p.price,
    slug: p.slug,
    product_id: p.product_id,
  };
}

function sameAgeGenderCompactHint(
  mode: SameAgeGenderCohortMode | null,
  loading: boolean
): React.ReactNode {
  if (loading || mode == null) return null;
  switch (mode) {
    case 'requires_login':
      return (
        <>
          <Link href="/auth/login" className="font-semibold text-[#ea580c] hover:underline">
            Đăng nhập
          </Link>
          {' '}
          và điền hồ sơ để nhận ưu đãi sinh nhật & sản phẩm có thể bạn thích.
        </>
      );
    case 'profile_incomplete':
      return (
        <>
          <Link href="/account/profile" className="font-semibold text-[#ea580c] hover:underline">
            Cập nhật ngày sinh & giới tính
          </Link>
          {' '}
          để nhận ưu đãi sinh nhật & sản phẩm hợp tuổi, hợp gu.
        </>
      );
    default:
      return null;
  }
}

export default function HomePageClient({
  initialPlainHome,
  initialHeroCategories = null,
}: {
  initialPlainHome: ProductListResponse | null;
  initialHeroCategories?: HeroCategoryTilesResponse | null;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isAuthenticated, user, isLoading: authLoading } = useAuth();
  const { refreshFavorites } = useFavorites();
  const qFromUrl = searchParams.get('q') ?? '';
  const shopIdFromUrl = searchParams.get('shop_id') ?? undefined;
  const shopNameFromUrl = searchParams.get('shop_name') ?? undefined;
  const proLowerFromUrl = searchParams.get('pro_lower_price') ?? undefined;
  const proHighFromUrl = searchParams.get('pro_high_price') ?? undefined;
  const shopNameChineseFromUrl = shopNameChineseFromListingUrlQuery((k) => searchParams.get(k));
  const chineseNameFromUrl = searchParams.get('chinese_name') ?? undefined;
  const styleFromUrl = searchParams.get('style') ?? undefined;
  const minPriceFromUrl = searchParams.get('min_price');
  const maxPriceFromUrl = searchParams.get('max_price');
  const sizeFromUrl = searchParams.get('size') ?? undefined;
  const colorFromUrl = searchParams.get('color') ?? undefined;
  const styleTagFromUrl = searchParams.get('style_tag') ?? undefined;
  const sortFromUrl = searchParams.get('sort') ?? undefined;
  const categoryFromUrl = searchParams.get('category') ?? undefined;
  const subcategoryFromUrl = searchParams.get('subcategory') ?? undefined;
  const subSubcategoryFromUrl = searchParams.get('sub_subcategory') ?? undefined;
  const ssrProducts = initialPlainHome?.products ?? [];
  const ssrHasList = ssrProducts.length > 0;
  /** SSR có list → hiện ngay, refresh personalized nền (không che skeleton). */
  const plainHomeAwaitingPersonalized = ssrHasList && initialPlainHome != null;
  const [products, setProducts] = useState<Product[]>(ssrProducts);
  const [totalProducts, setTotalProducts] = useState(initialPlainHome?.total ?? 0);
  const [loading, setLoading] = useState(!ssrHasList);
  const [homeFeedRefreshing, setHomeFeedRefreshing] = useState(plainHomeAwaitingPersonalized);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState(qFromUrl);
  const [selectedFilter, setSelectedFilter] = useState<{
    category?: string;
    subcategory?: string;
    sub_subcategory?: string;
  }>({});
  const [sortBy, setSortBy] = useState('popular');
  const [priceRange, setPriceRange] = useState<[number, number]>([0, 10000000]);
  const [apiStatus, setApiStatus] = useState<'checking' | 'online' | 'offline'>(
    ssrHasList ? 'online' : 'checking'
  );
  const [searchSuggestions, setSearchSuggestions] = useState<string[]>([]);
  const [suggestedCategories, setSuggestedCategories] = useState<{ name?: string; path?: string }[]>([]);
  const [nanoaiTextProducts, setNanoaiTextProducts] = useState<NanoaiSearchProduct[]>([]);
  const [nanoaiTextLoading, setNanoaiTextLoading] = useState(false);
  const [nanoaiTextError, setNanoaiTextError] = useState<string | null>(null);
  const [homeFeedPersonalized, setHomeFeedPersonalized] = useState(
    Boolean(initialPlainHome?.personalized)
  );
  const nanoaiReveal = useLazyRevealList(nanoaiTextProducts, { initial: 12, step: 12 });
  const isSearching = qFromUrl.trim().length > 0;
  const listingFacetAnchor = useMemo(() => {
    const nn = (v?: string | null) => {
      const t = (v ?? '').trim();
      return Boolean(t) && t.toLowerCase() !== 'nan';
    };
    return (
      nn(categoryFromUrl) ||
      nn(subcategoryFromUrl) ||
      nn(subSubcategoryFromUrl) ||
      nn(shopIdFromUrl) ||
      nn(shopNameFromUrl) ||
      nn(shopNameChineseFromUrl) ||
      nn(chineseNameFromUrl) ||
      nn(styleFromUrl) ||
      nn(proLowerFromUrl) ||
      nn(proHighFromUrl)
    );
  }, [
    categoryFromUrl,
    subcategoryFromUrl,
    subSubcategoryFromUrl,
    shopIdFromUrl,
    shopNameFromUrl,
    shopNameChineseFromUrl,
    chineseNameFromUrl,
    styleFromUrl,
    proLowerFromUrl,
    proHighFromUrl,
  ]);

  /** Fetch facets khi có listing (kể cả chỉ sort / giá / size / màu — không chỉ category). */
  const homeFacetFetchAnchor = useMemo(
    () =>
      Boolean(
        listingFacetAnchor ||
          (minPriceFromUrl ?? '').trim() ||
          (maxPriceFromUrl ?? '').trim() ||
          sizeFromUrl ||
          colorFromUrl ||
          styleTagFromUrl ||
          sortFromUrl
      ),
    [
      listingFacetAnchor,
      minPriceFromUrl,
      maxPriceFromUrl,
      sizeFromUrl,
      colorFromUrl,
      styleTagFromUrl,
      sortFromUrl,
    ]
  );

  const pageFromUrl = Number(searchParams.get('page') || 1);
  const currentPage = Number.isFinite(pageFromUrl) && pageFromUrl > 0 ? pageFromUrl : 1;
  const PAGE_SIZE = 48;
  /** Tìm kiếm trang 1: hiện trước N SP, sau đó gọi tiếp để đủ một “trang” (PAGE_SIZE). */
  const SEARCH_INITIAL_LIMIT = 12;
  const [searchCatalogAppending, setSearchCatalogAppending] = useState(false);
  const [searchListingFacets, setSearchListingFacets] = useState<CategoryProductFacets | null>(null);

  const fetchProducts = useCallback(async (filters?: any) => {
    try {
      setLoading(true);
      setError(null);
      const skip = (currentPage - 1) * PAGE_SIZE;
      const usePersonalizedHome = !filters || Object.keys(filters).length === 0;

      let response: ProductListResponse;

      if (usePersonalizedHome) {
        try {
          response = await apiClient.getPersonalizedHomeFeed(skip, PAGE_SIZE);
          setHomeFeedPersonalized(Boolean(response.personalized));
        } catch (homeFeedError) {
          console.warn('Personalized home feed unavailable, using plain product list:', homeFeedError);
          response = await apiClient.getProducts({
            limit: PAGE_SIZE,
            skip,
            is_active: true,
          });
          setHomeFeedPersonalized(false);
        }
      } else {
        setHomeFeedPersonalized(false);
        response = await apiClient.getProducts({
          limit: PAGE_SIZE,
          skip,
          is_active: true,
          ...filters,
        });
        if ((filters?.shop_id ?? '').toString().trim() && (response.products?.length ?? 0) === 0) {
          response = await apiClient.getProducts({
            limit: 48,
            is_active: true,
            ...filters,
            shop_id: undefined,
            shop_name: String(filters.shop_id),
          });
        }
      }

      setProducts(response.products || []);
      setTotalProducts(response.total ?? (response.products?.length ?? 0));
      setApiStatus('online');
    } catch (err: any) {
      console.error('❌ Lỗi tải dữ liệu:', err);
      setError('Không thể kết nối đến server. Vui lòng thử lại sau.');
      setApiStatus('offline');
      setProducts([]);
      setTotalProducts(0);
      setHomeFeedPersonalized(false);
    } finally {
      setLoading(false);
    }
  }, [currentPage]);

  // Tìm kiếm theo q
  const parseNumberParam = (value?: string | null) => {
    if (!value) return undefined;
    const num = Number(value);
    return Number.isFinite(num) ? num : undefined;
  };

  useEffect(() => {
    const qTrim = qFromUrl.trim();
    const fetchSearchFacets = Boolean(qTrim);

    if (!fetchSearchFacets && !homeFacetFetchAnchor) {
      setSearchListingFacets(null);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const baseArgs = {
          category: categoryFromUrl,
          subcategory: subcategoryFromUrl,
          sub_subcategory: subSubcategoryFromUrl,
          shop_id: shopIdFromUrl,
          shop_name: shopNameFromUrl,
          shop_name_chinese: shopNameChineseFromUrl,
          chinese_name: chineseNameFromUrl,
          style: styleFromUrl,
          pro_lower_price: proLowerFromUrl,
          pro_high_price: proHighFromUrl,
          min_price: minPriceFromUrl,
          max_price: maxPriceFromUrl,
          size: sizeFromUrl,
          color: colorFromUrl,
          style_tag: styleTagFromUrl,
          ...(sortFromUrl ? { sort: sortFromUrl } : {}),
        };
        const f = fetchSearchFacets
          ? await apiClient.getSearchProductFacets({ q: qTrim, ...baseArgs })
          : await apiClient.getProductListingFacets(baseArgs);
        if (!cancelled) setSearchListingFacets(f);
      } catch {
        if (!cancelled) {
          setSearchListingFacets({ sizes: [], colors: [], style_tags: [], price_min: null, price_max: null });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    qFromUrl,
    homeFacetFetchAnchor,
    categoryFromUrl,
    subcategoryFromUrl,
    subSubcategoryFromUrl,
    shopIdFromUrl,
    shopNameFromUrl,
    shopNameChineseFromUrl,
    chineseNameFromUrl,
    styleFromUrl,
    proLowerFromUrl,
    proHighFromUrl,
    minPriceFromUrl,
    maxPriceFromUrl,
    sizeFromUrl,
    colorFromUrl,
    styleTagFromUrl,
    sortFromUrl,
  ]);

  useEffect(() => {
    if (!qFromUrl.trim()) {
      setSearchCatalogAppending(false);
      setSearchSuggestions([]);
      setSuggestedCategories([]);
      setNanoaiTextProducts([]);
      setNanoaiTextLoading(false);
      setNanoaiTextError(null);
      return;
    }

    let cancelled = false;

    const searchApiParams = {
      q: qFromUrl,
      is_active: true as const,
      category: categoryFromUrl,
      subcategory: subcategoryFromUrl,
      sub_subcategory: subSubcategoryFromUrl,
      shop_id: shopIdFromUrl,
      shop_name: shopNameFromUrl,
      shop_name_chinese: shopNameChineseFromUrl,
      chinese_name: chineseNameFromUrl,
      style: styleFromUrl,
      pro_lower_price: proLowerFromUrl,
      pro_high_price: proHighFromUrl,
      min_price: parseNumberParam(minPriceFromUrl),
      max_price: parseNumberParam(maxPriceFromUrl),
      size: sizeFromUrl,
      color: colorFromUrl,
      style_tag: styleTagFromUrl,
      ...(sortFromUrl ? { sort: sortFromUrl } : {}),
    };

    const fetchSearchPage = async (skip: number, limit: number): Promise<ProductListResponse> => {
      const fp = searchRequestCacheFingerprint({
        q: qFromUrl,
        is_active: true,
        shop_id: shopIdFromUrl,
        shop_name: shopNameFromUrl,
        shop_name_chinese: shopNameChineseFromUrl,
        chinese_name: chineseNameFromUrl,
        style: styleFromUrl,
        pro_lower_price: proLowerFromUrl,
        pro_high_price: proHighFromUrl,
        min_price: parseNumberParam(minPriceFromUrl),
        max_price: parseNumberParam(maxPriceFromUrl),
        size: sizeFromUrl,
        color: colorFromUrl,
        style_tag: styleTagFromUrl,
        sort: sortFromUrl,
        skip,
        limit,
      });
      const hit = readSearchResultCache(fp);
      if (hit) return hit;
      const response = await apiClient.getProducts({
        ...searchApiParams,
        limit,
        skip,
      });
      if (!cancelled && !response.redirect_path) {
        writeSearchResultCache(fp, response);
      }
      return response;
    };

    (async () => {
      try {
        setError(null);
        setSearchCatalogAppending(false);
        setLoading(true);

        if (currentPage !== 1) {
          const response = await fetchSearchPage((currentPage - 1) * PAGE_SIZE, PAGE_SIZE);
          if (cancelled) return;
          if (response.redirect_path) {
            window.location.assign(response.redirect_path);
            return;
          }
          const latestSuggestions = response.total === 0 ? (response.suggested_queries ?? []) : [];
          setProducts(response.products ?? []);
          setTotalProducts(response.total ?? (response.products?.length ?? 0));
          setSuggestedCategories(response.suggested_categories ?? []);
          setSearchSuggestions(latestSuggestions);
          if (response.total > 0 && response.applied_query && response.applied_query.trim()) {
            apiClient.addSearchHistory(response.applied_query).catch(() => {});
          }
          if (typeof window !== 'undefined') {
            localStorage.setItem(
              'latest_search_suggestions',
              JSON.stringify({ term: qFromUrl.trim(), suggestions: latestSuggestions }),
            );
          }
          setNanoaiTextProducts([]);
          setNanoaiTextLoading(false);
          setNanoaiTextError(null);
          return;
        }

        const first = await fetchSearchPage(0, SEARCH_INITIAL_LIMIT);
        if (cancelled) return;
        if (first.redirect_path) {
          window.location.assign(first.redirect_path);
          return;
        }

        const catalogTotal = first.total ?? 0;
        const firstList = first.products ?? [];
        const latestSuggestions = catalogTotal === 0 ? (first.suggested_queries ?? []) : [];

        setProducts(firstList);
        setTotalProducts(catalogTotal);
        setSuggestedCategories(first.suggested_categories ?? []);
        setSearchSuggestions(latestSuggestions);

        if (catalogTotal > 0 && first.applied_query && first.applied_query.trim()) {
          apiClient.addSearchHistory(first.applied_query).catch(() => {});
        }
        if (typeof window !== 'undefined') {
          localStorage.setItem(
            'latest_search_suggestions',
            JSON.stringify({ term: qFromUrl.trim(), suggestions: latestSuggestions }),
          );
        }

        if (catalogTotal === 0) {
          setNanoaiTextProducts([]);
          setNanoaiTextError(null);
          if (qFromUrl.trim().length >= 2 && currentPage === 1) {
            setNanoaiTextLoading(true);
            try {
              const nano = await apiClient.nanoaiTextSearch(qFromUrl.trim(), NANOAI_TEXT_SEARCH_LIMIT);
              if (cancelled) return;
              const list = Array.isArray(nano.products) ? nano.products : [];
              setNanoaiTextProducts(list);
              if (nano.error && list.length === 0) {
                setNanoaiTextError(nano.error);
              }
            } catch {
              if (!cancelled) {
                setNanoaiTextProducts([]);
                setNanoaiTextError(null);
              }
            } finally {
              if (!cancelled) setNanoaiTextLoading(false);
            }
          } else {
            setNanoaiTextLoading(false);
          }
          return;
        }

        setNanoaiTextProducts([]);
        setNanoaiTextLoading(false);
        setNanoaiTextError(null);

        setLoading(false);

        const wantOnFirstScreen = Math.min(PAGE_SIZE, catalogTotal);
        if (
          firstList.length === SEARCH_INITIAL_LIMIT &&
          catalogTotal > firstList.length &&
          wantOnFirstScreen > firstList.length
        ) {
          setSearchCatalogAppending(true);
          try {
            const more = await fetchSearchPage(
              firstList.length,
              wantOnFirstScreen - firstList.length,
            );
            if (cancelled) return;
            if (!more.redirect_path && (more.products?.length ?? 0) > 0) {
              setProducts((prev) => [...prev, ...(more.products ?? [])]);
            }
          } finally {
            setSearchCatalogAppending(false);
          }
        }
      } catch (err) {
        console.error('Search error:', err);
        if (!cancelled) {
          setError('Lỗi tìm kiếm sản phẩm');
          setProducts([]);
          setTotalProducts(0);
          setSearchSuggestions([]);
          setSuggestedCategories([]);
          setNanoaiTextProducts([]);
          setNanoaiTextLoading(false);
          setNanoaiTextError(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
        setSearchCatalogAppending(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [
    qFromUrl,
    shopIdFromUrl,
    shopNameFromUrl,
    shopNameChineseFromUrl,
    chineseNameFromUrl,
    styleFromUrl,
    proLowerFromUrl,
    proHighFromUrl,
    minPriceFromUrl,
    maxPriceFromUrl,
    sizeFromUrl,
    colorFromUrl,
    styleTagFromUrl,
    sortFromUrl,
    categoryFromUrl,
    subcategoryFromUrl,
    subSubcategoryFromUrl,
    currentPage,
  ]);

  useEffect(() => {
    const minFromUrl = parseNumberParam(minPriceFromUrl) ?? 0;
    const maxFromUrl = parseNumberParam(maxPriceFromUrl) ?? 10000000;
    if (minPriceFromUrl || maxPriceFromUrl) {
      setPriceRange([minFromUrl, maxFromUrl]);
    } else if (
      shopIdFromUrl ||
      shopNameFromUrl ||
      shopNameChineseFromUrl ||
      chineseNameFromUrl ||
      styleFromUrl ||
      proLowerFromUrl ||
      proHighFromUrl
    ) {
      setPriceRange([0, 10000000]);
    }
  }, [
    shopIdFromUrl,
    shopNameFromUrl,
    shopNameChineseFromUrl,
    chineseNameFromUrl,
    styleFromUrl,
    proLowerFromUrl,
    proHighFromUrl,
    minPriceFromUrl,
    maxPriceFromUrl,
  ]);

  const hasFilterParams = Boolean(
    isSearching ||
      categoryFromUrl ||
      subcategoryFromUrl ||
      subSubcategoryFromUrl ||
      shopIdFromUrl ||
      shopNameFromUrl ||
      shopNameChineseFromUrl ||
      chineseNameFromUrl ||
      styleFromUrl ||
      proLowerFromUrl ||
      proHighFromUrl ||
      minPriceFromUrl ||
      maxPriceFromUrl ||
      sizeFromUrl ||
      colorFromUrl ||
      styleTagFromUrl ||
      sortFromUrl
  );

  const recommendationKey = `${isAuthenticated}-${user?.id ?? 'guest'}-${user?.gender ?? ''}-${
    user?.date_of_birth ?? ''
  }`;

  const shopBehaviorKey = useMemo(() => {
    if (user?.id != null) return `user:${user.id}`;
    const guestId = typeof window !== 'undefined' ? getGuestSessionId() : null;
    return `guest:${guestId ?? 'none'}`;
  }, [user?.id]);

  const [sameAgeGenderProducts, setSameAgeGenderProducts] = useState<Product[]>([]);
  const [sameAgeGenderLoading, setSameAgeGenderLoading] = useState(false);
  const [sameAgeGenderCohortMode, setSameAgeGenderCohortMode] = useState<SameAgeGenderCohortMode | null>(null);
  const [sameShopProducts, setSameShopProducts] = useState<Product[]>([]);
  const [sameShopTotal, setSameShopTotal] = useState(0);
  const [sameShopSeed, setSameShopSeed] = useState<number | null>(null);
  const [sameShopLoading, setSameShopLoading] = useState(false);
  const [sameShopLoadMoreLoading, setSameShopLoadMoreLoading] = useState(false);
  const [sameShopCanLoadMore, setSameShopCanLoadMore] = useState(false);
  const [mixedRecommendationProducts, setMixedRecommendationProducts] = useState<Product[]>([]);
  const recommendationMixAnchorRef = useRef('');
  /** Số SP same-shop đã gộp vào lưới — chỉ append khi tăng (tránh «Xem thêm» nhảy lưới). */
  const sameShopMergedCountRef = useRef(0);
  const showSameShopSection = !sameShopLoading && sameShopTotal > 0;
  const lastSearchTrackedRef = useRef<string>('');
  const lastFilterTrackedRef = useRef<string>('');

  useEffect(() => {
    if (!isAuthenticated || user?.id == null) {
      setSameAgeGenderProducts([]);
      setSameAgeGenderCohortMode('requires_login');
      setSameAgeGenderLoading(false);
      return;
    }
    let cancelled = false;
    setSameAgeGenderLoading(true);
    apiClient
      .getProductsViewedBySameAgeGender(HOME_COHORT_MIX_POOL_SIZE)
      .then(({ products, cohort_mode }) => {
        if (cancelled) return;
        setSameAgeGenderProducts(products ?? []);
        setSameAgeGenderCohortMode(cohort_mode);
      })
      .catch(() => {
        if (!cancelled) {
          setSameAgeGenderProducts([]);
          setSameAgeGenderCohortMode('requires_login');
        }
      })
      .finally(() => {
        if (!cancelled) setSameAgeGenderLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, user?.id, user?.gender, user?.date_of_birth]);

  useEffect(() => {
    let cancelled = false;
    setSameShopLoading(true);
    setSameShopCanLoadMore(false);
    apiClient
      .getProductsSameShopAsRecentViews(HOME_MIX_INITIAL_LIMIT, 0)
      .then(({ products, total, seed }) => {
        if (cancelled) return;
        const list = products || [];
        const reported = total ?? 0;
        setSameShopProducts(list);
        setSameShopTotal(
          normalizeSameShopTotal(list.length, reported, HOME_MIX_INITIAL_LIMIT)
        );
        setSameShopSeed(seed ?? null);
        setSameShopCanLoadMore(
          inferSameShopLoadMoreAvailable(
            list.length,
            list.length,
            HOME_MIX_INITIAL_LIMIT,
            normalizeSameShopTotal(list.length, reported, HOME_MIX_INITIAL_LIMIT)
          )
        );
      })
      .catch(() => {
        if (cancelled) return;
        setSameShopProducts([]);
        setSameShopTotal(0);
        setSameShopSeed(null);
        setSameShopCanLoadMore(false);
      })
      .finally(() => {
        if (!cancelled) setSameShopLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [shopBehaviorKey]);

  const cohortProductsForMix = useMemo(() => {
    if (sameAgeGenderLoading) return [];
    if (
      sameAgeGenderCohortMode === 'requires_login' ||
      sameAgeGenderCohortMode === 'profile_incomplete' ||
      sameAgeGenderProducts.length === 0
    ) {
      return [];
    }
    return sameAgeGenderProducts;
  }, [sameAgeGenderLoading, sameAgeGenderCohortMode, sameAgeGenderProducts]);

  useEffect(() => {
    recommendationMixAnchorRef.current = '';
    sameShopMergedCountRef.current = 0;
    setMixedRecommendationProducts([]);
  }, [shopBehaviorKey]);

  useEffect(() => {
    if (sameShopLoading) return;

    const cohortAnchor = sameAgeGenderLoading
      ? 'pending'
      : cohortProductsForMix.length > 0
        ? cohortProductsForMix
            .map((p) => p.id)
            .sort((a, b) => a - b)
            .join(',')
        : 'none';
    const anchor = `${recommendationKey}:${sameShopSeed ?? 'none'}:${cohortAnchor}`;
    if (recommendationMixAnchorRef.current !== anchor) {
      recommendationMixAnchorRef.current = anchor;
      sameShopMergedCountRef.current = sameShopProducts.length;
      setMixedRecommendationProducts(
        mixShopAndCohortProducts(sameShopProducts, cohortProductsForMix, sameShopSeed)
      );
      return;
    }

    const shopCount = sameShopProducts.length;
    if (shopCount <= sameShopMergedCountRef.current) return;
    sameShopMergedCountRef.current = shopCount;
    setMixedRecommendationProducts((prev) =>
      appendNewShopProductsToMix(prev, sameShopProducts)
    );
  }, [
    recommendationKey,
    sameShopSeed,
    sameShopProducts,
    sameShopLoading,
    sameAgeGenderLoading,
    cohortProductsForMix,
  ]);

  useEffect(() => {
    if (qFromUrl.trim()) return;
    setSelectedFilter({
      category: categoryFromUrl,
      subcategory: subcategoryFromUrl,
      sub_subcategory: subSubcategoryFromUrl,
    });
    const skip = (currentPage - 1) * PAGE_SIZE;
    const ssrPage = initialPlainHome?.page ?? 1;
    const ssrOk = (initialPlainHome?.products?.length ?? 0) > 0 && initialPlainHome != null;

    if (ssrOk && currentPage === ssrPage) {
      setError(null);
      setHomeFeedRefreshing(true);
      void apiClient
        .getPersonalizedHomeFeed(skip, PAGE_SIZE)
        .then((response) => {
          setProducts(response.products || []);
          setTotalProducts(response.total ?? (response.products?.length ?? 0));
          setHomeFeedPersonalized(Boolean(response.personalized));
          setApiStatus('online');
        })
        .catch(() => {
          setProducts(initialPlainHome?.products ?? []);
          setTotalProducts(initialPlainHome?.total ?? 0);
          setHomeFeedPersonalized(Boolean(initialPlainHome?.personalized));
          setApiStatus('online');
        })
        .finally(() => {
          setHomeFeedRefreshing(false);
          setLoading(false);
        });
      return;
    }

    if (authLoading) return;
    if (
      categoryFromUrl ||
      subcategoryFromUrl ||
      subSubcategoryFromUrl ||
      shopIdFromUrl ||
      shopNameFromUrl ||
      shopNameChineseFromUrl ||
      chineseNameFromUrl ||
      styleFromUrl ||
      proLowerFromUrl ||
      proHighFromUrl ||
      minPriceFromUrl ||
      maxPriceFromUrl ||
      sizeFromUrl ||
      colorFromUrl ||
      styleTagFromUrl ||
      sortFromUrl
    ) {
      fetchProducts({
        category: categoryFromUrl,
        subcategory: subcategoryFromUrl,
        sub_subcategory: subSubcategoryFromUrl,
        shop_id: shopIdFromUrl,
        shop_name: shopNameFromUrl,
        shop_name_chinese: shopNameChineseFromUrl,
        chinese_name: chineseNameFromUrl,
        style: styleFromUrl,
        pro_lower_price: proLowerFromUrl,
        pro_high_price: proHighFromUrl,
        min_price: parseNumberParam(minPriceFromUrl),
        max_price: parseNumberParam(maxPriceFromUrl),
        size: sizeFromUrl,
        color: colorFromUrl,
        style_tag: styleTagFromUrl,
        ...(sortFromUrl ? { sort: sortFromUrl } : {}),
      });
      return;
    }
    fetchProducts();
  }, [
    categoryFromUrl,
    subcategoryFromUrl,
    subSubcategoryFromUrl,
    shopIdFromUrl,
    shopNameFromUrl,
    shopNameChineseFromUrl,
    chineseNameFromUrl,
    styleFromUrl,
    proLowerFromUrl,
    proHighFromUrl,
    minPriceFromUrl,
    maxPriceFromUrl,
    qFromUrl,
    sizeFromUrl,
    colorFromUrl,
    styleTagFromUrl,
    sortFromUrl,
    fetchProducts,
    currentPage,
    initialPlainHome,
    authLoading,
  ]);

  const retryHomeDataLoad = useCallback(() => {
    if (qFromUrl.trim()) {
      if (typeof window !== 'undefined') window.location.reload();
      return;
    }
    if (
      categoryFromUrl ||
      subcategoryFromUrl ||
      subSubcategoryFromUrl ||
      shopIdFromUrl ||
      shopNameFromUrl ||
      shopNameChineseFromUrl ||
      chineseNameFromUrl ||
      styleFromUrl ||
      proLowerFromUrl ||
      proHighFromUrl ||
      minPriceFromUrl ||
      maxPriceFromUrl ||
      sizeFromUrl ||
      colorFromUrl ||
      styleTagFromUrl ||
      sortFromUrl
    ) {
      void fetchProducts({
        category: categoryFromUrl,
        subcategory: subcategoryFromUrl,
        sub_subcategory: subSubcategoryFromUrl,
        shop_id: shopIdFromUrl,
        shop_name: shopNameFromUrl,
        shop_name_chinese: shopNameChineseFromUrl,
        chinese_name: chineseNameFromUrl,
        style: styleFromUrl,
        pro_lower_price: proLowerFromUrl,
        pro_high_price: proHighFromUrl,
        min_price: parseNumberParam(minPriceFromUrl),
        max_price: parseNumberParam(maxPriceFromUrl),
        size: sizeFromUrl,
        color: colorFromUrl,
        style_tag: styleTagFromUrl,
        ...(sortFromUrl ? { sort: sortFromUrl } : {}),
      });
      return;
    }
    void fetchProducts();
  }, [
    qFromUrl,
    categoryFromUrl,
    subcategoryFromUrl,
    subSubcategoryFromUrl,
    shopIdFromUrl,
    shopNameFromUrl,
    shopNameChineseFromUrl,
    chineseNameFromUrl,
    styleFromUrl,
    proLowerFromUrl,
    proHighFromUrl,
    minPriceFromUrl,
    maxPriceFromUrl,
    sizeFromUrl,
    colorFromUrl,
    styleTagFromUrl,
    sortFromUrl,
    fetchProducts,
  ]);

  useEffect(() => {
    if (!qFromUrl.trim() || loading) return;
    const key = `${qFromUrl}-${currentPage}-${totalProducts}`;
    if (lastSearchTrackedRef.current === key) return;
    lastSearchTrackedRef.current = key;
    trackEvent('search', {
      term: qFromUrl.trim(),
      results: totalProducts,
      page: currentPage,
    });
  }, [qFromUrl, totalProducts, currentPage, loading]);

  useEffect(() => {
    if (!hasFilterParams || loading) return;
    const signature = JSON.stringify({
      category: categoryFromUrl,
      subcategory: subcategoryFromUrl,
      sub_subcategory: subSubcategoryFromUrl,
      shop_id: shopIdFromUrl,
      shop_name: shopNameFromUrl,
      shop_name_chinese: shopNameChineseFromUrl,
      chinese_name: chineseNameFromUrl,
      style: styleFromUrl,
      pro_lower_price: proLowerFromUrl,
      pro_high_price: proHighFromUrl,
      min_price: minPriceFromUrl,
      max_price: maxPriceFromUrl,
      size: sizeFromUrl,
      color: colorFromUrl,
      style_tag: styleTagFromUrl,
      sort: sortFromUrl,
      page: currentPage,
    });
    if (lastFilterTrackedRef.current === signature) return;
    lastFilterTrackedRef.current = signature;
    trackEvent('filter_apply', {
      category: categoryFromUrl,
      subcategory: subcategoryFromUrl,
      sub_subcategory: subSubcategoryFromUrl,
      shop_id: shopIdFromUrl,
      shop_name: shopNameFromUrl,
      shop_name_chinese: shopNameChineseFromUrl,
      chinese_name: chineseNameFromUrl,
      style: styleFromUrl,
      pro_lower_price: proLowerFromUrl,
      pro_high_price: proHighFromUrl,
      min_price: minPriceFromUrl,
      max_price: maxPriceFromUrl,
      size: sizeFromUrl,
      color: colorFromUrl,
      style_tag: styleTagFromUrl,
      sort: sortFromUrl,
      page: currentPage,
    });
  }, [
    hasFilterParams,
    loading,
    categoryFromUrl,
    subcategoryFromUrl,
    subSubcategoryFromUrl,
    shopIdFromUrl,
    shopNameFromUrl,
    shopNameChineseFromUrl,
    chineseNameFromUrl,
    styleFromUrl,
    proLowerFromUrl,
    proHighFromUrl,
    minPriceFromUrl,
    maxPriceFromUrl,
    sizeFromUrl,
    colorFromUrl,
    styleTagFromUrl,
    sortFromUrl,
    currentPage,
  ]);

  const canonicalListingQs = useMemo(
    () => searchParamsToEncodedQueryString(cloneUrlSearchParams(searchParams)),
    [searchParams]
  );

  useLayoutEffect(() => {
    if (typeof window === 'undefined') return;
    if (window.location.pathname !== '/') return;
    const curRaw = window.location.search.startsWith('?') ? window.location.search.slice(1) : '';
    if (curRaw === canonicalListingQs) return;
    const curSp = new URLSearchParams(curRaw);
    const canSp = new URLSearchParams(canonicalListingQs);
    if (!urlSearchParamsSemanticsEqual(curSp, canSp)) return;
    router.replace(canonicalListingQs ? `/?${canonicalListingQs}` : '/', { scroll: false });
  }, [canonicalListingQs, router, searchParams]);

  const totalPages = Math.max(1, Math.ceil(totalProducts / PAGE_SIZE));
  const setPage = (page: number) => {
    const next = Math.min(Math.max(1, page), totalPages);
    const params = cloneUrlSearchParams(searchParams);
    if (next <= 1) {
      params.delete('page');
    } else {
      params.set('page', String(next));
    }
    const q = searchParamsToEncodedQueryString(params);
    router.push(q ? `/?${q}` : '/');
  };

  const shouldApplyPriceFilter = Boolean(minPriceFromUrl || maxPriceFromUrl);
  const showPagination = totalPages > 1 && !shouldApplyPriceFilter;
  // Filter sản phẩm client-side cho price range (tạm thời)
  const filteredProducts = shouldApplyPriceFilter
    ? products.filter(product => {
      const productPrice = product.price || 0;
      return productPrice >= priceRange[0] && productPrice <= priceRange[1];
    })
    : products;

  const [favoriteIds, setFavoriteIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getFavorites()
      .then((list) => {
        if (cancelled || !Array.isArray(list)) return;
        const ids = list
          .map((x: { product_id?: number }) => x.product_id)
          .filter((n): n is number => typeof n === 'number');
        setFavoriteIds(new Set(ids));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, user?.id]);

  const loadMoreSameShop = useCallback(() => {
    if (!sameShopCanLoadMore || sameShopLoadMoreLoading) return;
    if (sameShopSeed == null) return;
    setSameShopLoadMoreLoading(true);
    const offset = sameShopProducts.length;
    apiClient
      .getProductsSameShopAsRecentViews(HOME_MIX_LOAD_MORE_LIMIT, offset, sameShopSeed)
      .then(({ products, total }) => {
        const batch = products || [];
        if (batch.length === 0) {
          setSameShopCanLoadMore(false);
          setSameShopTotal(sameShopTotalWhenExhausted(offset));
          return;
        }
        setSameShopProducts((prev) => {
          const { merged, addedCount } = mergeSameShopProductBatch(prev, batch);
          if (addedCount === 0) {
            setSameShopCanLoadMore(false);
            setSameShopTotal(sameShopTotalWhenExhausted(prev.length));
            return prev;
          }
          const reported = total ?? 0;
          const loaded = merged.length;
          const normalizedTotal = normalizeSameShopTotal(
            loaded,
            Math.max(reported, loaded),
            HOME_MIX_LOAD_MORE_LIMIT
          );
          setSameShopTotal(normalizedTotal);
          setSameShopCanLoadMore(
            inferSameShopLoadMoreAvailable(
              loaded,
              batch.length,
              HOME_MIX_LOAD_MORE_LIMIT,
              normalizedTotal
            )
          );
          return merged;
        });
      })
      .catch(() => {
        /* Giữ nút «Xem thêm» — khách bấm lại; không xóa lưới hiện tại. */
      })
      .finally(() => setSameShopLoadMoreLoading(false));
  }, [
    sameShopCanLoadMore,
    sameShopLoadMoreLoading,
    sameShopProducts.length,
    sameShopSeed,
    sameShopProducts,
  ]);

  const cohortBadgeProductIds = useMemo(() => {
    const shopIds = new Set(sameShopProducts.map((p) => p.id));
    return new Set(cohortProductsForMix.filter((p) => !shopIds.has(p.id)).map((p) => p.id));
  }, [sameShopProducts, cohortProductsForMix]);

  const hasCohortProductsForHeader =
    sameAgeGenderCohortMode != null &&
    sameAgeGenderCohortMode !== 'requires_login' &&
    sameAgeGenderCohortMode !== 'profile_incomplete' &&
    sameAgeGenderProducts.length > 0;

  const sameAgeGenderHint = sameAgeGenderCompactHint(
    sameAgeGenderCohortMode,
    sameAgeGenderLoading && isAuthenticated
  );

  const showMixedRecommendationSection =
    mixedRecommendationProducts.length > 0 ||
    showSameShopSection ||
    cohortProductsForMix.length > 0 ||
    sameShopLoading ||
    (!authLoading &&
      (sameAgeGenderCohortMode === 'requires_login' ||
        sameAgeGenderCohortMode === 'profile_incomplete'));

  const handleFavorite = async (productId: number, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const product =
      filteredProducts.find((p) => p.id === productId) ??
      products.find((p) => p.id === productId) ??
      sameShopProducts.find((p) => p.id === productId) ??
      mixedRecommendationProducts.find((p) => p.id === productId) ??
      sameAgeGenderProducts.find((p) => p.id === productId);
    const had = favoriteIds.has(productId);
    try {
      if (had) {
        await apiClient.removeFromFavorites(productId);
        setFavoriteIds((prev) => {
          const next = new Set(prev);
          next.delete(productId);
          return next;
        });
      } else {
        await apiClient.addToFavorites(
          productId,
          product ? favoritePayloadFromProduct(product) : undefined
        );
        setFavoriteIds((prev) => new Set(prev).add(productId));
      }
      void refreshFavorites();
    } catch {
      /* im lặng — có thể thêm toast sau */
    }
  };

  const heroShopName = useMemo(() => {
    for (const p of sameShopProducts) {
      const name = (p.shop_name_chinese ?? p.shop_name ?? '').trim();
      if (name) return name;
    }
    return null;
  }, [sameShopProducts]);

  const heroPreviewProducts = useMemo(() => sameShopProducts.slice(0, 3), [sameShopProducts]);

  const heroUserGender =
    user?.gender === 'male' || user?.gender === 'female' ? user.gender : null;

  return (
    <div>
      {apiStatus === 'offline' && (
        <div className="bg-amber-500/95 text-white py-3 px-4 text-center text-sm font-medium shadow-md">
          Không thể kết nối đến server. Vui lòng kiểm tra mạng và tải lại trang.
        </div>
      )}

      <main className="max-w-7xl mx-auto px-4 py-4 md:py-6">
        {error && (
          <div className="mb-6 bg-red-50/90 border border-red-200 rounded-xl p-4 flex items-center justify-between gap-4 shadow-sm">
            <p className="text-red-700 font-medium">{error}</p>
            <button
              type="button"
              onClick={() => retryHomeDataLoad()}
              className="flex-shrink-0 bg-red-500 text-white px-4 py-2.5 rounded-lg text-sm font-medium hover:bg-red-600 transition-colors shadow-sm"
            >
              Thử lại
            </button>
          </div>
        )}

        {!hasFilterParams && (
          <PersonalizedHeroBanner
            apiStatus={apiStatus}
            sameShopTotal={sameShopTotal}
            sameShopLoading={sameShopLoading}
            shopName={heroShopName}
            previewProducts={heroPreviewProducts}
            behaviorKey={recommendationKey}
            isAuthenticated={isAuthenticated}
            userGender={heroUserGender}
            initialHeroCategories={initialHeroCategories}
          />
        )}

        {hasFilterParams && (
          <section className="mb-6">
            <div className="flex flex-col gap-4 mb-4">
              <div className="min-w-0">
                <h2 className="text-base font-bold text-gray-900 mb-2 border-b-2 border-[#ea580c] pb-1 w-fit">
                  KẾT QUẢ LỌC
                </h2>
                <p className="text-sm text-gray-600 mt-1">
                  {isSearching ? (
                    <>
                      Từ khóa: <span className="font-medium text-gray-900">&quot;{qFromUrl}&quot;</span> —{' '}
                      {totalProducts} sản phẩm trong kho
                      {nanoaiTextProducts.length > 0 && (
                        <span className="text-gray-700">
                          {' '}
                          · {nanoaiTextProducts.length} gợi ý từ NanoAI
                          {nanoaiTextProducts.length >= NANOAI_TEXT_SEARCH_LIMIT ? (
                            <span className="text-gray-500"> (tối đa {NANOAI_TEXT_SEARCH_LIMIT} mỗi lần truy vấn)</span>
                          ) : null}
                        </span>
                      )}
                      {nanoaiTextLoading && <span className="text-gray-500"> · Đang tra cứu NanoAI…</span>}
                    </>
                  ) : (
                    <>
                      {totalProducts} sản phẩm
                    </>
                  )}
                </p>
              </div>
            </div>
            <div className="sticky top-[var(--mobile-app-header-height)] z-40 mb-4 w-full border-b border-gray-200 bg-gray-50/95 px-1.5 py-1.5 shadow-sm backdrop-blur sm:px-3 md:top-[var(--listing-filter-sticky-top)] md:border-t-0 md:bg-gray-50 md:shadow-none md:backdrop-blur-none">
                <CategoryProductFilters
                  basePath="/"
                  facets={
                    searchListingFacets ?? {
                      sizes: [],
                      colors: [],
                      style_tags: [],
                      price_min: null,
                      price_max: null,
                    }
                  }
                  enableEmptyListing={isSearching}
                  enableListingFacetShell={!isSearching && hasFilterParams}
                  compact
                />
              </div>
            <div className="mt-4">
              {loading ? (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-4">
                  {[...Array(12)].map((_, i) => (
                    <div key={i} className="bg-white rounded-xl border border-gray-100 overflow-hidden animate-pulse">
                      <div className="aspect-square bg-gray-100" />
                      <div className="p-3 space-y-2">
                        <div className="h-3 bg-gray-100 rounded w-3/4" />
                        <div className="h-3 bg-gray-100 rounded w-full" />
                        <div className="h-4 bg-gray-100 rounded w-2/5" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : filteredProducts.length > 0 ? (
                <>
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-4">
                  {filteredProducts.map((product, index) => (
                    <SimpleProductCard
                      key={product.id}
                      product={product}
                      onFavorite={handleFavorite}
                      isFavorited={favoriteIds.has(product.id)}
                      priority={index < 2}
                    />
                  ))}
                </div>
                {isSearching && currentPage === 1 && searchCatalogAppending && (
                  <p className="mt-4 flex items-center justify-center gap-2 text-sm text-gray-600" aria-live="polite">
                    <span
                      className="inline-block w-4 h-4 border-2 border-[#ea580c] border-t-transparent rounded-full animate-spin"
                      aria-hidden
                    />
                    Đang tải thêm sản phẩm…
                  </p>
                )}
                </>
              ) : (
                <div className="space-y-6">
                  {isSearching && nanoaiTextLoading && (
                    <div className="flex items-center gap-2 text-sm text-gray-600">
                      <span
                        className="inline-block w-4 h-4 border-2 border-[#ea580c] border-t-transparent rounded-full animate-spin"
                        aria-hidden
                      />
                      Đang tìm gợi ý theo từ khóa (NanoAI)…
                    </div>
                  )}
                  {isSearching && !nanoaiTextLoading && nanoaiTextProducts.length > 0 && (
                    <div>
                      <h3 className="text-sm font-semibold text-gray-900 mb-3 border-b border-[#ea580c]/30 pb-1 w-fit">
                        Gợi ý theo ngữ nghĩa (NanoAI)
                      </h3>
                      <p className="text-xs text-gray-600 mb-3">
                        Kho cửa hàng không có kết quả trùng từ khóa; dưới đây là sản phẩm gần nghĩa từ chỉ mục vector.
                      </p>
                      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-4">
                        {nanoaiReveal.revealed.map((item, i) => (
                          <NanoaiSimilarProductCard
                            key={item.inventory_id || `${item.sku || item.name || i}-${i}`}
                            item={item}
                          />
                        ))}
                      </div>
                      {nanoaiReveal.hasMore ? (
                        <p className="text-center text-xs text-gray-500 py-3" aria-live="polite">
                          Đang hiển thị {nanoaiReveal.revealed.length} / {nanoaiReveal.total} — kéo xuống để xem thêm
                        </p>
                      ) : null}
                      <div ref={nanoaiReveal.sentinelRef} className="h-4 w-full" aria-hidden />
                    </div>
                  )}
                  {isSearching && nanoaiTextError && !nanoaiTextLoading && nanoaiTextProducts.length === 0 && (
                    <p className="text-xs text-amber-900 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
                      {nanoaiTextError}
                    </p>
                  )}
                  <div className="text-sm text-gray-500 bg-gray-50 border border-gray-200 rounded-lg p-4">
                    <p>Không tìm thấy sản phẩm chính xác, nhưng có thể bạn quan tâm:</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {suggestedCategories.length > 0 ? (
                        suggestedCategories.map((c, idx) => (
                          <Link
                            key={`${c.path}-${idx}`}
                            href={c.path || '#'}
                            className="px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-[#ea580c] hover:bg-[#d97706] transition-colors"
                          >
                            {c.name || 'Danh mục'}
                          </Link>
                        ))
                      ) : isSearching && searchSuggestions.length > 0 ? (
                        searchSuggestions.map((term) => (
                          <Link
                            key={term}
                            href={`/?q=${encodeURIComponent(term)}`}
                            className="text-xs text-[#ea580c] bg-white border border-[#ea580c]/30 px-2 py-1 rounded-full hover:bg-[#ea580c] hover:text-white transition-colors"
                          >
                            {term}
                          </Link>
                        ))
                      ) : null}
                    </div>
                  </div>
                </div>
              )}
            </div>
            {showPagination && (
              <HomeProductPagination
                currentPage={currentPage}
                totalPages={totalPages}
                totalProducts={totalProducts}
                onPageChange={setPage}
              />
            )}
          </section>
        )}

        {/* Cùng shop + trộn ngẫu nhiên pool tuổi/giới (1 lưới). */}
        {!hasFilterParams && showMixedRecommendationSection && (
          <section className="mb-8" id="san-pham-cung-shop">
            <SameShopRecommendationHeader
              cohortMode={sameAgeGenderCohortMode}
              cohortLoading={sameAgeGenderLoading}
              isAuthenticated={isAuthenticated}
              hasCohortProducts={hasCohortProductsForHeader}
              hint={sameAgeGenderHint}
            />
            <div className="mt-3">
              {sameShopLoading ? (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-4">
                  {[...Array(12)].map((_, i) => (
                    <div key={i} className="bg-white rounded-xl border border-gray-100 overflow-hidden animate-pulse">
                      <div className="aspect-square bg-gray-100" />
                      <div className="p-3 space-y-2">
                        <div className="h-3 bg-gray-100 rounded w-3/4" />
                        <div className="h-3 bg-gray-100 rounded w-full" />
                        <div className="h-4 bg-gray-100 rounded w-2/5" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : mixedRecommendationProducts.length > 0 ? (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-4">
                  {mixedRecommendationProducts.map((product, index) => (
                    <SimpleProductCard
                      key={product.id}
                      product={product}
                      onFavorite={handleFavorite}
                      isFavorited={favoriteIds.has(product.id)}
                      showPersonalizedBadge={cohortBadgeProductIds.has(product.id)}
                      priority={index < 2}
                    />
                  ))}
                </div>
              ) : null}
              {sameShopCanLoadMore && mixedRecommendationProducts.length > 0 && (
                <div className="flex justify-center pt-5 pb-2">
                  <button
                    type="button"
                    onClick={loadMoreSameShop}
                    disabled={sameShopLoadMoreLoading}
                    className="inline-flex min-h-[44px] items-center rounded-xl bg-[#ea580c] px-6 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-[#c2410c] disabled:opacity-60"
                  >
                    {sameShopLoadMoreLoading ? 'Đang tải...' : 'Xem thêm'}
                  </button>
                </div>
              )}
            </div>
          </section>
        )}

        {/* Grid SP chính: không có ?category/lọc URL — trước đây không render danh sách filteredProducts */}
        {!hasFilterParams && (
          <section className="mb-8" aria-labelledby="home-all-products-heading">
            <div className="mb-4">
              <h2
                id="home-all-products-heading"
                className="text-base font-bold text-gray-900 mb-2 border-b-2 border-[#ea580c] pb-1 w-fit"
              >
                TẤT CẢ SẢN PHẨM
              </h2>
              {homeFeedPersonalized ? (
                <p className="text-xs text-gray-600">
                  Ưu tiên theo danh mục và shop gần với sản phẩm bạn đã xem hoặc thích.
                </p>
              ) : null}
            </div>
            {loading ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-4 min-h-[min(32rem,80vh)]">
                {[...Array(12)].map((_, i) => (
                  <div key={i} className="bg-white rounded-xl border border-gray-100 overflow-hidden animate-pulse">
                    <div className="aspect-square bg-gray-100" />
                    <div className="p-3 space-y-2">
                      <div className="h-3 bg-gray-100 rounded w-3/4" />
                      <div className="h-3 bg-gray-100 rounded w-full" />
                      <div className="h-4 bg-gray-100 rounded w-2/5" />
                    </div>
                  </div>
                ))}
              </div>
            ) : filteredProducts.length > 0 ? (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-4">
                  {filteredProducts.map((product, index) => (
                    <SimpleProductCard
                      key={product.id}
                      product={product}
                      onFavorite={handleFavorite}
                      isFavorited={favoriteIds.has(product.id)}
                      priority={index < 2 && sameShopProducts.length === 0}
                    />
                  ))}
                </div>
                {showPagination && (
                  <HomeProductPagination
                    currentPage={currentPage}
                    totalPages={totalPages}
                    totalProducts={totalProducts}
                    onPageChange={setPage}
                  />
                )}
              </>
            ) : (
              <p className="text-center text-gray-500 py-10">
                {apiStatus === 'offline'
                  ? 'Không tải được danh sách sản phẩm. Vui lòng thử lại sau.'
                  : 'Chưa có sản phẩm nào.'}
              </p>
            )}
          </section>
        )}

      </main>
    </div>
  );
}
