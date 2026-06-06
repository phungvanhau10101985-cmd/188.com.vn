'use client';

import { useEffect, useMemo, useState } from 'react';
import { usePathname } from 'next/navigation';
import { apiClient } from '@/lib/api-client';
import { sortCategoryLevel1Tree } from '@/lib/category-tree-sort';
import { withKhoSaleMenuCategory } from '@/lib/kho-sale-menu-category';
import { useAuth } from '@/features/auth/hooks/useAuth';
import type { CategoryLevel1 } from '@/types/api';

/**
 * Cây danh mục đã sắp theo giới (Nam/Nữ) từ 8 SP xem gần nhất hoặc hồ sơ.
 * SSR vẫn trả cây alphabet; client reorder sau khi có inferred-gender.
 */
export function usePersonalizedCategoryTree(
  baseTree: CategoryLevel1[] | undefined,
): CategoryLevel1[] {
  const pathname = usePathname();
  const { user, isAuthenticated } = useAuth();
  const [genderSuffix, setGenderSuffix] = useState<string | null>(null);
  const [viewTick, setViewTick] = useState(0);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onView = () => setViewTick((t) => t + 1);
    window.addEventListener('188-product-viewed', onView);
    return () => window.removeEventListener('188-product-viewed', onView);
  }, []);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getInferredCategoryGender(8)
      .then((res) => {
        if (!cancelled) setGenderSuffix(res.gender_suffix);
      })
      .catch(() => {
        if (!cancelled) setGenderSuffix(null);
      });
    return () => {
      cancelled = true;
    };
  }, [pathname, isAuthenticated, user?.gender, viewTick]);

  return useMemo(
    () => withKhoSaleMenuCategory(sortCategoryLevel1Tree(baseTree || [], genderSuffix)),
    [baseTree, genderSuffix],
  );
}
