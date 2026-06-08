import { NextResponse } from "next/server";

import { CATEGORY_SEO_SITEMAP_PATH } from "@/lib/category-sitemap";
import { getSiteOrigin } from "@/lib/site-origin";

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

function buildSitemapIndexXml(origin: string): string {
  const sitemaps = [
    `${origin}/sitemap.xml`,
    `${origin}${CATEGORY_SEO_SITEMAP_PATH}`,
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
  const xml = buildSitemapIndexXml(origin);
  return new NextResponse(xml, {
    status: 200,
    headers: {
      "Content-Type": "application/xml; charset=utf-8",
      "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
    },
  });
}
