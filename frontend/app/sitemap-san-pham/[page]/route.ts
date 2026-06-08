import { NextResponse } from "next/server";

import { getSiteOrigin } from "@/lib/site-origin";
import {
  SITEMAP_PRODUCT_MAX_PAGES,
  buildProductSitemapXml,
  fetchProductSitemapPage,
} from "@/lib/sitemap-products";

export const dynamic = "force-dynamic";
export const revalidate = 3600;

type RouteContext = { params: Promise<{ page: string }> };

export async function GET(_request: Request, context: RouteContext) {
  const rawPage = (await context.params).page;
  const page = parseInt(rawPage, 10);
  if (!Number.isFinite(page) || page < 1 || page > SITEMAP_PRODUCT_MAX_PAGES) {
    return new NextResponse("Not Found", { status: 404 });
  }

  const { products } = await fetchProductSitemapPage(page, { skipTotal: true });
  if (products.length === 0 && page > 1) {
    return new NextResponse("Not Found", { status: 404 });
  }

  const origin = getSiteOrigin();
  const xml = buildProductSitemapXml(origin, products);
  return new NextResponse(xml, {
    status: 200,
    headers: {
      "Content-Type": "application/xml; charset=utf-8",
      "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
    },
  });
}
