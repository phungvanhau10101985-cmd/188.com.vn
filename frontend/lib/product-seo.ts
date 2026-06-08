/**
 * Server-side only: lấy thông tin sản phẩm theo slug cho SEO (generateMetadata, JSON-LD).
 * Dùng trong layout/products/[slug] và generateMetadata.
 */
import type { Product } from "@/types/api";
import { cache } from "react";
import { displayableBrandWithDefault } from "@/lib/utils";
import { productPublicPdpUrl } from "@/lib/product-path-slug";
import { getApiBaseUrl } from "@/lib/api-base";
import { normalizeProductRouteSlug } from "@/lib/product-route-slug";

function apiBaseForProductFetch(): string {
  return getApiBaseUrl();
}

export interface ProductForSeo {
  id: number;
  product_id?: string;
  name: string;
  slug: string;
  price: number;
  original_price?: number;
  description?: string;
  main_image?: string;
  images?: string[];
  brand_name?: string;
  rating_point?: number;
  rating_total?: number;
  purchases?: number;
  available?: number;
  meta_title?: string | null;
  meta_description?: string | null;
  meta_keywords?: string | null;
  created_at?: string;
  updated_at?: string;
  category?: string;
  subcategory?: string;
  sub_subcategory?: string;
  raw_category?: string;
  raw_subcategory?: string;
}

async function fetchProductBySlug(
  normalized: string,
  opts: { attachGroupListing: boolean; noStore: boolean },
): Promise<Product | null> {
  try {
    const { attachGroupListing, noStore } = opts;
    const apiBase = apiBaseForProductFetch();
    const encoded = encodeURIComponent(normalized);
    const params = new URLSearchParams({ slug: normalized });
    if (attachGroupListing) {
      params.set("attach_group_listing", "true");
    }

    let res = await fetch(`${apiBase}/products/by-slug/?${params}`, {
      ...(noStore ? { cache: "no-store" as const } : { next: { revalidate: 60 } }),
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.timeout(15_000),
    });
    if (!res.ok) {
      const attachQs = attachGroupListing ? "?attach_group_listing=true" : "";
      res = await fetch(`${apiBase}/products/by-slug/${encoded}${attachQs}`, {
        ...(noStore ? { cache: "no-store" as const } : { next: { revalidate: 60 } }),
        headers: { "Content-Type": "application/json" },
        signal: AbortSignal.timeout(15_000),
      });
    }
    if (!res.ok) return null;
    const data = await res.json();
    return data as Product;
  } catch {
    return null;
  }
}

const fetchProductBySlugCached = cache(
  async (normalized: string, attachGroupListing: boolean): Promise<Product | null> =>
    fetchProductBySlug(normalized, { attachGroupListing, noStore: false }),
);

export async function getProductBySlugForSeo(
  slug: string
): Promise<ProductForSeo | null> {
  const product = await getProductBySlugForSSR(slug, { attachGroupListing: true });
  return product as ProductForSeo | null;
}

export type ProductSSRLoadOptions = {
  /** PDP OOS: không cache để redirect kịp thời */
  noStore?: boolean;
  /** Một request: kèm group_listing_path khi hết hàng */
  attachGroupListing?: boolean;
};

/** Server-side: lấy full product theo slug (cho SSR trang chi tiết). */
export async function getProductBySlugForSSR(
  slug: string,
  options?: ProductSSRLoadOptions,
): Promise<Product | null> {
  const normalized = normalizeProductRouteSlug(slug);
  if (!normalized) return null;
  const attach = Boolean(options?.attachGroupListing);
  if (options?.noStore) {
    return fetchProductBySlug(normalized, { attachGroupListing: attach, noStore: true });
  }
  return fetchProductBySlugCached(normalized, attach);
}

