import Link from 'next/link';
import { redirect } from 'next/navigation';
import { getCategoryByPathForSeo, getCategorySeoData, getProductsByCategory, getCategoryTreeForLayout } from '@/lib/category-seo';
import { buildInternalLinkMap } from '@/lib/internal-links';
import { getClusterSlugForCat3 } from '@/lib/seo-cluster';
import CategoryPageClient from './CategoryPageClient';
import CategoryListPage from './CategoryListPage';
import type { Product } from '@/types/api';

const PAGE_SIZE = 96;

type Props = {
  params: { slug?: string[] };
  searchParams: { page?: string };
};

export default async function CategoryPage({ params, searchParams }: Props) {
  const { slug } = params;
  const { page: pageParam } = searchParams;
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

  const page = Math.max(1, parseInt(String(pageParam), 10) || 1);
  const skip = (page - 1) * PAGE_SIZE;

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

  const { products, total, total_pages, page: currentPage } = await getProductsByCategory(
    level1,
    level2,
    level3,
    {
      limit: PAGE_SIZE,
      skip,
    },
    info
  );

  const seoData = await getCategorySeoData(level1, level2, level3);
  const seoBody = seoData?.seo_body ?? null;

  const categoryTree = await getCategoryTreeForLayout();
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
    />
  );
}
