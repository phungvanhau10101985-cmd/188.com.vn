/**
 * Server-side: lấy thông tin danh mục theo path cho SEO (generateMetadata, JSON-LD).
 * Và lấy cây danh mục 3 cấp cho thanh Navigation (tránh phụ thuộc fetch client/CORS).
 */

import type { CategoryLevel1 } from "@/types/api";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001/api/v1";
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || process.env.NEXT_PUBLIC_DOMAIN || "https://188.com.vn";

/** Tránh treo SSR khi backend tắt / mạng chặn (Windows hay gặp). */
const LAYOUT_FETCH_TIMEOUT_MS = 8000;

/** Trong development hoặc khi set DISABLE_CACHE=1: không cache để thấy thay đổi ngay. Production: cache 2–5 phút. */
const isDev = process.env.NODE_ENV === "development";
const disableCache = process.env.NEXT_PUBLIC_DISABLE_CACHE === "1" || process.env.DISABLE_CACHE === "1";
const REVALIDATE_CATEGORY = isDev || disableCache ? 0 : 120;
const REVALIDATE_SEO_DATA = isDev || disableCache ? 0 : 300;

/** Tag dùng cho revalidateTag() khi admin bấm "Xóa sạch cache". */
export const CACHE_TAG_CATEGORY_SEO = "category-seo";

/** Trạng thái SEO cho một path danh mục: mỗi ý định chỉ SEO một trang. */
export interface CategorySeoStatus {
  should_redirect: boolean;
  redirect_to: string | null;
  seo_indexable: boolean;
  canonical_url: string | null;
}

/**
 * Server-side: kiểm tra path danh mục có được SEO (index) hay không.
 * Trang cùng ý định nhưng không phải canonical → seo_indexable=false, canonical_url trỏ về trang chính.
 */
export async function getCategorySeoStatus(
  level1: string,
  level2?: string | null,
  level3?: string | null
): Promise<CategorySeoStatus> {
  const parts = [level1.trim()];
  if (level2?.trim()) parts.push(level2.trim());
  if (level3?.trim()) parts.push(level3.trim());
  const path = parts.join("/");
  try {
    const url = `${API_BASE}/category-seo/check-redirect?path=${encodeURIComponent(path)}`;
    const res = await fetch(url, {
      next: { revalidate: REVALIDATE_CATEGORY, tags: [CACHE_TAG_CATEGORY_SEO] },
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.timeout(LAYOUT_FETCH_TIMEOUT_MS),
    });
    if (!res.ok)
      return {
        should_redirect: false,
        redirect_to: null,
        seo_indexable: true,
        canonical_url: null,
      };
    const data = (await res.json()) as CategorySeoStatus;
    return {
      should_redirect: data.should_redirect ?? false,
      redirect_to: data.redirect_to ?? null,
      seo_indexable: data.seo_indexable !== false,
      canonical_url: data.canonical_url ?? null,
    };
  } catch {
    return {
      should_redirect: false,
      redirect_to: null,
      seo_indexable: true,
      canonical_url: null,
    };
  }
}

/** Server-side: lấy cây danh mục 3 cấp từ API (dùng trong layout để thanh danh mục luôn có dữ liệu). */
export async function getCategoryTreeForLayout(): Promise<CategoryLevel1[]> {
  try {
    const url = `${API_BASE}/categories/from-products`;
    const res = await fetch(url, {
      next: { revalidate: REVALIDATE_CATEGORY, tags: [CACHE_TAG_CATEGORY_SEO] },
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.timeout(LAYOUT_FETCH_TIMEOUT_MS),
    });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? (data as CategoryLevel1[]) : [];
  } catch {
    return [];
  }
}

export interface CategoryByPathInfo {
  level: 1 | 2 | 3;
  name: string;
  full_name: string;
  breadcrumb_names: string[];
  product_count: number;
}

export interface CategorySeoData extends CategoryByPathInfo {
  images: string[];  // 4 ảnh sản phẩm đầu tiên cho og:image
  seo_description: string | null;  // Mô tả SEO được viết bởi AI
  seo_body: string | null;  // Đoạn văn SEO 150-300 từ (cuối trang), do AI viết
}

