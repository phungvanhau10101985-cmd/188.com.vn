/**
 * Sinh XML sitemap cho khu SEO danh mục: /danh-muc (+ cây đường dẫn) và tuỳ chọn /c/<cluster>.
 */

import type { CategoryLevel1, CategoryLevel3 } from '@/types/api';

/** Đường dẫn route công khai — dùng trong Link và Search Console. */
export const CATEGORY_SEO_SITEMAP_PATH = '/sitemap-danh-muc-seo';

export interface CategorySitemapRow {
  /** Đường dẫn tương đối kiểu `/danh-muc/…` */
  url: string;
  level: 1 | 2 | 3;
}

function slugOf(node: { name: string; slug?: string }): string {
  return (node.slug || node.name).toString().trim().toLowerCase().replace(/\s+/g, '-');
}

/** Khớp logic flatten trên `/admin/danh-muc-seo` — dùng chung cho tải file và route GET. */
export function flattenCategoryTreeForSitemap(tree: CategoryLevel1[]): CategorySitemapRow[] {
  const out: CategorySitemapRow[] = [];
  for (const c1 of tree) {
    const s1 = slugOf(c1);
    out.push({ level: 1, url: `/danh-muc/${s1}` });
    for (const c2 of c1.children || []) {
      const s2 = slugOf(c2);
      const path2 = `${s1}/${s2}`;
      out.push({ level: 2, url: `/danh-muc/${path2}` });
      for (const c3 of c2.children || []) {
        const name3 =
          typeof c3 === 'object' && c3 !== null && 'name' in c3 ? (c3 as CategoryLevel3).name : String(c3);
        const s3 =
          typeof c3 === 'object' && c3 !== null && 'slug' in c3
            ? (c3 as CategoryLevel3).slug || name3
            : name3;
        const s3Norm = String(s3).trim().toLowerCase().replace(/\s+/g, '-');
        const path3 = `${path2}/${s3Norm}`;
        out.push({ level: 3, url: `/danh-muc/${path3}` });
      }
    }
  }
  return out;
}

function escapeXml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function absLoc(siteBase: string, pathname: string): string {
  const base = siteBase.replace(/\/$/, '');
  const path = pathname.startsWith('/') ? pathname : `/${pathname}`;
  return new URL(path, `${base}/`).href;
}

function priorityForCategoryLevel(level: 1 | 2 | 3): string {
  if (level === 1) return '0.82';
  if (level === 2) return '0.8';
  return '0.78';
}

/**
 * Chuẩn sitemaps.org 0.9 — không có lastmod để không cần cập nhật theo ngày từng URL.
 */
export function buildCategorySeoSitemapXml(args: {
  siteBase: string;
  categories: CategorySitemapRow[];
  indexedClusterAbsoluteUrls?: string[];
}): string {
  const { siteBase, categories, indexedClusterAbsoluteUrls } = args;
  const rows: string[] = [];
  rows.push('<?xml version="1.0" encoding="UTF-8"?>');
  rows.push('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">');

  const pushUrl = (loc: string, changefreq: string, priority: string) => {
    rows.push('  <url>');
    rows.push(`    <loc>${escapeXml(loc)}</loc>`);
    rows.push(`    <changefreq>${changefreq}</changefreq>`);
    rows.push(`    <priority>${priority}</priority>`);
    rows.push('  </url>');
  };

  pushUrl(absLoc(siteBase, '/danh-muc'), 'daily', '0.9');

  for (const c of categories) {
    pushUrl(absLoc(siteBase, c.url), 'daily', priorityForCategoryLevel(c.level));
  }

  for (const loc of indexedClusterAbsoluteUrls || []) {
    pushUrl(loc, 'weekly', '0.85');
  }

  rows.push('</urlset>');
  return rows.join('\n');
}

export function triggerDownloadXml(filename: string, xmlBody: string) {
  const blob = new Blob([xmlBody], { type: 'application/xml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
