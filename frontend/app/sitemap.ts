import type { MetadataRoute } from "next";
import { getCategoryTreeForLayout } from "@/lib/category-seo";
import type { CategoryLevel1 } from "@/types/api";
import { INFO_PAGES } from "@/app/info/info-pages.config";

const BASE_URL =
  process.env.NEXT_PUBLIC_SITE_URL ||
  process.env.NEXT_PUBLIC_DOMAIN ||
  "https://188.com.vn";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001/api/v1";

/** Lấy tất cả slug sản phẩm từ API (phân trang). */
async function getAllProductSlugs(): Promise<{ slug: string; updated_at?: string }[]> {
  const results: { slug: string; updated_at?: string }[] = [];
  let skip = 0;
  const limit = 500;
  try {
    while (true) {
      const url = `${API_BASE}/products/?limit=${limit}&skip=${skip}&is_active=true`;
      const res = await fetch(url, {
        next: { revalidate: 3600 },
        headers: { "Content-Type": "application/json" },
      });
      if (!res.ok) break;
      const data = (await res.json()) as { products?: { slug?: string; updated_at?: string }[] };
      const products = data.products || [];
      if (products.length === 0) break;
      for (const p of products) {
        if (p.slug) results.push({ slug: p.slug, updated_at: p.updated_at });
      }
      if (products.length < limit) break;
      skip += limit;
    }
  } catch {
    // Bỏ qua nếu API lỗi (vd: build không có backend)
  }
  return results;
}

/** Flatten cây danh mục 3 cấp thành danh sách path (slug). */
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
      for (const c3 of c2.children || []) {
        const name3 = typeof c3 === "object" && c3 !== null && "name" in c3 ? (c3 as { name: string }).name : String(c3);
        const slug3 = ((c3 as { slug?: string }).slug || name3 || "").trim().toLowerCase();
        if (!slug3) continue;
        paths.push(`${slug1}/${slug2}/${slug3}`);
      }
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

  // Các trang danh mục (cấp 1, 2, 3)
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

  // Trang thông tin / chính sách
  for (const page of INFO_PAGES) {
    entries.push({
      url: `${BASE_URL}/info/${page.slug}`,
      lastModified: now,
      changeFrequency: "monthly",
      priority: 0.5,
    });
  }

  // Trang sản phẩm
  const products = await getAllProductSlugs();
  for (const p of products) {
    entries.push({
      url: `${BASE_URL}/products/${p.slug}`,
      lastModified: p.updated_at ? new Date(p.updated_at) : now,
      changeFrequency: "weekly",
      priority: 0.7,
    });
  }

  return entries;
}
