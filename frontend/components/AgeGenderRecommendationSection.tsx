'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { SimpleProductCard } from '@/components/ProductCard';
import SameShopRecommendationHeader from '@/components/home/SameShopRecommendationHeader';
import { apiClient } from '@/lib/api-client';
import { sameAgeGenderCompactHint } from '@/lib/same-age-gender-hint';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useFavorites } from '@/features/favorites/hooks/useFavorites';
import type { Product, SameAgeGenderCohortMode } from '@/types/api';

const DEFAULT_LIMIT = 24;

function favoritePayloadFromProduct(p: Product): Record<string, unknown> {
  return {
    name: p.name,
    main_image: p.main_image,
    price: p.price,
    slug: p.slug,
    product_id: p.product_id,
  };
}

type AgeGenderRecommendationSectionProps = {
  excludeProductId?: number;
  limit?: number;
  className?: string;
};

export default function AgeGenderRecommendationSection({
  excludeProductId,
  limit = DEFAULT_LIMIT,
  className = '',
}: AgeGenderRecommendationSectionProps) {
  const { isAuthenticated, user, isLoading: authLoading } = useAuth();
  const { refreshFavorites } = useFavorites();
  const [products, setProducts] = useState<Product[]>([]);
  const [cohortMode, setCohortMode] = useState<SameAgeGenderCohortMode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [favoriteIds, setFavoriteIds] = useState<Set<number>>(new Set());

  const profileKey = `${isAuthenticated}-${user?.id ?? 'guest'}-${user?.gender ?? ''}-${
    user?.date_of_birth ?? ''
  }`;

  const visibleProducts = useMemo(
    () =>
      excludeProductId != null
        ? products.filter((p) => p.id !== excludeProductId)
        : products,
    [products, excludeProductId]
  );

  const loadRecommendations = useCallback(() => {
    setLoading(true);
    setError(null);
    return apiClient
      .getProductsViewedBySameAgeGender(limit)
      .then(({ products: list, cohort_mode }) => {
        setProducts(list ?? []);
        setCohortMode(cohort_mode ?? 'requires_login');
      })
      .catch(() => {
        setProducts([]);
        setCohortMode('requires_login');
        setError('Không tải được gợi ý. Vui lòng thử lại.');
      })
      .finally(() => {
        setLoading(false);
      });
  }, [limit]);

  useEffect(() => {
    if (authLoading) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiClient
      .getProductsViewedBySameAgeGender(limit)
      .then(({ products: list, cohort_mode }) => {
        if (cancelled) return;
        setProducts(list ?? []);
        setCohortMode(cohort_mode ?? 'requires_login');
      })
      .catch(() => {
        if (cancelled) return;
        setProducts([]);
        setCohortMode('requires_login');
        setError('Không tải được gợi ý. Vui lòng thử lại.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [authLoading, profileKey, limit]);

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

  const hasCohortProductsForHeader =
    cohortMode != null &&
    cohortMode !== 'requires_login' &&
    cohortMode !== 'profile_incomplete' &&
    visibleProducts.length > 0;

  const hint = sameAgeGenderCompactHint(cohortMode, loading && isAuthenticated);

  const showSection =
    loading ||
    visibleProducts.length > 0 ||
    error != null ||
    (!authLoading &&
      (cohortMode === 'requires_login' || cohortMode === 'profile_incomplete'));

  const handleFavorite = async (productId: number, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const product = visibleProducts.find((p) => p.id === productId);
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

  if (!showSection) return null;

  return (
    <section className={className} id="san-pham-goi-y-tuoi-gioi">
      <SameShopRecommendationHeader
        cohortMode={cohortMode}
        cohortLoading={loading}
        isAuthenticated={isAuthenticated}
        hasCohortProducts={hasCohortProductsForHeader}
        hint={hint}
      />

      <div className="mt-3">
        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}{' '}
            <button
              type="button"
              onClick={() => void loadRecommendations()}
              className="font-medium underline"
            >
              Thử lại
            </button>
          </div>
        ) : loading ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-4">
            {[...Array(10)].map((_, i) => (
              <div
                key={i}
                className="overflow-hidden rounded-xl border border-gray-100 bg-white animate-pulse"
              >
                <div className="aspect-square bg-gray-100" />
                <div className="space-y-2 p-3">
                  <div className="h-3 w-3/4 rounded bg-gray-100" />
                  <div className="h-3 w-full rounded bg-gray-100" />
                  <div className="h-4 w-2/5 rounded bg-gray-100" />
                </div>
              </div>
            ))}
          </div>
        ) : visibleProducts.length > 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-4">
            {visibleProducts.map((product) => (
              <SimpleProductCard
                key={product.id}
                product={product}
                onFavorite={handleFavorite}
                isFavorited={favoriteIds.has(product.id)}
                showPersonalizedBadge
              />
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
