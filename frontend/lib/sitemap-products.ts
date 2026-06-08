import { productPublicPdpUrl } from "@/lib/product-path-slug";
import { isNextProductionBuild } from "@/lib/build-phase";

export const SITEMAP_PRODUCT_PAGE_SIZE = 5000;
export const SITEMAP_PRODUCT_MAX_PAGES = 12;

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001/api/v1";

export interface ProductSitemapSlug {
  slug: string;
  updated_at?: string;
}

export interface ProductSitemapPageResult {
  total: number;
  products: ProductSitemapSlug[];
}

function escapeXml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function formatLastmod(updatedAt: string | undefined, fallback: string): string {
  if (!updatedAt) return fallback;
  const d = new Date(updatedAt);
  if (Number.isNaN(d.getTime())) return fallback;
  return escapeXml(d.toISOString());
}

/** Một trang slug SP — `skip_total` bỏ COUNT nặng trên API (trang 2+). */
export async function fetchProductSitemapPage(
  page: number,
  options?: { skipTotal?: boolean },
): Promise<ProductSitemapPageResult> {
  if (isNextProductionBuild() || page < 1 || page > SITEMAP_PRODUCT_MAX_PAGES) {
    return { total: 0, products: [] };
  }

  const skip = (page - 1) * SITEMAP_PRODUCT_PAGE_SIZE;
  const skipTotal = options?.skipTotal ?? page > 1;
  const params = new URLSearchParams({
    limit: String(SITEMAP_PRODUCT_PAGE_SIZE),
    skip: String(skip),
    is_active: "true",
    skip_total: skipTotal ? "true" : "false",
  });

  try {
    const res = await fetch(`${API_BASE}/products/sitemap-slugs?${params}`, {
      next: { revalidate: 3600 },
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.timeout(60_000),
    });
    if (!res.ok) return { total: 0, products: [] };
    const data = (await res.json()) as {
      total?: number;
      products?: ProductSitemapSlug[];
    };
    return {
      total: typeof data.total === "number" ? data.total : 0,
      products: data.products || [],
    };
  } catch {
    return { total: 0, products: [] };
  }
}

export function countProductSitemapPages(total: number): number {
  if (total <= 0) return 1;
  return Math.min(
    SITEMAP_PRODUCT_MAX_PAGES,
    Math.ceil(total / SITEMAP_PRODUCT_PAGE_SIZE),
  );
}

export function buildProductSitemapXml(
  siteBase: string,
  products: ProductSitemapSlug[],
): string {
  const now = new Date().toISOString();
  const rows = products
    .filter((p) => p.slug)
    .map((p) => {
      const loc = escapeXml(productPublicPdpUrl(p.slug, siteBase));
      const lastmod = formatLastmod(p.updated_at, now);
      return `  <url>\n    <loc>${loc}</loc>\n    <lastmod>${lastmod}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.7</priority>\n  </url>`;
    });

  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${rows.join("\n")}\n</urlset>\n`;
}

export const SITEMAP_PRODUCT_PATH_PREFIX = "/sitemap-san-pham";
