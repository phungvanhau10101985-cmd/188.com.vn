'use client';

import type { AppRouterInstance } from 'next/dist/shared/lib/app-router-context.shared-runtime';

const prefetchedHrefs = new Set<string>();

/** Prefetch RSC payload PDP — dedupe theo href trong phiên tab. */
export function prefetchProductPdp(router: AppRouterInstance, href: string | null | undefined): void {
  const path = (href ?? '').trim();
  if (!path || path === '#' || !path.startsWith('/products/')) return;
  if (prefetchedHrefs.has(path)) return;
  prefetchedHrefs.add(path);
  try {
    router.prefetch(path);
  } catch {
    prefetchedHrefs.delete(path);
  }
}
