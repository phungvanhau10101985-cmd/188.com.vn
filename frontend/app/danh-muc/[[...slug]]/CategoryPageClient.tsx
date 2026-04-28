'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import ProductGrid from '@/components/ProductGrid';
import { linkifySeoBody } from '@/lib/internal-links';
import type { Product } from '@/types/api';
import type { InternalLinkItem } from '@/lib/internal-links';

/** Từ ngày 20 tháng N hiển thị "tháng N+1"; trước đó hiển thị "tháng N". Tự nhảy theo tháng. */
function getCurrentMonthLabel(): string {
  const now = new Date();
  let month = now.getMonth() + 1;
  let year = now.getFullYear();
  if (now.getDate() >= 20) {
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
  }
  return `tháng ${month}/${year}`;
}

interface CategoryPageClientProps {
  breadcrumbNames: string[];
  pathSegments: string[];
  products: Product[];
  total: number;
  totalPages: number;
  currentPage: number;
  pageSize: number;
  seoBody: string | null;
  internalLinkMap?: InternalLinkItem[];
  error: string | null;
}

export default function CategoryPageClient({
  breadcrumbNames,
  pathSegments,
  products,
  total,
  totalPages,
  currentPage,
  pageSize,
  seoBody,
  internalLinkMap = [],
  error,
}: CategoryPageClientProps) {
  const router = useRouter();
  const fullName = breadcrumbNames.join(' - ');
  const leafName = breadcrumbNames[breadcrumbNames.length - 1] || 'sản phẩm';
  const basePath = `/danh-muc/${pathSegments.join('/')}`;
  const from = total === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const to = Math.min(currentPage * pageSize, total);

  const monthLabel = getCurrentMonthLabel();
  const h1Text = `${leafName} mới nhất ${monthLabel} | ${total} sản phẩm`;

  return (
    <main className="max-w-7xl mx-auto px-4 py-6" role="main" aria-label={fullName}>
      <nav className="text-sm text-gray-500 mb-4" aria-label="Breadcrumb">
        <Link href="/" className="hover:text-[#ea580c]">Trang chủ</Link>
        {breadcrumbNames.map((name, i) => (
          <span key={i}>
            <span className="mx-2">/</span>
            <Link
              href={`/danh-muc/${pathSegments.slice(0, i + 1).join('/')}`}
              className="hover:text-[#ea580c]"
            >
              {name}
            </Link>
          </span>
        ))}
      </nav>

      {/* H1: tên danh mục lá + mới nhất tháng X/YYYY | số sản phẩm (SEO, tự cập nhật theo ngày 20) */}
      <h1 className="text-2xl font-bold text-gray-900 mb-4">
        {h1Text}
      </h1>

      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 rounded-xl p-4 flex items-center justify-between">
          <p className="text-red-700 font-medium">{error}</p>
          <button
            onClick={() => router.push('/')}
            className="px-4 py-2 rounded-lg bg-red-500 text-white text-sm font-medium hover:bg-red-600"
          >
            Về trang chủ
          </button>
        </div>
      )}

      {!error && (
        <>
          <h2 className="text-lg font-semibold text-gray-800 mb-4">
            {total} {leafName} dành cho bạn
            {totalPages > 1 && (
              <span className="text-gray-500 font-normal text-base ml-2">
                (trang {currentPage}/{totalPages}, hiển thị {from}–{to})
              </span>
            )}
          </h2>
          <ProductGrid
            products={products}
            loading={false}
            selectedCategory={leafName}
            showFilters={false}
          />
          {totalPages > 1 && (
            <nav className="mt-8 flex flex-wrap items-center justify-center gap-2" aria-label="Phân trang danh mục">
              {currentPage > 1 && (
                <Link
                  href={currentPage === 2 ? basePath : `${basePath}?page=${currentPage - 1}`}
                  className="px-4 py-2 rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 font-medium text-sm"
                >
                  ← Trang trước
                </Link>
              )}
              <span className="px-3 py-2 text-gray-600 text-sm">
                Trang {currentPage} / {totalPages}
              </span>
              {currentPage < totalPages && (
                <Link
                  href={`${basePath}?page=${currentPage + 1}`}
                  className="px-4 py-2 rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 font-medium text-sm"
                >
                  Trang sau →
                </Link>
              )}
            </nav>
          )}

          {seoBody && (
            <section
              className="mt-12 pt-8 border-t border-gray-200"
              aria-label="Giới thiệu danh mục"
            >
              <div
                className="prose prose-gray max-w-none text-gray-600 text-sm leading-relaxed"
                dangerouslySetInnerHTML={{
                  __html: linkifySeoBody(seoBody, internalLinkMap),
                }}
              />
            </section>
          )}
        </>
      )}
    </main>
  );
}
