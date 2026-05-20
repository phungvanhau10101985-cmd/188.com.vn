import type { Metadata } from 'next';
import HomePageClient from "./HomePageClient";
import { getInitialHomeProductList } from "@/lib/home-initial-feed";
import { getInitialHomeHeroCategories } from "@/lib/home-hero-categories";
import {
  buildHomeCanonicalWithFilters,
  buildHomeFilterTitleParts,
  homeHasListingFiltersFromSp,
  homeUrlNeedsFilteredMeta,
} from '@/lib/filtered-listing-metadata';
import { getListingFreshnessMonthLabel } from '@/lib/listing-freshness-label';

function spGet(
  sp: Record<string, string | string[] | undefined>,
  key: string
): string | undefined {
  const v = sp[key];
  if (Array.isArray(v)) return v[0];
  return v;
}

/** Trang chủ có tham số lọc/tìm — không dùng SSR danh sách mặc định. */
function homeHasListingFilters(
  sp: Record<string, string | string[] | undefined>
): boolean {
  return homeHasListingFiltersFromSp(sp);
}

export async function generateMetadata({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<Metadata> {
  const sp = await searchParams;
  if (!homeUrlNeedsFilteredMeta(sp)) return {};

  const bits = buildHomeFilterTitleParts(sp);
  let title = bits.join(' · ');
  if (title.length > 68) title = `${title.slice(0, 65)}…`;

  const month = getListingFreshnessMonthLabel();
  const description = (
    bits.length
      ? `Danh sách sản phẩm đã lọc trên 188.COM.VN (${bits.slice(0, 4).join(', ')})`
      : 'Danh sách sản phẩm đã lọc trên 188.COM.VN.'
  ).concat(` Cập nhật ${month}.`);

  const canonical = buildHomeCanonicalWithFilters(sp);

  return {
    title: title.trim() ? title : `Lọc sản phẩm`,
    description: description.slice(0, 160),
    alternates: { canonical },
    robots: { index: true, follow: true },
  };
}

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const resolvedSearchParams = await searchParams;
  const pageRaw = spGet(resolvedSearchParams, "page");
  const currentPage = Math.max(
    1,
    Math.min(9999, parseInt(pageRaw || "1", 10) || 1)
  );
  const PAGE_SIZE = 48;
  const skip = (currentPage - 1) * PAGE_SIZE;

  const hasFilters = homeHasListingFilters(resolvedSearchParams);
  const initialPlainHome = hasFilters ? null : await getInitialHomeProductList(skip, PAGE_SIZE);
  const initialHeroCategories = hasFilters ? null : await getInitialHomeHeroCategories('Nam', 16);

  /** Nội dung không bọc Suspense riêng: layout đã có Suspense `{children}` với skeleton ổn định hơn. */
  return (
    <HomePageClient
      initialPlainHome={initialPlainHome}
      initialHeroCategories={initialHeroCategories}
    />
  );
}
