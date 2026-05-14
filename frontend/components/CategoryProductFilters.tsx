'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import type { CategoryProductFacets } from '@/lib/category-seo';

type Props = {
  basePath: string;
  facets: CategoryProductFacets | null;
  compact?: boolean;
  /** Trang `/?q=` — hiện khung lọc ngay khi đang tìm (facets có thể tải sau). */
  enableEmptyListing?: boolean;
  /** Listing `/?style=…`, cùng loại — không có `q` nhưng vẫn cần khung lọc trước khi facets về. */
  enableListingFacetShell?: boolean;
};

function formatVndHint(n: number): string {
  return `${Math.round(n).toLocaleString('vi-VN')} ₫`;
}

function CategoryProductFiltersInner({
  basePath,
  facets,
  compact,
  enableEmptyListing,
  enableListingFacetShell,
}: Props) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const minPriceQ = searchParams.get('min_price') || '';
  const maxPriceQ = searchParams.get('max_price') || '';
  const size = searchParams.get('size') || '';
  const color = searchParams.get('color') || '';
  const styleTag = searchParams.get('style_tag') || '';
  const sort = searchParams.get('sort') || '';

  const [minLocal, setMinLocal] = useState(minPriceQ);
  const [maxLocal, setMaxLocal] = useState(maxPriceQ);

  useEffect(() => {
    setMinLocal(minPriceQ);
    setMaxLocal(maxPriceQ);
  }, [minPriceQ, maxPriceQ]);

  const navigateWith = useCallback(
    (updates: Record<string, string | null>) => {
      const p = new URLSearchParams(searchParams.toString());
      Object.entries(updates).forEach(([key, val]) => {
        if (val === null || val === '') {
          p.delete(key);
        } else {
          p.set(key, val);
        }
      });
      if (!Object.prototype.hasOwnProperty.call(updates, 'page')) {
        p.delete('page');
      }
      const q = p.toString();
      const dest = q ? `${basePath}?${q}` : basePath;
      router.push(dest, { scroll: false });
    },
    [basePath, router, searchParams]
  );

  const applyPriceFilters = useCallback(() => {
    const norm = (s: string) => s.trim();
    const nextMin = norm(minLocal);
    const nextMax = norm(maxLocal);
    const curMin = norm(minPriceQ);
    const curMax = norm(maxPriceQ);
    if (nextMin === curMin && nextMax === curMax) {
      return;
    }
    navigateWith({
      min_price: nextMin || null,
      max_price: nextMax || null,
      page: null,
    });
  }, [minLocal, maxLocal, minPriceQ, maxPriceQ, navigateWith]);

  const hasFacets =
    (facets && (facets.sizes.length > 0 || facets.colors.length > 0 || facets.style_tags.length > 0)) ||
    (facets && (facets.price_min != null || facets.price_max != null));

  const hasActiveFilters = useMemo(
    () => Boolean(minPriceQ || maxPriceQ || size || color || styleTag || sort),
    [minPriceQ, maxPriceQ, size, color, styleTag, sort]
  );

  const qList = searchParams.get('q')?.trim() ?? '';
  const showSearchShell = Boolean(enableEmptyListing && qList);
  const showListingFacetShell = Boolean(enableListingFacetShell);

  useEffect(() => {
    if (!facets) return;
    const updates: Record<string, string | null> = {};
    if (size && !facets.sizes.includes(size)) {
      updates.size = null;
    }
    if (color && !facets.colors.includes(color)) {
      updates.color = null;
    }
    if (styleTag && !facets.style_tags.includes(styleTag)) {
      updates.style_tag = null;
    }
    const minNum = minPriceQ ? Number(minPriceQ) : NaN;
    const maxNum = maxPriceQ ? Number(maxPriceQ) : NaN;
    const priceInvalid =
      (Number.isFinite(minNum) && Number.isFinite(maxNum) && minNum > maxNum) ||
      (facets.price_min != null && Number.isFinite(maxNum) && maxNum < facets.price_min) ||
      (facets.price_max != null && Number.isFinite(minNum) && minNum > facets.price_max) ||
      (facets.price_min == null &&
        facets.price_max == null &&
        facets.sizes.length === 0 &&
        facets.colors.length === 0 &&
        facets.style_tags.length === 0 &&
        Boolean(minPriceQ || maxPriceQ));
    if (priceInvalid) {
      updates.min_price = null;
      updates.max_price = null;
    }
    if (Object.keys(updates).length > 0) {
      navigateWith({ ...updates, page: null });
    }
  }, [facets, size, color, styleTag, minPriceQ, maxPriceQ, navigateWith]);

  if (!hasFacets && !hasActiveFilters && !showSearchShell && !showListingFacetShell) {
    return null;
  }

  return (
    <div className={compact ? "flex w-full flex-col gap-1" : "flex flex-col gap-2 sm:gap-3 w-full"} aria-label="Bộ lọc sản phẩm">
      <div className={compact ? "grid grid-cols-3 gap-1.5 sm:flex sm:flex-row sm:flex-wrap sm:items-end sm:justify-start" : "grid grid-cols-2 gap-2 sm:flex sm:flex-row sm:flex-wrap sm:items-end sm:justify-start"}>
        {facets && facets.sizes.length > 0 ? (
          <label className={compact ? "flex min-w-0 flex-col text-left" : "flex min-w-0 flex-col gap-1 text-left"}>
            <span className={compact ? "sr-only" : "text-xs font-medium text-gray-500"}>Size</span>
            <select
              value={size}
              onChange={(e) =>
                navigateWith({ size: e.target.value || null, page: null })
              }
              className={compact ? "h-8 w-full min-w-0 rounded-md border border-gray-300 bg-white px-1.5 text-[11px] text-gray-800 sm:min-w-[110px] sm:px-2 sm:text-xs" : "h-10 w-full rounded-lg border border-gray-300 bg-white px-2.5 py-2 text-xs text-gray-800 sm:min-w-[120px] sm:px-3 sm:text-sm"}
              aria-label="Lọc theo size"
            >
              <option value="">Tất cả size</option>
              {facets.sizes.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {facets && facets.style_tags.length > 0 ? (
          <label className={compact ? "flex min-w-0 flex-col text-left" : "flex min-w-0 flex-col gap-1 text-left"}>
            <span className={compact ? "sr-only" : "text-xs font-medium text-gray-500"}>Kiểu</span>
            <select
              value={styleTag}
              onChange={(e) =>
                navigateWith({ style_tag: e.target.value || null, page: null })
              }
              className={compact ? "h-8 w-full min-w-0 rounded-md border border-gray-300 bg-white px-1.5 text-[11px] text-gray-800 sm:min-w-[130px] sm:max-w-[200px] sm:px-2 sm:text-xs" : "h-10 w-full rounded-lg border border-gray-300 bg-white px-2.5 py-2 text-xs text-gray-800 sm:min-w-[150px] sm:max-w-[220px] sm:px-3 sm:text-sm"}
              aria-label="Lọc theo kiểu sản phẩm"
            >
              <option value="">Tất cả kiểu</option>
              {facets.style_tags.map((tag) => (
                <option key={tag} value={tag}>
                  {tag}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {facets && facets.colors.length > 0 ? (
          <label className={compact ? "flex min-w-0 flex-col text-left" : "flex min-w-0 flex-col gap-1 text-left"}>
            <span className={compact ? "sr-only" : "text-xs font-medium text-gray-500"}>Màu</span>
            <select
              value={color}
              onChange={(e) =>
                navigateWith({ color: e.target.value || null, page: null })
              }
              className={compact ? "h-8 w-full min-w-0 rounded-md border border-gray-300 bg-white px-1.5 text-[11px] text-gray-800 sm:min-w-[120px] sm:max-w-[190px] sm:px-2 sm:text-xs" : "h-10 w-full rounded-lg border border-gray-300 bg-white px-2.5 py-2 text-xs text-gray-800 sm:min-w-[140px] sm:max-w-[220px] sm:px-3 sm:text-sm"}
              aria-label="Lọc theo màu"
            >
              <option value="">Tất cả màu</option>
              {facets.colors.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        <label className={compact ? "flex min-w-0 flex-col text-left" : "flex min-w-0 flex-col gap-1 text-left"}>
          <span className={compact ? "sr-only" : "text-xs font-medium text-gray-500"}>Giá từ (₫)</span>
          <input
            type="number"
            min={0}
            step={1000}
            placeholder={
              facets?.price_min != null ? formatVndHint(facets.price_min) : 'Tối thiểu'
            }
            value={minLocal}
            onChange={(e) => setMinLocal(e.target.value)}
            onBlur={applyPriceFilters}
            onKeyDown={(e) => {
              if (e.key === 'Enter') applyPriceFilters();
            }}
            className={compact ? "h-8 w-full min-w-0 rounded-md border border-gray-300 bg-white px-1.5 text-[11px] sm:w-[120px] sm:px-2 sm:text-xs" : "h-10 w-full rounded-lg border border-gray-300 bg-white px-2.5 py-2 text-xs sm:w-[140px] sm:px-3 sm:text-sm"}
            aria-label="Giá tối thiểu"
          />
        </label>

        <label className={compact ? "flex min-w-0 flex-col text-left" : "flex min-w-0 flex-col gap-1 text-left"}>
          <span className={compact ? "sr-only" : "text-xs font-medium text-gray-500"}>Đến (₫)</span>
          <input
            type="number"
            min={0}
            step={1000}
            placeholder={
              facets?.price_max != null ? formatVndHint(facets.price_max) : 'Tối đa'
            }
            value={maxLocal}
            onChange={(e) => setMaxLocal(e.target.value)}
            onBlur={applyPriceFilters}
            onKeyDown={(e) => {
              if (e.key === 'Enter') applyPriceFilters();
            }}
            className={compact ? "h-8 w-full min-w-0 rounded-md border border-gray-300 bg-white px-1.5 text-[11px] sm:w-[120px] sm:px-2 sm:text-xs" : "h-10 w-full rounded-lg border border-gray-300 bg-white px-2.5 py-2 text-xs sm:w-[140px] sm:px-3 sm:text-sm"}
            aria-label="Giá tối đa"
          />
        </label>

        <label className={compact ? "flex min-w-0 flex-col text-left" : "col-span-2 flex min-w-0 flex-col gap-1 text-left sm:col-span-1"}>
          <span className={compact ? "sr-only" : "text-xs font-medium text-gray-500"}>Sắp xếp</span>
          <select
            value={sort}
            onChange={(e) =>
              navigateWith({ sort: e.target.value || null, page: null })
            }
            className={compact ? "h-8 w-full min-w-0 rounded-md border border-gray-300 bg-white px-1.5 text-[11px] sm:min-w-[150px] sm:px-2 sm:text-xs" : "h-10 w-full rounded-lg border border-gray-300 bg-white px-2.5 py-2 text-xs sm:min-w-[160px] sm:px-3 sm:text-sm"}
            aria-label="Sắp xếp danh sách"
          >
            <option value="">Ngẫu nhiên</option>
            <option value="newest">Mới nhất</option>
            <option value="oldest">Cũ nhất</option>
            <option value="views_desc">Xem nhiều</option>
          </select>
        </label>
      </div>

      {hasActiveFilters ? (
        <div className={compact ? "flex justify-end leading-none" : "flex justify-end"}>
          <button
            type="button"
            onClick={() => router.push(basePath, { scroll: false })}
            className={compact ? "text-xs font-medium text-[#ea580c] hover:underline" : "rounded-full bg-orange-50 px-3 py-1.5 text-xs font-medium text-[#ea580c] hover:underline sm:bg-transparent sm:px-0 sm:py-0 sm:text-sm"}
          >
            Xóa bộ lọc
          </button>
        </div>
      ) : null}
    </div>
  );
}

function FiltersSkeleton() {
  return (
    <div
      className="w-full min-h-[100px] rounded-lg bg-gray-100 animate-pulse"
      aria-hidden
    />
  );
}

/** Giữ filter + page trong URL; đổi lọc → về trang 1. Bọc Suspense vì dùng `useSearchParams`. */
export default function CategoryProductFilters(props: Props) {
  return (
    <Suspense fallback={<FiltersSkeleton />}>
      <CategoryProductFiltersInner {...props} />
    </Suspense>
  );
}
