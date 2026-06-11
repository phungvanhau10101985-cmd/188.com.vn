'use client';

import { createContext, useContext, type ReactNode } from 'react';
import type { CategoryLevel1 } from '@/types/api';

const AppCategoryTreeContext = createContext<CategoryLevel1[]>([]);

export function AppCategoryTreeProvider({
  tree,
  children,
}: {
  tree: CategoryLevel1[];
  children: ReactNode;
}) {
  return (
    <AppCategoryTreeContext.Provider value={tree}>{children}</AppCategoryTreeContext.Provider>
  );
}

/** Cây danh mục SSR từ layout — tránh fetch lại trên PDP. */
export function useAppCategoryTreeBase(): CategoryLevel1[] {
  return useContext(AppCategoryTreeContext);
}
