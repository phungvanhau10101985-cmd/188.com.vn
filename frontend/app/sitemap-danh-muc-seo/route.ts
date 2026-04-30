import { NextResponse } from 'next/server';
import { getCategoryTreeForLayout } from '@/lib/category-seo';
import {
  CATEGORY_SEO_SITEMAP_PATH,
  buildCategorySeoSitemapXml,
  flattenCategoryTreeForSitemap,
} from '@/lib/category-sitemap';
import { listSeoClusters } from '@/lib/seo-cluster';

export const revalidate = 3600;

function siteBaseFromRequest(request: Request): string {
  const env =
    process.env.NEXT_PUBLIC_SITE_URL?.trim() ||
    process.env.NEXT_PUBLIC_DOMAIN?.trim() ||
    '';
  if (env) return env.replace(/\/$/, '');
  try {
    const u = new URL(request.url);
    return `${u.protocol}//${u.host}`.replace(/\/$/, '');
  } catch {
    return 'https://188.com.vn';
  }
}

/**
 * GET — Sitemap XML SEO danh mục (URL công khai, gửi Search Console).
 * Trang admin: liên kết cùng pathname với hằng CATEGORY_SEO_SITEMAP_PATH.
 */
export async function GET(request: Request) {
  const siteBase = siteBaseFromRequest(request);
  const tree = await getCategoryTreeForLayout();
  const categories = flattenCategoryTreeForSitemap(tree);
  const clusters = await listSeoClusters();
  const indexedClusterUrls = clusters
    .filter((c) => c.index_policy === 'index' && c.slug)
    .map(
      (c) =>
        `${siteBase}/c/${encodeURIComponent(String(c.slug).replace(/^\/+|\/+$/g, ''))}`,
    );
  const xml = buildCategorySeoSitemapXml({
    siteBase,
    categories,
    indexedClusterAbsoluteUrls: indexedClusterUrls,
  });
  return new NextResponse(xml, {
    status: 200,
    headers: {
      'Content-Type': 'application/xml; charset=utf-8',
      'Cache-Control': 'public, s-maxage=3600, stale-while-revalidate=86400',
    },
  });
}
