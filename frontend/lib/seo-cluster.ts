/**
 * Server-side helper cho SEO cluster (`/c/<slug>`).
 *
 * Cluster gom các cat3 trùng ý định tìm kiếm về 1 landing duy nhất (URL chính được Google index).
 * Cat3 cũ (`/danh-muc/.../<cat3>`) đã bị disable ở UI; nếu Google còn giữ trong index, route
 * `/danh-muc/[[...slug]]/page.tsx` redirect 301 sang `/c/<cluster_slug>` qua API mapping này.
 */

import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';

const REVALIDATE_TTL = process.env.NODE_ENV === "development" ? 0 : 120;
export const SEO_CLUSTER_TAG = "seo-clusters";

export interface SeoClusterListItem {
  id: number;
  slug: string;
  name: string;
  canonical_path: string;
  index_policy: "index" | "noindex" | string;
  product_count: number;
}

export interface SeoClusterCategorySummary {
  id: number;
  name: string;
  slug: string;
  full_slug: string;
}

export interface SeoClusterProductCard {
  id: number;
  product_id: string;
  name: string;
  slug: string;
  main_image: string | null;
  images: string[];
  price: number;
  pro_lower_price: string | null;
  pro_high_price: string | null;
  rating_point: number;
  rating_total: number;
  purchases: number;
  shop_name: string | null;
  available: number;
  brand_name: string | null;
}

export interface SeoClusterDetail {
  id: number;
  slug: string;
  name: string;
  canonical_path: string;
  index_policy: "index" | "noindex" | string;
  source: string | null;
  notes: string | null;
  categories: SeoClusterCategorySummary[];
  product_count: number;
  products_sample: SeoClusterProductCard[];
}

export interface SeoClusterPagedProducts {
  total: number;
  skip: number;
  limit: number;
  products: SeoClusterProductCard[];
}

export interface SeoClusterListingFilters {
  minPrice?: number | null;
  maxPrice?: number | null;
  size?: string | null;
  color?: string | null;
  styleTag?: string | null;
  sort?: string | null;
}

export interface SeoClusterProductFacets {
  sizes: string[];
  colors: string[];
  style_tags: string[];
  price_min: number | null;
  price_max: number | null;
}

function appendClusterFilters(params: URLSearchParams, filters?: SeoClusterListingFilters) {
  if (!filters) return;
  if (filters.minPrice != null && !Number.isNaN(filters.minPrice) && filters.minPrice >= 0) {
    params.set("min_price", String(filters.minPrice));
  }
  if (filters.maxPrice != null && !Number.isNaN(filters.maxPrice) && filters.maxPrice >= 0) {
    params.set("max_price", String(filters.maxPrice));
  }
  if (filters.size?.trim()) params.set("size", filters.size.trim());
  if (filters.color?.trim()) params.set("color", filters.color.trim());
  if (filters.styleTag?.trim()) params.set("style_tag", filters.styleTag.trim());
  if (filters.sort?.trim()) params.set("sort", filters.sort.trim());
}

/** Trả null nếu cluster không tồn tại — caller dùng `notFound()`. */
export async function getSeoClusterDetail(slug: string): Promise<SeoClusterDetail | null> {
  try {
    const res = await fetch(`${getApiBaseUrl()}/seo-clusters/${encodeURIComponent(slug)}`, {
      next: { revalidate: REVALIDATE_TTL, tags: [SEO_CLUSTER_TAG] },
      headers: { "Content-Type": "application/json", ...ngrokFetchHeaders() },
    });
    if (res.status === 404) return null;
    if (!res.ok) return null;
    return (await res.json()) as SeoClusterDetail;
  } catch {
    return null;
  }
}

export async function getSeoClusterProducts(
  slug: string,
  options: { skip?: number; limit?: number; filters?: SeoClusterListingFilters } = {},
): Promise<SeoClusterPagedProducts> {
  const skip = options.skip ?? 0;
  const limit = options.limit ?? 48;
  try {
    const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    appendClusterFilters(params, options.filters);
    const url = `${getApiBaseUrl()}/seo-clusters/${encodeURIComponent(slug)}/products?${params.toString()}`;
    const res = await fetch(url, {
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...ngrokFetchHeaders() },
    });
    if (!res.ok) return { total: 0, skip, limit, products: [] };
    return (await res.json()) as SeoClusterPagedProducts;
  } catch {
    return { total: 0, skip, limit, products: [] };
  }
}

export async function getSeoClusterFacets(
  slug: string,
  filters?: SeoClusterListingFilters,
): Promise<SeoClusterProductFacets | null> {
  try {
    const params = new URLSearchParams();
    appendClusterFilters(params, filters);
    const q = params.toString();
    const res = await fetch(`${getApiBaseUrl()}/seo-clusters/${encodeURIComponent(slug)}/facets${q ? `?${q}` : ""}`, {
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...ngrokFetchHeaders() },
    });
    if (!res.ok) return null;
    const data = (await res.json()) as Record<string, unknown>;
    return {
      sizes: Array.isArray(data.sizes) ? (data.sizes as string[]) : [],
      colors: Array.isArray(data.colors) ? (data.colors as string[]) : [],
      style_tags: Array.isArray(data.style_tags) ? (data.style_tags as string[]) : [],
      price_min: typeof data.price_min === "number" ? data.price_min : null,
      price_max: typeof data.price_max === "number" ? data.price_max : null,
    };
  } catch {
    return null;
  }
}

export async function listSeoClusters(): Promise<SeoClusterListItem[]> {
  try {
    const res = await fetch(`${getApiBaseUrl()}/seo-clusters/`, {
      next: { revalidate: REVALIDATE_TTL, tags: [SEO_CLUSTER_TAG] },
      headers: { "Content-Type": "application/json", ...ngrokFetchHeaders() },
    });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? (data as SeoClusterListItem[]) : [];
  } catch {
    return [];
  }
}

/**
 * Tra cluster_slug từ chuỗi cat3 slug (cột AD `Sub-subcategory`).
 * Dùng trong `/danh-muc/[[...slug]]/page.tsx` để 301 redirect cat3 → /c/<cluster>.
 *
 * Đọc từ tree-v2 (đã có cluster_slug ở cat3) để nhẹ + cache tốt.
 */
interface TreeV2Node {
  id: number;
  parent_id: number | null;
  level: number;
  name: string;
  slug: string;
  full_slug: string;
  cluster_slug: string | null;
  children?: TreeV2Node[];
}

async function fetchTreeV2(): Promise<TreeV2Node[]> {
  try {
    const res = await fetch(`${getApiBaseUrl()}/categories/tree-v2`, {
      next: { revalidate: REVALIDATE_TTL, tags: [SEO_CLUSTER_TAG] },
      headers: { "Content-Type": "application/json", ...ngrokFetchHeaders() },
    });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? (data as TreeV2Node[]) : [];
  } catch {
    return [];
  }
}

function flattenCat3(nodes: TreeV2Node[]): TreeV2Node[] {
  const out: TreeV2Node[] = [];
  const walk = (list: TreeV2Node[]) => {
    for (const n of list) {
      if (n.level === 3) out.push(n);
      if (n.children?.length) walk(n.children);
    }
  };
  walk(nodes);
  return out;
}

export async function getClusterSlugForCat3(cat3Slug: string): Promise<string | null> {
  if (!cat3Slug) return null;
  const target = cat3Slug.trim().toLowerCase();
  const tree = await fetchTreeV2();
  for (const c of flattenCat3(tree)) {
    if ((c.slug || "").toLowerCase() === target) {
      return c.cluster_slug || null;
    }
  }
  return null;
}
