import Link from 'next/link';
import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import {
  getCategoryByPathForSeo,
  getCategorySeoData,
  getProductsByCategory,
  getCategoryTreeForLayout,
  type CategoryListingFilters,
} from '@/lib/category-seo';
import {
  buildCategoryCanonicalWithFilters,
  buildCategoryFilterMetaParts,
  categoryListingHasSeoDimensions,
} from '@/lib/filtered-listing-metadata';
import { getListingFreshnessMonthLabel } from '@/lib/listing-freshness-label';
import { buildInternalLinkMap } from '@/lib/internal-links';
import { getClusterSlugForCat3 } from '@/lib/seo-cluster';
import CategoryPageClient from './CategoryPageClient';
import CategoryListPage from './CategoryListPage';
import type { Product } from '@/types/api';

const PAGE_SIZE = 96;

function parseListingFilters(sp: Record<string, string | string[] | undefined>): {
  page: number;
  filters: CategoryListingFilters;
} {
  const g = (k: string) => {
    const v = sp[k];
    return Array.isArray(v) ? v[0] : v;
  };
  const page = Math.max(1, parseInt(String(g('page') ?? '1'), 10) || 1);
  const minRaw = g('min_price');
  const maxRaw = g('max_price');
  const minNum =
    minRaw != null && String(minRaw).trim() !== ''
      ? parseFloat(String(minRaw))
      : NaN;
  const maxNum =
    maxRaw != null && String(maxRaw).trim() !== ''
      ? parseFloat(String(maxRaw))
      : NaN;
  const filters: CategoryListingFilters = {};
  if (!Number.isNaN(minNum) && minNum >= 0) filters.minPrice = minNum;
  if (!Number.isNaN(maxNum) && maxNum >= 0) filters.maxPrice = maxNum;
  const sz = g('size')?.trim();
  if (sz) filters.size = sz;
  const cl = g('color')?.trim();
  if (cl) filters.color = cl;
  const styleTag = g('style_tag')?.trim();
  if (styleTag) filters.styleTag = styleTag;
  const sort = g('sort')?.trim();
  if (sort) filters.sort = sort;
  return { page, filters };
}

function serializeSearchParamsForListing(
  sp: Record<string, string | string[] | undefined>
): string {
  const p = new URLSearchParams();
  for (const [key, val] of Object.entries(sp)) {
    if (val === undefined) continue;
    if (Array.isArray(val)) {
      for (const v of val) {
        if (v !== undefined) p.append(key, v);
      }
    } else {
      p.set(key, val);
    }
  }
  return p.toString();
}

type Props = {
  params: Promise<{ slug?: string[] }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export async function generateMetadata({ params, searchParams }: Props): Promise<Metadata> {
  const { slug } = await params;
  const sp = await searchParams;
  const [level1, level2, level3] = slug || [];

  if (level3) {
    const clusterSlug = await getClusterSlugForCat3(level3);
    if (clusterSlug) return {};
  }

  if (!level1 || !categoryListingHasSeoDimensions(sp)) {
    return {};
  }

  const info = await getCategorySeoData(level1, level2, level3);
  if (!info) return {};

  const pathSegments = [level1];
  if (level2) pathSegments.push(level2);
  if (level3) pathSegments.push(level3);
  const pathStr = pathSegments.join('/');
  const canonical = buildCategoryCanonicalWithFilters(`/danh-muc/${pathStr}`, sp);

  const filterBits = buildCategoryFilterMetaParts(sp);
  const month = getListingFreshnessMonthLabel();
  const filterStr = filterBits.join(' · ');

  const title = filterStr
    ? `${info.full_name} — ${filterStr} — ${month} | ${info.product_count}+ mẫu`
    : `${info.full_name} — ${month} | ${info.product_count}+ mẫu`;

  const baseDesc =
    info.seo_description ||
    `${info.full_name} - ${info.product_count} sản phẩm. Mua sắm tại 188.com.vn - Xem là thích click là mê.`;
  const description = `${baseDesc} ${filterStr ? `Đang lọc: ${filterStr}. ` : ''}Cập nhật ${month}.`.slice(
    0,
    160,
  );

  return {
    title,
    description,
    alternates: { canonical },
    robots: { index: true, follow: true },
  };
}

export default async function CategoryPage({ params, searchParams }: Props) {
  const { slug } = await params;
  const resolvedSearchParams = await searchParams;
  const [level1, level2, level3] = slug || [];

  // Cat3 (URL có 3 segments): theo plan SEO mới, mỗi cat3 đã gom về 1 SEO cluster.
  // Redirect 301 sang `/c/<cluster_slug>` để gom traffic + tránh duplicate content.
  if (level3) {
    const clusterSlug = await getClusterSlugForCat3(level3);
    if (clusterSlug) {
      redirect(`/c/${clusterSlug}`);
    }
    // Không tìm được cluster (cat3 chưa có trong taxonomy mới) — render fallback ở dưới.
  }

  const { page: pageParam, filters: listingFilters } =
    parseListingFilters(resolvedSearchParams);
  const page = pageParam;
  const skip = (page - 1) * PAGE_SIZE;

  const listingQueryString = serializeSearchParamsForListing(resolvedSearchParams);

  // Trang danh mục tổng (không có slug): mobile = header cam + list; desktop = list + về trang chủ
  if (!level1) {
    const categoryTree = await getCategoryTreeForLayout();
    return <CategoryListPage categoryTree={categoryTree} />;
  }

  // Lấy thông tin danh mục (không còn redirect canonical, SEO tất cả trang danh mục)
  const info = await getCategoryByPathForSeo(level1, level2, level3);
  if (!info) {
    return (
      <main className="max-w-7xl mx-auto px-4 py-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-4">Danh mục không tồn tại</h1>
        <p className="text-gray-600 mb-6">
          Danh mục bạn tìm không có trong hệ thống.{' '}
          <Link href="/" className="text-[#ea580c] hover:underline">
            Về trang chủ
          </Link>
        </p>
      </main>
    );
  }

  const breadcrumbNames = info.breadcrumb_names || [];
  const pathSegments = [level1];
  if (level2) pathSegments.push(level2);
  if (level3) pathSegments.push(level3);

  // Song song hóa: giảm chờ tuyến tính; Next vẫn SSR đầy đủ HTML + metadata (layout generateMetadata).
  const [
    { products, total, total_pages, page: currentPage },
    seoData,
    categoryTree,
  ] = await Promise.all([
    getProductsByCategory(
      level1,
      level2,
      level3,
      { limit: PAGE_SIZE, skip, filters: listingFilters },
      info,
    ),
    getCategorySeoData(level1, level2, level3),
    getCategoryTreeForLayout(),
  ]);

  const seoBody = seoData?.seo_body ?? null;
  const internalLinkMap = buildInternalLinkMap(categoryTree, pathSegments);

  return (
    <CategoryPageClient
      breadcrumbNames={breadcrumbNames}
      pathSegments={pathSegments}
      products={products as Product[]}
      total={total}
      totalPages={total_pages}
      currentPage={currentPage}
      pageSize={PAGE_SIZE}
      seoBody={seoBody}
      internalLinkMap={internalLinkMap}
      error={null}
      facets={null}
      listingQueryString={listingQueryString}
    />
  );
}
