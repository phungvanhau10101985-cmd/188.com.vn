import { NextResponse } from "next/server";

import { CATEGORY_SEO_SITEMAP_PATH } from "@/lib/category-sitemap";
import { getSiteOrigin } from "@/lib/site-origin";
import {
  SITEMAP_PRODUCT_PATH_PREFIX,
  countProductSitemapPages,
  fetchProductSitemapPage,
} from "@/lib/sitemap-products";

export const dynamic = "force-dynamic";
export const revalidate = 3600;

function escapeXml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function buildSitemapIndexXml(origin: string, productPages: number): string {
  const sitemaps = [
    `${origin}/sitemap.xml`,
    `${origin}${CATEGORY_SEO_SITEMAP_PATH}`,
    ...Array.from(
      { length: productPages },
      (_, i) => `${origin}${SITEMAP_PRODUCT_PATH_PREFIX}/${i + 1}`,
    ),
  ];
  const now = new Date().toISOString();
  const entries = sitemaps
    .map(
      (loc) =>
        `  <sitemap>\n    <loc>${escapeXml(loc)}</loc>\n    <lastmod>${now}</lastmod>\n  </sitemap>`
    )
    .join("\n");

  return `<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${entries}\n</sitemapindex>\n`;
}

export async function GET() {
  const origin = getSiteOrigin();
  const { total } = await fetchProductSitemapPage(1, { skipTotal: false });
  const productPages = countProductSitemapPages(total);
  const xml = buildSitemapIndexXml(origin, productPages);
  return new NextResponse(xml, {
    status: 200,
    headers: {
      "Content-Type": "application/xml; charset=utf-8",
      "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
    },
  });
}
