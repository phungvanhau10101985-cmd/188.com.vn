/**
 * Server-side helper cho SEO cluster (`/c/<slug>`).
 *
 * Cluster gom các cat3 trùng ý định tìm kiếm về 1 landing duy nhất (URL chính được Google index).
 * Cat3 cũ (`/danh-muc/.../<cat3>`) đã bị disable ở UI; nếu Google còn giữ trong index, route
 * `/danh-muc/[[...slug]]/page.tsx` redirect 301 sang `/c/<cluster_slug>` qua API mapping này.
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001/api/v1";

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

/** Trả null nếu cluster không tồn tại — caller dùng `notFound()`. */
export async function getSeoClusterDetail(slug: string): Promise<SeoClusterDetail | null> {
  try {
    const res = await fetch(`${API_BASE}/seo-clusters/${encodeURIComponent(slug)}`, {
      next: { revalidate: REVALIDATE_TTL, tags: [SEO_CLUSTER_TAG] },
      headers: { "Content-Type": "application/json" },
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
  options: { skip?: number; limit?: number } = {},
): Promise<SeoClusterPagedProducts> {
  const skip = options.skip ?? 0;
  const limit = options.limit ?? 48;
  try {
    const url = `${API_BASE}/seo-clusters/${encodeURIComponent(slug)}/products?skip=${skip}&limit=${limit}`;
    const res = await fetch(url, {
      next: { revalidate: REVALIDATE_TTL, tags: [SEO_CLUSTER_TAG] },
      headers: { "Content-Type": "application/json" },
    });
    if (!res.ok) return { total: 0, skip, limit, products: [] };
    return (await res.json()) as SeoClusterPagedProducts;
  } catch {
    return { total: 0, skip, limit, products: [] };
  }
}

export async function listSeoClusters(): Promise<SeoClusterListItem[]> {
  try {
    const res = await fetch(`${API_BASE}/seo-clusters/`, {
      next: { revalidate: REVALIDATE_TTL, tags: [SEO_CLUSTER_TAG] },
      headers: { "Content-Type": "application/json" },
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
    const res = await fetch(`${API_BASE}/categories/tree-v2`, {
      next: { revalidate: REVALIDATE_TTL, tags: [SEO_CLUSTER_TAG] },
      headers: { "Content-Type": "application/json" },
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
