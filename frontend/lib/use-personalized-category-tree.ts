'use client';

import { useEffect, useMemo, useState } from 'react';
import { usePathname } from 'next/navigation';
import { sortCategoryLevel1Tree } from '@/lib/category-tree-sort';
import { withKhoSaleMenuCategory } from '@/lib/kho-sale-menu-category';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { readNavCategoryTreeCache } from '@/lib/nav-category-tree-cache';
import { useInferredCategoryGender } from '@/lib/use-inferred-category-gender';
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
  const [viewTick, setViewTick] = useState(0);
  const [cachedTree, setCachedTree] = useState<CategoryLevel1[]>([]);

  useEffect(() => {
    if ((baseTree?.length ?? 0) > 0) return;
    const cached = readNavCategoryTreeCache();
    if (cached.length > 0) setCachedTree(cached);
  }, [baseTree]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onView = () => setViewTick((t) => t + 1);
    window.addEventListener('188-product-viewed', onView);
    return () => window.removeEventListener('188-product-viewed', onView);
  }, []);

  const genderFetchKey = `${pathname}|${isAuthenticated}|${user?.gender ?? ''}|${viewTick}`;
  const genderSuffix = useInferredCategoryGender(genderFetchKey);

  const resolvedBase =
    (baseTree?.length ?? 0) > 0 ? baseTree! : cachedTree;

  return useMemo(
    () => withKhoSaleMenuCategory(sortCategoryLevel1Tree(resolvedBase, genderSuffix)),
    [resolvedBase, genderSuffix],
  );
}
