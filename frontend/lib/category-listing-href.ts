/**
 * URL listing danh mục / cluster SEO.
 * Cấp 3 index trên `/c/<cluster>`; `/danh-muc/.../<cat3>` chỉ còn fallback 301.
 */
import type { CategoryLevel3, HeroCategoryTile } from '@/types/api';
import { categorySegmentForUrl } from '@/lib/category-url';

/** Cluster 0 SP không đưa Google index. */
export const MIN_CLUSTER_INDEX_PRODUCTS = 1;

export function isSeoClusterIndexable(cluster: {
  index_policy?: string | null;
  product_count?: number | null;
  indexable?: boolean | null;
}): boolean {
  if (typeof cluster.indexable === 'boolean') return cluster.indexable;
  if ((cluster.index_policy || 'index').trim().toLowerCase() === 'noindex') return false;
  return (cluster.product_count ?? 0) >= MIN_CLUSTER_INDEX_PRODUCTS;
}

export function categoryLevel1Href(slug1: string): string {
  return `/danh-muc/${encodeURIComponent(slug1)}`;
}

export function categoryLevel2Href(slug1: string, slug2: string): string {
  return `/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}`;
}

export function categoryLevel3ListingHref(opts: {
  slug1: string;
  slug2: string;
  slug3: string;
  clusterSlug?: string | null;
}): string {
  const cluster = (opts.clusterSlug || '').trim();
  if (cluster) return `/c/${encodeURIComponent(cluster)}`;
  return `/danh-muc/${encodeURIComponent(opts.slug1)}/${encodeURIComponent(opts.slug2)}/${encodeURIComponent(opts.slug3)}`;
}

export function clusterSlugOfLevel3(level3: CategoryLevel3 | string | null | undefined): string | null {
  if (!level3 || typeof level3 === 'string') return null;
  const s = (level3.cluster_slug || '').trim();
  return s || null;
}

export function categoryLevel3HrefFromNode(
  slug1: string,
  slug2: string,
  level3: CategoryLevel3 | string,
): string {
  if (typeof level3 === 'string') {
    const slug3 = categorySegmentForUrl(level3);
    return categoryLevel3ListingHref({ slug1, slug2, slug3 });
  }
  const slug3 = categorySegmentForUrl(level3.slug) || categorySegmentForUrl(level3.name);
  return categoryLevel3ListingHref({
    slug1,
    slug2,
    slug3,
    clusterSlug: clusterSlugOfLevel3(level3),
  });
}

export function categoryTileHref(tile: HeroCategoryTile): string {
  const s1 = categorySegmentForUrl(tile.category);
  if (!s1) return '/';
  const s2 = categorySegmentForUrl(tile.subcategory || tile.name);
  if (tile.level === 2) return categoryLevel2Href(s1, s2);
  const s3 = categorySegmentForUrl(tile.sub_subcategory || tile.name);
  return categoryLevel3ListingHref({
    slug1: s1,
    slug2: s2,
    slug3: s3,
    clusterSlug: tile.cluster_slug,
  });
}
