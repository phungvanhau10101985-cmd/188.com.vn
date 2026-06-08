import type { MetadataRoute } from "next";
import { getCategoryTreeForLayout } from "@/lib/category-seo";
import type { CategoryLevel1 } from "@/types/api";
import { INFO_PAGES } from "@/app/info/info-pages.config";
import { listSeoClusters } from "@/lib/seo-cluster";

/** Không prerender lúc build — generate khi request (tránh timeout khi API/DB bận). */
export const dynamic = "force-dynamic";
export const revalidate = 3600;

const BASE_URL =
  process.env.NEXT_PUBLIC_SITE_URL ||
  process.env.NEXT_PUBLIC_DOMAIN ||
  "https://188.com.vn";

/** Trang tĩnh + danh mục + cluster + info. SP nằm ở /sitemap-san-pham/<page> (sitemap index). */
function flattenCategoryPaths(tree: CategoryLevel1[]): string[] {
  const paths: string[] = [];
  for (const c1 of tree) {
    const slug1 = (c1.slug || c1.name || "").trim().toLowerCase();
    if (!slug1) continue;
    paths.push(slug1);
    for (const c2 of c1.children || []) {
      const slug2 = (c2.slug || c2.name || "").trim().toLowerCase();
      if (!slug2) continue;
      paths.push(`${slug1}/${slug2}`);
    }
  }
  return paths;
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date();
  const entries: MetadataRoute.Sitemap = [];

  // Trang chủ
  entries.push({
    url: BASE_URL,
    lastModified: now,
    changeFrequency: "daily",
    priority: 1,
  });

  // Danh mục tổng
  entries.push({
    url: `${BASE_URL}/danh-muc`,
    lastModified: now,
    changeFrequency: "daily",
    priority: 0.9,
  });

  // Trang danh mục cấp 1, 2 (cat3 đã được gom về /c/<cluster>, không index trong sitemap)
  const tree = await getCategoryTreeForLayout();
  const categoryPaths = flattenCategoryPaths(tree);
  for (const path of categoryPaths) {
    entries.push({
      url: `${BASE_URL}/danh-muc/${path}`,
      lastModified: now,
      changeFrequency: "daily",
      priority: 0.8,
    });
  }

  // Landing SEO clusters: /c/<slug> — chỉ index những cluster có index_policy=index
  const clusters = await listSeoClusters();
  for (const c of clusters) {
    if (c.index_policy !== "index") continue;
    entries.push({
      url: `${BASE_URL}/c/${c.slug}`,
      lastModified: now,
      changeFrequency: "weekly",
      priority: 0.85,
    });
  }

  // Trang thông tin / chính sách
  for (const page of INFO_PAGES) {
    entries.push({
      url: `${BASE_URL}/info/${page.slug}`,
      lastModified: now,
      changeFrequency: "monthly",
      priority: 0.5,
    });
  }

  return entries;
}
