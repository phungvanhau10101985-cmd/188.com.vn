/**
 * Server-side helper cho Ladipage public.
 * Ladipage 1 SP: nội dung bổ sung trên PDP `/products/...` (không dùng URL /lp/ riêng).
 */

import { cache } from 'react';
import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';
import { sortProductsByIds } from '@/lib/ladipage-utils';
import type { LadipageSection } from '@/lib/admin-api';
import type { Product } from '@/types/api';

export interface LadipagePublicDetail {
  id: number;
  slug: string;
  title: string;
  meta_title?: string | null;
  meta_description?: string | null;
  material_filter?: string | null;
  category_id?: number | null;
  category_name?: string | null;
  category_catalog_path?: string | null;
  category_seo_path?: string | null;
  sections: LadipageSection[];
  resolved_product_ids: number[];
}

export interface LadipageRelatedItem {
  id: number;
  slug: string;
  title: string;
  material_filter?: string | null;
  path: string;
  meta_title?: string | null;
}

/** Ladipage danh mục đã publish — link chéo từ danh mục/cluster. */
export async function listRelatedPublishedLadipages(opts: {
  categoryId?: number;
  categoryPath?: string;
  clusterSlug?: string;
  limit?: number;
  excludeId?: number;
}): Promise<LadipageRelatedItem[]> {
  try {
    const sp = new URLSearchParams();
    if (opts.categoryId) sp.set('category_id', String(opts.categoryId));
    if (opts.categoryPath) sp.set('category_path', opts.categoryPath);
    if (opts.clusterSlug) sp.set('cluster_slug', opts.clusterSlug);
    if (opts.limit) sp.set('limit', String(opts.limit));
    if (opts.excludeId) sp.set('exclude_id', String(opts.excludeId));
    const res = await fetch(`${getApiBaseUrl()}/ladipages/public/related?${sp.toString()}`, {
      next: { revalidate: 600 },
      headers: { 'Content-Type': 'application/json', ...ngrokFetchHeaders() },
    });
    if (!res.ok) return [];
    const data = (await res.json()) as { items?: LadipageRelatedItem[] };
    return Array.isArray(data.items) ? data.items : [];
  } catch {
    return [];
  }
}

/** Ladipage 1 SP đã publish — null nếu không có. */
export async function getPublishedLadipageForProduct(
  productDbId: number,
  opts?: { fallbackSlug?: string | null },
): Promise<LadipagePublicDetail | null> {
  if (!Number.isFinite(productDbId) || productDbId <= 0) {
    return opts?.fallbackSlug ? getPublicLadipage(opts.fallbackSlug) : null;
  }

  try {
    const res = await fetch(`${getApiBaseUrl()}/ladipages/public/by-product/${productDbId}`, {
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', ...ngrokFetchHeaders() },
    });
    if (res.ok) {
      return (await res.json()) as LadipagePublicDetail;
    }
  } catch {
    /* fallback slug bên dưới */
  }

  if (opts?.fallbackSlug) {
    return getPublicLadipage(opts.fallbackSlug);
  }
  return null;
}

/** Trả null nếu ladipage không tồn tại hoặc chưa publish — caller dùng `notFound()`. */
export async function getPublicLadipage(slug: string): Promise<LadipagePublicDetail | null> {
  try {
    const res = await fetch(`${getApiBaseUrl()}/ladipages/public/${encodeURIComponent(slug)}`, {
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', ...ngrokFetchHeaders() },
    });
    if (res.status === 404) return null;
    if (!res.ok) return null;
    return (await res.json()) as LadipagePublicDetail;
  } catch {
    return null;
  }
}

const getPublishedLadipageForProductCached = cache(
  async (productDbId: number, fallbackSlug?: string | null): Promise<LadipagePublicDetail | null> =>
    getPublishedLadipageForProduct(productDbId, { fallbackSlug }),
);

export async function getPublishedLadipageForProductRecord(
  product: Pick<Product, 'id' | 'published_ladipage_slug'>,
): Promise<LadipagePublicDetail | null> {
  // API sản phẩm đã đính kèm slug ladipage khi có. Đa số sản phẩm không có
  // ladipage, nên không gọi thêm endpoint (no-store) chỉ để nhận 404 trước
  // khi PDP có thể render.
  if (!product.published_ladipage_slug?.trim()) return null;

  return getPublishedLadipageForProductCached(product.id, product.published_ladipage_slug);
}

/** Server-side: lấy full product theo id (khoá chính). */
export async function getProductByIdForSeo(id: number): Promise<Product | null> {
  try {
    const res = await fetch(`${getApiBaseUrl()}/products/by-id/${id}`, {
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', ...ngrokFetchHeaders() },
    });
    if (!res.ok) return null;
    return (await res.json()) as Product;
  } catch {
    return null;
  }
}

/** Server-side: lấy nhiều product theo id — SEO + SSR lưới sản phẩm trên ladipage. */
export async function getProductsByIdsForSeo(ids: number[], limit = 60): Promise<Product[]> {
  const unique = [...new Set(ids)].slice(0, limit);
  const results = await Promise.all(unique.map((id) => getProductByIdForSeo(id)));
  return sortProductsByIds(results.filter((p): p is Product => p != null), unique);
}

export interface LadipageSitemapEntry {
  slug: string;
  updated_at?: string | null;
  published_at?: string | null;
}

/** Danh sách ladipage đã publish cho sitemap.xml (không gồm ladipage 1 SP). */
export async function listPublishedLadipagesForSitemap(): Promise<LadipageSitemapEntry[]> {
  try {
    const res = await fetch(`${getApiBaseUrl()}/ladipages/public/sitemap`, {
      next: { revalidate: 3600 },
      headers: { 'Content-Type': 'application/json', ...ngrokFetchHeaders() },
    });
    if (!res.ok) return [];
    const data = (await res.json()) as { items?: LadipageSitemapEntry[] };
    return data.items ?? [];
  } catch {
    return [];
  }
}
