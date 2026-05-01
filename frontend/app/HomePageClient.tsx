// frontend/app/HomePageClient.tsx — logic trang chủ (client); dữ liệu khởi đầu từ SSR qua `initialPlainHome`.
'use client';

import dynamic from 'next/dynamic';
import { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import Image from 'next/image';
import { SimpleProductCard } from '@/components/ProductCard';

const NanoaiSimilarProductCard = dynamic(() => import('@/components/NanoaiSimilarProductCard'));
import MobilePromoBanner from '@/components/mobile/MobilePromoBanner';
import { apiClient, NANOAI_TEXT_SEARCH_LIMIT } from '@/lib/api-client';
import { useLazyRevealList } from '@/hooks/useLazyRevealList';
import { trackEvent } from '@/lib/analytics';
import { getOptimizedImage } from '@/lib/image-utils';
import { formatPrice } from '@/lib/utils';
import type { Product, ProductListResponse, NanoaiSearchProduct, SameAgeGenderCohortMode } from '@/types/api';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useFavorites } from '@/features/favorites/hooks/useFavorites';

function favoritePayloadFromProduct(p: Product): Record<string, unknown> {
  return {
    name: p.name,
    main_image: p.main_image,
    price: p.price,
    slug: p.slug,
    product_id: p.product_id,
  };
}

function sameAgeGenderSectionDescription(
  mode: SameAgeGenderCohortMode | null,
  loading: boolean
): string | null {
  if (loading || mode == null) return null;
  switch (mode) {
    case 'requires_login':
      return 'Đăng nhập và điền ngày sinh cùng giới tính trong Hồ sơ để nhận gợi ý từ nhóm khách tương đồng.';
    case 'profile_incomplete':
      return 'Vui lòng cập nhật đủ ngày sinh và giới tính trong Hồ sơ — sau khi lưu, trang chủ sẽ hiển thị gợi ý theo nhóm tuổi và giới của bạn.';
    case 'exact_cohort':
      return 'Dựa trên sản phẩm mà khách cùng năm sinh và cùng giới tính với bạn thường xem.';
    case 'gender_peers':
      return 'Nhóm cùng tuổi chưa có đủ lượt xem — đang mở rộng gợi ý theo giới tính của bạn.';
    case 'popular_fallback':
      return 'Chưa có lượt xem nhóm để so sánh — đang hiển thị sản phẩm phổ biến; khám phá thêm để gợi ý chính xác hơn.';
    default:
      return null;
  }
}

function sameAgeGenderPanelTitle(mode: SameAgeGenderCohortMode | null): string {
  switch (mode) {
    case 'exact_cohort':
      return 'Khách cùng tuổi, cùng giới tính với bạn đang xem';
    case 'gender_peers':
      return 'Khách cùng giới tính đang xem nhiều';
    case 'popular_fallback':
      return 'Sản phẩm phổ biến gợi ý cho bạn';
    default:
      return 'Gợi ý cho bạn';
  }
}

