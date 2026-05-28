'use client';

type HomeProductPaginationProps = {
  currentPage: number;
  totalPages: number;
  totalProducts: number;
  onPageChange: (page: number) => void;
};

function buildVisiblePageNumbers(current: number, total: number): (number | 'ellipsis')[] {
  if (total <= 1) return [];
  if (total <= 7) {
    return Array.from({ length: total }, (_, index) => index + 1);
  }

  const pages: (number | 'ellipsis')[] = [1];
  const windowStart = Math.max(2, current - 1);
  const windowEnd = Math.min(total - 1, current + 1);

  if (windowStart > 2) pages.push('ellipsis');
  for (let page = windowStart; page <= windowEnd; page += 1) {
    pages.push(page);
  }
  if (windowEnd < total - 1) pages.push('ellipsis');
  pages.push(total);
  return pages;
}

export default function HomeProductPagination({
  currentPage,
  totalPages,
  totalProducts,
  onPageChange,
}: HomeProductPaginationProps) {
  if (totalPages <= 1) return null;

  const pageItems = buildVisiblePageNumbers(currentPage, totalPages);
  const canGoPrev = currentPage > 1;
  const canGoNext = currentPage < totalPages;

  const navButtonClass =
    'inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg border border-gray-200 bg-white px-3 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40';

  const pageButtonClass = (active: boolean) =>
    [
      'inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg border px-3 text-sm font-semibold transition-colors',
      active
        ? 'border-[#ea580c] bg-[#ea580c] text-white shadow-sm'
        : 'border-gray-200 bg-white text-gray-700 hover:border-orange-200 hover:bg-orange-50 hover:text-[#c2410c]',
    ].join(' ');

  return (
    <nav className="mt-6 flex flex-col items-start gap-2" aria-label="Phân trang sản phẩm">
      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          onClick={() => onPageChange(currentPage - 1)}
          disabled={!canGoPrev}
          className={navButtonClass}
          aria-label="Trang trước"
        >
          ←
        </button>

        {pageItems.map((item, index) =>
          item === 'ellipsis' ? (
            <span
              key={`ellipsis-${index}`}
              className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center px-1 text-sm text-gray-400"
              aria-hidden
            >
              …
            </span>
          ) : (
            <button
              key={item}
              type="button"
              onClick={() => onPageChange(item)}
              className={pageButtonClass(item === currentPage)}
              aria-label={`Trang ${item}`}
              aria-current={item === currentPage ? 'page' : undefined}
            >
              {item}
            </button>
          )
        )}

        <button
          type="button"
          onClick={() => onPageChange(currentPage + 1)}
          disabled={!canGoNext}
          className={navButtonClass}
          aria-label="Trang sau"
        >
          →
        </button>
      </div>

      <p className="text-xs text-gray-500">
        Tổng {totalProducts.toLocaleString('vi-VN')} sản phẩm · Trang {currentPage}/{totalPages}
      </p>
    </nav>
  );
}
