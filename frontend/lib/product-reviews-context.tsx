'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from 'react';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/features/auth/hooks/useAuth';
import type { ProductReviewItem } from '@/types/api';

type ProductReviewsContextValue = {
  reviews: ProductReviewItem[];
  loading: boolean;
  canReview: boolean;
  hasReviewed: boolean;
  setReviews: Dispatch<SetStateAction<ProductReviewItem[]>>;
  setHasReviewed: Dispatch<SetStateAction<boolean>>;
  refreshReviews: () => Promise<void>;
};

const ProductReviewsContext = createContext<ProductReviewsContextValue | null>(null);

export function ProductReviewsProvider({
  productId,
  children,
}: {
  productId: number;
  children: ReactNode;
}) {
  const { isAuthenticated } = useAuth();
  const [reviews, setReviews] = useState<ProductReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [canReview, setCanReview] = useState(false);
  const [hasReviewed, setHasReviewed] = useState(false);

  const refreshReviews = useCallback(async () => {
    if (!productId) return;
    try {
      const list = await apiClient.getProductReviews(productId);
      setReviews(Array.isArray(list) ? list : []);
    } catch {
      setReviews([]);
    }
  }, [productId]);

  useEffect(() => {
    if (!productId) {
      setReviews([]);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);

    refreshReviews()
      .catch(() => {
        if (!cancelled) setReviews([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [productId, refreshReviews]);

  useEffect(() => {
    if (!isAuthenticated || !productId) {
      setCanReview(false);
      setHasReviewed(false);
      return;
    }

    let cancelled = false;
    Promise.all([
      apiClient.canReviewProduct(productId).then((r) => r.can_review ?? false),
      apiClient
        .getUserReviewedProductIds([productId])
        .then((r) => (r.product_ids || []).includes(productId)),
    ])
      .then(([can, reviewed]) => {
        if (cancelled) return;
        setCanReview(can);
        setHasReviewed(reviewed);
      })
      .catch(() => {
        if (!cancelled) {
          setCanReview(false);
          setHasReviewed(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, productId]);

  const value = useMemo(
    () => ({
      reviews,
      loading,
      canReview,
      hasReviewed,
      setReviews,
      setHasReviewed,
      refreshReviews,
    }),
    [reviews, loading, canReview, hasReviewed, refreshReviews],
  );

  return (
    <ProductReviewsContext.Provider value={value}>{children}</ProductReviewsContext.Provider>
  );
}

export function useProductReviews(): ProductReviewsContextValue {
  const ctx = useContext(ProductReviewsContext);
  if (!ctx) {
    throw new Error('useProductReviews must be used within ProductReviewsProvider');
  }
  return ctx;
}