export default function HomePageClient({
  initialPlainHome,
}: {
  initialPlainHome: ProductListResponse | null;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isAuthenticated, user } = useAuth();
  const { refreshFavorites } = useFavorites();
  const qFromUrl = searchParams.get('q') ?? '';
  const shopIdFromUrl = searchParams.get('shop_id') ?? undefined;
  const shopNameFromUrl = searchParams.get('shop_name') ?? undefined;
  const proLowerFromUrl = searchParams.get('pro_lower_price') ?? undefined;
  const proHighFromUrl = searchParams.get('pro_high_price') ?? undefined;
  const minPriceFromUrl = searchParams.get('min_price');
  const maxPriceFromUrl = searchParams.get('max_price');
  const ssrProducts = initialPlainHome?.products ?? [];
  const ssrHasList = ssrProducts.length > 0;
  const [products, setProducts] = useState<Product[]>(ssrProducts);
  const [totalProducts, setTotalProducts] = useState(initialPlainHome?.total ?? 0);
  const [loading, setLoading] = useState(!ssrHasList);
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
  const pageFromUrl = Number(searchParams.get('page') || 1);
  const currentPage = Number.isFinite(pageFromUrl) && pageFromUrl > 0 ? pageFromUrl : 1;
  const PAGE_SIZE = 48;

  const fetchProducts = useCallback(async (filters?: any) => {
    try {
      setLoading(true);
      setError(null);
      const skip = (currentPage - 1) * PAGE_SIZE;
      const usePersonalizedHome = !filters || Object.keys(filters).length === 0;

      let response: ProductListResponse;

      if (usePersonalizedHome) {
        response = await apiClient.getPersonalizedHomeFeed(skip, PAGE_SIZE);
        setHomeFeedPersonalized(Boolean(response.personalized));
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
    setSearchTerm(qFromUrl);
    if (qFromUrl.trim()) {
      (async () => {
        try {
          setLoading(true);
          setError(null);
          const response = await apiClient.getProducts({
            q: qFromUrl,
            limit: PAGE_SIZE,
            skip: (currentPage - 1) * PAGE_SIZE,
            is_active: true,
            shop_id: shopIdFromUrl,
            shop_name: shopNameFromUrl,
            pro_lower_price: proLowerFromUrl,
            pro_high_price: proHighFromUrl,
            min_price: parseNumberParam(minPriceFromUrl),
            max_price: parseNumberParam(maxPriceFromUrl),
          });
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
            const payload = {
              term: qFromUrl.trim(),
              suggestions: latestSuggestions,
            };
            localStorage.setItem('latest_search_suggestions', JSON.stringify(payload));
          }

          const catalogTotal = response.total ?? 0;
          if (
            qFromUrl.trim().length >= 2 &&
            currentPage === 1 &&
            catalogTotal === 0
          ) {
            setNanoaiTextLoading(true);
            setNanoaiTextProducts([]);
            setNanoaiTextError(null);
            try {
              const nano = await apiClient.nanoaiTextSearch(qFromUrl.trim(), NANOAI_TEXT_SEARCH_LIMIT);
              const list = Array.isArray(nano.products) ? nano.products : [];
              setNanoaiTextProducts(list);
              if (nano.error && list.length === 0) {
                setNanoaiTextError(nano.error);
              }
            } catch {
              setNanoaiTextProducts([]);
              setNanoaiTextError(null);
            } finally {
              setNanoaiTextLoading(false);
            }
          } else {
            setNanoaiTextProducts([]);
            setNanoaiTextLoading(false);
            setNanoaiTextError(null);
          }
        } catch (err) {
          console.error('Search error:', err);
          setError('Lỗi tìm kiếm sản phẩm');
          setProducts([]);
          setTotalProducts(0);
          setSearchSuggestions([]);
          setSuggestedCategories([]);
          setNanoaiTextProducts([]);
          setNanoaiTextLoading(false);
          setNanoaiTextError(null);
        } finally {
          setLoading(false);
        }
      })();
    } else {
      setSearchSuggestions([]);
      setSuggestedCategories([]);
      setNanoaiTextProducts([]);
      setNanoaiTextLoading(false);
      setNanoaiTextError(null);
    }
  }, [qFromUrl, shopIdFromUrl, shopNameFromUrl, proLowerFromUrl, proHighFromUrl, minPriceFromUrl, maxPriceFromUrl, currentPage]);

  useEffect(() => {
    const minFromUrl = parseNumberParam(minPriceFromUrl) ?? 0;
    const maxFromUrl = parseNumberParam(maxPriceFromUrl) ?? 10000000;
    if (minPriceFromUrl || maxPriceFromUrl) {
      setPriceRange([minFromUrl, maxFromUrl]);
    } else if (shopIdFromUrl || shopNameFromUrl || proLowerFromUrl || proHighFromUrl) {
      setPriceRange([0, 10000000]);
    }
  }, [shopIdFromUrl, shopNameFromUrl, proLowerFromUrl, proHighFromUrl, minPriceFromUrl, maxPriceFromUrl]);

  // Danh mục từ URL (thanh danh mục ở AppShell chuyển về trang chủ với ?category=...)
  const categoryFromUrl = searchParams.get('category') ?? undefined;
  const subcategoryFromUrl = searchParams.get('subcategory') ?? undefined;
  const subSubcategoryFromUrl = searchParams.get('sub_subcategory') ?? undefined;
  const hasFilterParams = Boolean(
    isSearching ||
      categoryFromUrl ||
      subcategoryFromUrl ||
      subSubcategoryFromUrl ||
      shopIdFromUrl ||
      shopNameFromUrl ||
      proLowerFromUrl ||
      proHighFromUrl ||
      minPriceFromUrl ||
      maxPriceFromUrl
  );

  useEffect(() => {
    if (qFromUrl.trim()) return;
    setSelectedFilter({
      category: categoryFromUrl,
      subcategory: subcategoryFromUrl,
      sub_subcategory: subSubcategoryFromUrl,
    });
    if (categoryFromUrl || subcategoryFromUrl || subSubcategoryFromUrl || shopIdFromUrl || shopNameFromUrl || proLowerFromUrl || proHighFromUrl || minPriceFromUrl || maxPriceFromUrl) {
      fetchProducts({
        category: categoryFromUrl,
        subcategory: subcategoryFromUrl,
        sub_subcategory: subSubcategoryFromUrl,
        shop_id: shopIdFromUrl,
        shop_name: shopNameFromUrl,
        pro_lower_price: proLowerFromUrl,
        pro_high_price: proHighFromUrl,
        min_price: parseNumberParam(minPriceFromUrl),
        max_price: parseNumberParam(maxPriceFromUrl),
      });
      return;
    }
    const skip = (currentPage - 1) * PAGE_SIZE;
    const ssrPage = initialPlainHome?.page ?? 1;
    const ssrOk = (initialPlainHome?.products?.length ?? 0) > 0 && initialPlainHome != null;

    if (ssrOk && currentPage === ssrPage) {
      setLoading(false);
      setApiStatus('online');
      setError(null);
      void apiClient
        .getPersonalizedHomeFeed(skip, PAGE_SIZE)
        .then((response) => {
          setProducts(response.products || []);
          setTotalProducts(response.total ?? (response.products?.length ?? 0));
          setHomeFeedPersonalized(Boolean(response.personalized));
          setApiStatus('online');
        })
        .catch(() => {
          setApiStatus('offline');
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
    proLowerFromUrl,
    proHighFromUrl,
    minPriceFromUrl,
    maxPriceFromUrl,
    qFromUrl,
    fetchProducts,
    user?.id,
    currentPage,
    initialPlainHome,
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
      pro_lower_price: proLowerFromUrl,
      pro_high_price: proHighFromUrl,
      min_price: minPriceFromUrl,
      max_price: maxPriceFromUrl,
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
      pro_lower_price: proLowerFromUrl,
      pro_high_price: proHighFromUrl,
      min_price: minPriceFromUrl,
      max_price: maxPriceFromUrl,
      page: currentPage,
    });
  }, [hasFilterParams, loading, categoryFromUrl, subcategoryFromUrl, subSubcategoryFromUrl, shopIdFromUrl, shopNameFromUrl, proLowerFromUrl, proHighFromUrl, minPriceFromUrl, maxPriceFromUrl, currentPage]);

  const totalPages = Math.max(1, Math.ceil(totalProducts / PAGE_SIZE));
  const setPage = (page: number) => {
    const next = Math.min(Math.max(1, page), totalPages);
    const params = new URLSearchParams(searchParams?.toString());
    if (next <= 1) {
      params.delete('page');
    } else {
      params.set('page', String(next));
    }
    router.push(`/?${params.toString()}`);
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

  const recommendationKey = `${isAuthenticated}-${user?.id ?? 'guest'}-${user?.gender ?? ''}-${
    user?.date_of_birth ?? ''
  }`;

  const [sameAgeGenderProducts, setSameAgeGenderProducts] = useState<Product[]>([]);
  const [sameAgeGenderLoading, setSameAgeGenderLoading] = useState(false);
  const [sameAgeGenderCohortMode, setSameAgeGenderCohortMode] = useState<SameAgeGenderCohortMode | null>(null);
  const [sameAgeGenderPanelOpen, setSameAgeGenderPanelOpen] = useState(false);
  const [sameShopProducts, setSameShopProducts] = useState<Product[]>([]);
  const [sameShopTotal, setSameShopTotal] = useState(0);
  const [sameShopSeed, setSameShopSeed] = useState<number | null>(null);
  const [sameShopLoading, setSameShopLoading] = useState(false);
  const [sameShopLoadMoreLoading, setSameShopLoadMoreLoading] = useState(false);
  const sameShopHasMore = sameShopProducts.length < sameShopTotal && sameShopTotal > 0;
  const lastSearchTrackedRef = useRef<string>('');
  const lastFilterTrackedRef = useRef<string>('');

  useEffect(() => {
    if (!isAuthenticated) {
      setSameAgeGenderProducts([]);
      setSameAgeGenderCohortMode('requires_login');
      setSameAgeGenderLoading(false);
      return;
    }
    let cancelled = false;
    setSameAgeGenderLoading(true);
    apiClient
      .getProductsViewedBySameAgeGender(24)
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
  }, [isAuthenticated, recommendationKey]);

  useEffect(() => {
    setSameShopLoading(true);
    apiClient.getProductsSameShopAsRecentViews(60, 0)
      .then(({ products, total, seed }) => {
        setSameShopProducts(products || []);
        setSameShopTotal(total ?? 0);
        setSameShopSeed(seed ?? null);
      })
      .catch(() => {
        setSameShopProducts([]);
        setSameShopTotal(0);
        setSameShopSeed(null);
      })
      .finally(() => setSameShopLoading(false));
  }, [recommendationKey]);

  const loadMoreSameShop = useCallback(() => {
    if (!sameShopHasMore || sameShopLoadMoreLoading) return;
    setSameShopLoadMoreLoading(true);
    apiClient.getProductsSameShopAsRecentViews(60, sameShopProducts.length, sameShopSeed ?? undefined)
      .then(({ products }) => {
        setSameShopProducts((prev) => [...prev, ...(products || [])]);
      })
      .finally(() => setSameShopLoadMoreLoading(false));
  }, [sameShopHasMore, sameShopLoadMoreLoading, sameShopProducts.length, sameShopSeed]);

  const sameShopSentinelRef = useRef<HTMLDivElement>(null);
  const sameShopLoadingRef = useRef(false);
  sameShopLoadingRef.current = sameShopLoadMoreLoading;
  useEffect(() => {
    if (!sameShopHasMore || sameShopProducts.length === 0) return;
    const el = sameShopSentinelRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting || sameShopLoadingRef.current) return;
        loadMoreSameShop();
      },
      { rootMargin: '200px', threshold: 0.1 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [sameShopHasMore, sameShopProducts.length, loadMoreSameShop]);

  const handleFavorite = async (productId: number, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const product =
      filteredProducts.find((p) => p.id === productId) ??
      products.find((p) => p.id === productId) ??
      sameShopProducts.find((p) => p.id === productId) ??
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

  const sameAgeGenderExplain = sameAgeGenderSectionDescription(sameAgeGenderCohortMode, sameAgeGenderLoading);

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
              onClick={() => fetchProducts()}
              className="flex-shrink-0 bg-red-500 text-white px-4 py-2.5 rounded-lg text-sm font-medium hover:bg-red-600 transition-colors shadow-sm"
            >
              Thử lại
            </button>
          </div>
        )}

        {/* Mobile: banner KM — ẩn khi đang tìm kiếm / lọc (trang kết quả) */}
        {!hasFilterParams && <MobilePromoBanner />}

        {hasFilterParams && (
          <section className="mb-6">
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
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-4">
                  {filteredProducts.map((product, index) => (
                    <SimpleProductCard
                      key={product.id}
                      product={product}
                      onFavorite={handleFavorite}
                      isFavorited={favoriteIds.has(product.id)}
                      priority={index < 6}
                    />
                  ))}
                </div>
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
              <div className="mt-6 flex flex-wrap items-center justify-between gap-3 text-sm">
                <p className="text-gray-600">
                  Trang {currentPage} / {totalPages} — Tổng {totalProducts} sản phẩm
                </p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setPage(currentPage - 1)}
                    disabled={currentPage <= 1}
                    className="px-3 py-2 rounded-lg border border-gray-200 text-gray-700 disabled:opacity-50 hover:bg-gray-50"
                  >
                    Trang trước
                  </button>
                  <button
                    type="button"
                    onClick={() => setPage(currentPage + 1)}
                    disabled={currentPage >= totalPages}
                    className="px-3 py-2 rounded-lg border border-gray-200 text-gray-700 disabled:opacity-50 hover:bg-gray-50"
                  >
                    Trang sau
                  </button>
                </div>
              </div>
            )}
          </section>
        )}

        {/* Hero Banner - desktop + tablet */}
        {!hasFilterParams && (
          <div className="hidden md:block mb-10 rounded-2xl overflow-hidden shadow-xl border border-gray-100">
          <div className="relative bg-gradient-to-br from-[#ea580c] via-orange-500 to-amber-600 h-52 md:h-72 flex items-center justify-center text-white">
            <div className="absolute inset-0 bg-black/5" />
            <div className="relative text-center px-6">
              <h2 className="text-2xl md:text-4xl font-bold tracking-tight mb-2 drop-shadow-sm">
                188.COM.VN
              </h2>
              <p className="text-base md:text-lg text-white/95 font-medium mb-1">
                Xem là thích — Mua sắm tin cậy
              </p>
              {/* Cố định copy: tránh CLS khi tổng SP thay đổi sau refetch personalized feed. */}
              <p className="text-sm text-white">
                Mua sắm khám phá toàn cửa hàng
                {apiStatus === 'online' ? (
                  <>
                    {' '}
                    <span aria-hidden className="text-white/95">
                      ·
                    </span>{' '}
                    <span className="text-white/95">Kết nối ổn định</span>
                  </>
                ) : null}
              </p>
            </div>
          </div>
          </div>
        )}

        {/* Cùng shop_name (Excel cột H) với shop của tối đa 8 SP xem gần; random mỗi lần mở khi không gửi seed */}
        {!hasFilterParams && (
          <section className="mb-8" id="san-pham-cung-shop">
          <h2 className="text-base font-bold text-gray-900 mb-2 border-b-2 border-[#ea580c] pb-1 w-fit">
            SẢN PHẨM CÙNG SHOP BẠN VỪA XEM
          </h2>
          <p className="text-sm text-gray-600 mt-1">
            Gợi ý từ shop (shop_name trong dữ liệu import) dựa trên tối đa 8 sản phẩm bạn xem gần nhất — thứ tự
            được trộn ngẫu nhiên mỗi lần mở trang chủ.
          </p>
          <div className="mt-4 min-h-[min(28rem,75vh)]">
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
            ) : sameShopProducts.length > 0 ? (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-4">
                  {sameShopProducts.map((product, index) => (
                    <SimpleProductCard
                      key={product.id}
                      product={product}
                      onFavorite={handleFavorite}
                      isFavorited={favoriteIds.has(product.id)}
                      priority={index < 4}
                    />
                  ))}
                </div>
                {sameShopHasMore && (
                  <>
                    <div ref={sameShopSentinelRef} className="h-4 w-full" aria-hidden />
                    <div className="flex justify-center py-6">
                      <button
                        type="button"
                        onClick={loadMoreSameShop}
                        disabled={sameShopLoadMoreLoading}
                        className="bg-[#ea580c] hover:bg-[#c2410c] disabled:opacity-60 text-white px-6 py-2.5 rounded-xl font-medium transition-colors text-sm shadow-sm"
                      >
                        {sameShopLoadMoreLoading ? 'Đang tải...' : 'Xem thêm'}
                      </button>
                    </div>
                  </>
                )}
              </>
            ) : null}
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
                      priority={index < 4 && sameShopProducts.length === 0}
                    />
                  ))}
                </div>
                {showPagination && (
                  <div className="mt-6 flex flex-wrap items-center justify-between gap-3 text-sm">
                    <p className="text-gray-600">
                      Trang {currentPage} / {totalPages} — Tổng {totalProducts} sản phẩm
                    </p>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setPage(currentPage - 1)}
                        disabled={currentPage <= 1}
                        className="px-3 py-2 rounded-lg border border-gray-200 text-gray-700 disabled:opacity-50 hover:bg-gray-50"
                      >
                        Trang trước
                      </button>
                      <button
                        type="button"
                        onClick={() => setPage(currentPage + 1)}
                        disabled={currentPage >= totalPages}
                        className="px-3 py-2 rounded-lg border border-gray-200 text-gray-700 disabled:opacity-50 hover:bg-gray-50"
                      >
                        Trang sau
                      </button>
                    </div>
                  </div>
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

        {/* Section Đề xuất theo tuổi và giới tính — bật đầy đủ sau khi đăng nhập và lưu ngày sinh + giới tính */}
        {!hasFilterParams && (
          <section className="mb-6">
            <h2 className="text-base font-bold text-gray-900 mb-2 border-b-2 border-[#ea580c] pb-1 w-fit">
              SẢN PHẨM ĐỀ XUẤT THEO TUỔI VÀ GIỚI TÍNH
            </h2>
            {sameAgeGenderExplain ? (
              <p className="text-sm text-gray-600 mt-1 max-w-2xl">{sameAgeGenderExplain}</p>
            ) : null}

            {!sameAgeGenderLoading && sameAgeGenderCohortMode === 'requires_login' ? (
              <div className="mt-3 flex flex-wrap gap-3">
                <Link
                  href="/auth/login"
                  className="inline-flex items-center justify-center bg-[#ea580c] text-white text-sm font-semibold px-4 py-2.5 rounded-lg hover:bg-[#c2410c] transition-colors"
                >
                  Đăng nhập
                </Link>
              </div>
            ) : null}

            {!sameAgeGenderLoading && sameAgeGenderCohortMode === 'profile_incomplete' ? (
              <div className="mt-3 flex flex-wrap gap-3">
                <Link
                  href="/account/profile"
                  className="inline-flex items-center justify-center bg-[#ea580c] text-white text-sm font-semibold px-4 py-2.5 rounded-lg hover:bg-[#c2410c] transition-colors"
                >
                  Cập nhật ngày sinh và giới tính
                </Link>
              </div>
            ) : null}

            {!sameAgeGenderLoading &&
            isAuthenticated &&
            sameAgeGenderProducts.length > 0 &&
            sameAgeGenderCohortMode !== 'profile_incomplete' &&
            sameAgeGenderCohortMode !== 'requires_login' ? (
              <Link
                href="/account/profile"
                className="inline-block mt-2 text-xs text-[#ea580c] font-medium hover:underline"
              >
                Chỉnh sửa ngày sinh / giới tính
              </Link>
            ) : null}

            <div className="mt-4">
              {sameAgeGenderLoading ? (
                <div className="flex flex-col gap-2">
                  {[0, 1].map((rowIndex) => (
                    <div key={rowIndex} className="flex gap-2 overflow-x-auto scrollbar-hide -mx-4 px-4 py-1">
                      {[...Array(6)].map((_, i) => (
                        <div key={i} className="flex-shrink-0 w-24 h-24 md:w-28 md:h-28 rounded-lg bg-gray-100 animate-pulse" />
                      ))}
                    </div>
                  ))}
                </div>
              ) : sameAgeGenderProducts.length > 0 ? (
              <>
                <div className="flex flex-col gap-2">
                  {[0, 1].map((rowIndex) => {
                    const start = rowIndex * Math.ceil(sameAgeGenderProducts.length / 2);
                    const rowProducts = sameAgeGenderProducts.slice(
                      start,
                      start + Math.ceil(sameAgeGenderProducts.length / 2)
                    );
                    return (
                      <div
                        key={rowIndex}
                        className="flex gap-2 overflow-x-auto scrollbar-hide -mx-4 px-4 py-1"
                      >
                        {rowProducts.map((product) => {
                          const imgUrl = getOptimizedImage(product.main_image, {
                            width: 160,
                            height: 160,
                            quality: 80,
                            fallbackStrategy: 'local',
                          });
                          return (
                            <button
                              key={product.id}
                              type="button"
                              onClick={() => setSameAgeGenderPanelOpen(true)}
                              className="flex-shrink-0 w-24 h-24 md:w-28 md:h-28 rounded-lg overflow-hidden border border-gray-200 shadow-sm hover:shadow-md hover:scale-[1.02] transition-all focus:outline-none focus:ring-2 focus:ring-[#ea580c] focus:ring-offset-1"
                            >
                              <Image
                                src={imgUrl}
                                alt=""
                                width={112}
                                height={112}
                                className="object-cover w-full h-full"
                              />
                            </button>
                          );
                        })}
                      </div>
                    );
                  })}
                </div>

                {sameAgeGenderPanelOpen && (
                  <>
                    <button
                      type="button"
                      aria-label="Đóng"
                      className="fixed inset-0 bg-black/50 z-40"
                      onClick={() => setSameAgeGenderPanelOpen(false)}
                    />
                    <div className="fixed left-0 right-0 top-1/2 -translate-y-1/2 z-50 max-h-[85vh] overflow-hidden mx-4 rounded-xl bg-white shadow-2xl border border-gray-200 flex flex-col">
                      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gray-50 rounded-t-xl">
                        <h3 className="text-base font-bold text-gray-900">
                          {sameAgeGenderPanelTitle(sameAgeGenderCohortMode)}
                        </h3>
                        <button
                          type="button"
                          onClick={() => setSameAgeGenderPanelOpen(false)}
                          className="p-2 rounded-full hover:bg-gray-200 text-gray-600"
                          aria-label="Đóng"
                        >
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                      <div className="overflow-y-auto flex-1 p-4">
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
                          {sameAgeGenderProducts.map((product) => {
                            const imgUrl = getOptimizedImage(product.main_image, {
                              width: 200,
                              height: 200,
                              quality: 85,
                              fallbackStrategy: 'local',
                            });
                            return (
                              <Link
                                key={product.id}
                                href={`/products/${product.slug || product.id}`}
                                onClick={() => setSameAgeGenderPanelOpen(false)}
                                className="bg-white rounded-xl border border-gray-100 overflow-hidden hover:shadow-md transition-shadow"
                              >
                                <div className="aspect-square bg-gray-50 relative">
                                  <Image
                                    src={imgUrl}
                                    alt={product.name}
                                    width={200}
                                    height={200}
                                    className="object-cover w-full h-full"
                                  />
                                </div>
                                <div className="p-2">
                                  <p className="text-xs font-medium text-gray-900 line-clamp-2 min-h-[2rem]">
                                    {product.name}
                                  </p>
                                  <p className="text-sm font-bold text-[#ea580c] mt-0.5">
                                    {formatPrice(product.price)}
                                  </p>
                                </div>
                              </Link>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  </>
                )}
              </>
            ) : null}
            </div>
          </section>
        )}

      </main>
    </div>
  );
}