/** Server-side: lấy full product theo SKU (product_id, slug hoặc code). */
export async function getProductBySkuForSSR(sku: string): Promise<Product | null> {
  const key = (sku || "").trim();
  if (!key) return null;
  const apiBase = apiBaseForProductFetch();
  const headers = { "Content-Type": "application/json" };

  try {
    const directUrl = `${apiBase}/products/${encodeURIComponent(key)}`;
    const res = await fetch(directUrl, {
      next: { revalidate: 60 },
      headers,
    });
    if (res.ok) {
      return (await res.json()) as Product;
    }

    // Fallback: API list đã hỗ trợ lọc theo product_id hoặc mã code (SKU nội bộ).
    const listUrl = `${apiBase}/products/?product_id=${encodeURIComponent(key)}&limit=1`;
    const listRes = await fetch(listUrl, {
      next: { revalidate: 60 },
      headers,
    });
    if (!listRes.ok) return null;
    const data = (await listRes.json()) as { products?: Product[] };
    const first = data?.products?.[0];
    return first ?? null;
  } catch {
    return null;
  }
}

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL ||
  process.env.NEXT_PUBLIC_DOMAIN ||
  "https://188.com.vn";

function absoluteImage(img: string | undefined): string {
  if (!img) return "";
  if (img.startsWith("http")) return img;
  if (img.startsWith("//")) return "https:" + img;
  if (img.startsWith("/")) return SITE_URL + img;
  return SITE_URL + "/" + img;
}

/** Loại bỏ thẻ HTML để meta description và JSON-LD là plain text (tốt cho Google). */
export function stripHtml(html: string | undefined): string {
  if (!html || typeof html !== "string") return "";
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Cắt mô tả tại dấu câu gần nhất (trọn câu), tối đa maxLen. */
export function truncateDescriptionAtSentence(
  text: string,
  maxLen: number = 160
): string {
  const s = stripHtml(text).trim();
  if (!s || s.length <= maxLen) return s;
  const slice = s.slice(0, maxLen);
  const lastDot = slice.lastIndexOf(".");
  const lastQuestion = slice.lastIndexOf("?");
  const lastExclaim = slice.lastIndexOf("!");
  const lastBreak = Math.max(lastDot, lastQuestion, lastExclaim);
  if (lastBreak > maxLen * 0.5) return slice.slice(0, lastBreak + 1).trim();
  const lastSpace = slice.lastIndexOf(" ");
  if (lastSpace > maxLen * 0.5) return (slice.slice(0, lastSpace).trim() + "...");
  return slice.trim() + "...";
}

/**
 * Tạo JSON-LD schema Product cho Google (rich results, index nhanh).
 */
export function buildProductJsonLd(product: ProductForSeo): object {
  const image = absoluteImage(product.main_image) || (product.images?.[0] ? absoluteImage(product.images[0]) : "");
  const name = product.meta_title || product.name;
  const brandDisplay = displayableBrandWithDefault(product.brand_name);
  const rawDesc =
    product.meta_description ||
    product.description ||
    `${product.name}${brandDisplay ? ` - ${brandDisplay}` : ""}. Mua tại 188.com.vn`;
  const description = stripHtml(rawDesc);

  const pdpUrl = productPublicPdpUrl(product.slug, SITE_URL);

  return {
    "@context": "https://schema.org",
    "@type": "Product",
    name,
    description: description.slice(0, 500),
    image: image ? [image] : undefined,
    sku: product.product_id || String(product.id),
    url: pdpUrl,
    brand: { "@type": "Brand", name: brandDisplay },
    offers: {
      "@type": "Offer",
      url: pdpUrl,
      priceCurrency: "VND",
      price: product.price,
      availability:
        (product.available ?? 0) > 0
          ? "https://schema.org/InStock"
          : "https://schema.org/OutOfStock",
      seller: { "@type": "Organization", name: "188.com.vn" },
    },
    aggregateRating:
      product.rating_total != null && product.rating_total > 0
        ? {
            "@type": "AggregateRating",
            ratingValue: product.rating_point ?? 0,
            reviewCount: product.rating_total,
            bestRating: 5,
            worstRating: 1,
          }
        : undefined,
  };
}