export async function getCategoryByPathForSeo(
  level1: string,
  level2?: string | null,
  level3?: string | null
): Promise<CategoryByPathInfo | null> {
  try {
    const params = new URLSearchParams({ level1: level1.trim() });
    if (level2?.trim()) params.set("level2", level2.trim());
    if (level3?.trim()) params.set("level3", level3.trim());
    const url = `${API_BASE}/categories/from-products/by-path?${params.toString()}`;
    const res = await fetch(url, {
      next: { revalidate: REVALIDATE_CATEGORY, tags: [CACHE_TAG_CATEGORY_SEO] },
      headers: { "Content-Type": "application/json" },
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data as CategoryByPathInfo;
  } catch {
    return null;
  }
}

/**
 * Lấy dữ liệu SEO đầy đủ cho danh mục bao gồm:
 * - Thông tin cơ bản
 * - 4 ảnh sản phẩm đầu tiên (cho og:image)
 * - Mô tả SEO được viết bởi AI
 */
export async function getCategorySeoData(
  level1: string,
  level2?: string | null,
  level3?: string | null
): Promise<CategorySeoData | null> {
  try {
    const params = new URLSearchParams({ level1: level1.trim() });
    if (level2?.trim()) params.set("level2", level2.trim());
    if (level3?.trim()) params.set("level3", level3.trim());
    const url = `${API_BASE}/categories/from-products/seo-data?${params.toString()}`;
    const res = await fetch(url, {
      next: { revalidate: REVALIDATE_SEO_DATA, tags: [CACHE_TAG_CATEGORY_SEO] },
      headers: { "Content-Type": "application/json" },
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data as CategorySeoData;
  } catch {
    return null;
  }
}

/** Server-side: lấy sản phẩm theo danh mục (cho SSR). Hỗ trợ phân trang qua skip/limit.
 *  Có thể truyền sẵn info danh mục (CategoryByPathInfo) để tránh gọi API by-path lần nữa.
 */
export async function getProductsByCategory(
  level1: string,
  level2?: string | null,
  level3?: string | null,
  options: { limit?: number; skip?: number } = {},
  resolvedInfo?: CategoryByPathInfo | null
): Promise<{
  products: unknown[];
  total: number;
  total_pages: number;
  page: number;
  category?: string;
  subcategory?: string;
  sub_subcategory?: string;
}> {
  const { limit = 96, skip = 0 } = options;
  const info = resolvedInfo ?? (await getCategoryByPathForSeo(level1, level2, level3));
  if (!info) return { products: [], total: 0, total_pages: 0, page: 1 };
  const breadcrumb = info.breadcrumb_names || [];
  const category = breadcrumb[0];
  const subcategory = breadcrumb[1];
  const sub_subcategory = breadcrumb[2];
  try {
    const params = new URLSearchParams({
      limit: String(limit),
      skip: String(skip),
      is_active: "true",
      category: category || level1,
    });
    if (subcategory) params.set("subcategory", subcategory);
    if (sub_subcategory) params.set("sub_subcategory", sub_subcategory);
    const url = `${API_BASE}/products/?${params.toString()}`;
    const res = await fetch(url, {
      next: { revalidate: REVALIDATE_CATEGORY, tags: [CACHE_TAG_CATEGORY_SEO] },
      headers: { "Content-Type": "application/json" },
    });
    if (!res.ok) {
      return { products: [], total: 0, total_pages: 0, page: 1, category, subcategory, sub_subcategory };
    }
    const data = (await res.json()) as {
      products?: unknown[];
      total?: number;
      total_pages?: number;
    };
    const total = typeof data.total === "number" ? data.total : (Array.isArray(data.products) ? data.products.length : 0);
    const totalPages = typeof data.total_pages === "number" ? data.total_pages : (limit > 0 ? Math.ceil(total / limit) : 1);
    const page = limit > 0 ? Math.floor(skip / limit) + 1 : 1;
    return {
      products: Array.isArray(data.products) ? data.products : [],
      total,
      total_pages: totalPages,
      page,
      category,
      subcategory,
      sub_subcategory,
    };
  } catch {
    return { products: [], total: 0, total_pages: 0, page: 1, category, subcategory, sub_subcategory };
  }
}

/** URL path danh mục (không có leading slash). */
export function categoryPath(level1: string, level2?: string, level3?: string): string {
  const parts = [level1];
  if (level2) parts.push(level2);
  if (level3) parts.push(level3);
  return parts.join("/");
}

export function buildCategoryBreadcrumbJsonLd(
  breadcrumbNames: string[],
  pathSegments: string[]
): object {
  const items = [
    { "@type": "ListItem", position: 1, name: "Trang chủ", item: SITE_URL },
    ...breadcrumbNames.map((name, i) => ({
      "@type": "ListItem" as const,
      position: i + 2,
      name,
      item: `${SITE_URL}/danh-muc/${pathSegments.slice(0, i + 1).join("/")}`,
    })),
  ];
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items,
  };
}

export function buildCategoryCollectionJsonLd(
  fullName: string,
  path: string,
  productCount: number,
  description: string
): object {
  return {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: fullName,
    description: description.slice(0, 500),
    url: `${SITE_URL}/danh-muc/${path}`,
    numberOfItems: productCount,
    isPartOf: { "@type": "WebSite", name: "188.com.vn", url: SITE_URL },
  };
}
