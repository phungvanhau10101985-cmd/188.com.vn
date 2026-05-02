'use client';

import Link from 'next/link';
import { useState, useEffect, useCallback, useRef } from 'react';
import { SimpleProductCard } from '@/components/ProductCard';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useFavorites } from '@/features/favorites/hooks/useFavorites';
import type { Product } from '@/types/api';

function favoritePayloadFromProduct(p: Product): Record<string, unknown> {
  return {
    name: p.name,
    main_image: p.main_image,
    price: p.price,
    slug: p.slug,
    product_id: p.product_id,
  };
}

/** Khối “SẢN PHẨM CÙNG SHOP BẠN VỪA XEM” như trang chủ — dùng khi giỏ hàng trống. */
export default function CartEmptySameShopSection() {
  const { isAuthenticated, user } = useAuth();
  const { refreshFavorites } = useFavorites();
  const recommendationKey = `${isAuthenticated}-${user?.id ?? 'guest'}-${user?.gender ?? ''}-${
    user?.date_of_birth ?? ''
  }`;

  const [favoriteIds, setFavoriteIds] = useState<Set<number>>(new Set());
  const [sameShopProducts, setSameShopProducts] = useState<Product[]>([]);
  const [sameShopTotal, setSameShopTotal] = useState(0);
  const [sameShopSeed, setSameShopSeed] = useState<number | null>(null);
  const [sameShopLoading, setSameShopLoading] = useState(false);
  const [sameShopLoadMoreLoading, setSameShopLoadMoreLoading] = useState(false);
  const sameShopHasMore = sameShopProducts.length < sameShopTotal && sameShopTotal > 0;

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

  useEffect(() => {
    setSameShopLoading(true);
    apiClient
      .getProductsSameShopAsRecentViews(60, 0)
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
    apiClient
      .getProductsSameShopAsRecentViews(60, sameShopProducts.length, sameShopSeed ?? undefined)
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
    const product = sameShopProducts.find((p) => p.id === productId);
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

  if (!sameShopLoading && sameShopTotal <= 0) {
    return null;
  }

  return (
    <section className="mt-8 md:mt-10 text-left" aria-label="Sản phẩm cùng shop bạn vừa xem">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3 mb-2">
        <h2 className="text-base font-bold text-gray-900 border-b-2 border-[#ea580c] pb-1 w-fit shrink-0">
          SẢN PHẨM CÙNG SHOP BẠN VỪA XEM
        </h2>
        {!sameShopLoading && (
          <Link
            href={
              sameShopSeed != null
                ? `/luot-video-cung-shop?seed=${sameShopSeed}`
                : '/luot-video-cung-shop'
            }
            className="inline-flex items-center justify-center gap-1.5 rounded-full bg-gradient-to-r from-[#ea580c] to-orange-600 text-white text-xs font-semibold px-3.5 py-2 shadow-md shrink-0 self-start sm:self-center min-h-[40px] active:scale-[0.98] transition-transform"
          >
            <svg className="w-4 h-4 shrink-0" fill="currentColor" viewBox="0 0 24 24" aria-hidden>
              <path d="M8 5v14l11-7z" />
            </svg>
            Lướt video
          </Link>
        )}
      </div>
      <p className="text-sm text-gray-600 mt-1">
        Gợi ý từ shop (shop_name trong dữ liệu import) dựa trên tối đa 8 sản phẩm bạn xem gần nhất — thứ tự
        được trộn ngẫu nhiên mỗi lần mở trang.
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
        ) : (
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
        )}
      </div>
    </section>
  );
}
