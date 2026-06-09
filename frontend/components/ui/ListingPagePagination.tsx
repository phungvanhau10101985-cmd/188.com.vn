'use client';

import LoadingLink from '@/components/ui/LoadingLink';

type ListingPagePaginationProps = {
  currentPage: number;
  totalPages: number;
  getHref: (page: number) => string;
  className?: string;
};

const pageLinkClass =
  'inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50';

export default function ListingPagePagination({
  currentPage,
  totalPages,
  getHref,
  className = '',
}: ListingPagePaginationProps) {
  if (totalPages <= 1) return null;

  return (
    <nav
      className={`mt-8 flex flex-wrap items-center justify-center gap-2 ${className}`.trim()}
      aria-label="Phân trang danh sách"
    >
      {currentPage > 1 ? (
        <LoadingLink href={getHref(currentPage - 1)} className={pageLinkClass} loadingLabel="Đang tải…">
          ← Trang trước
        </LoadingLink>
      ) : null}
      <span className="px-3 py-2 text-sm text-gray-600">
        Trang {currentPage} / {totalPages}
      </span>
      {currentPage < totalPages ? (
        <LoadingLink href={getHref(currentPage + 1)} className={pageLinkClass} loadingLabel="Đang tải…">
          Trang sau →
        </LoadingLink>
      ) : null}
    </nav>
  );
}
