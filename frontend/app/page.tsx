import HomePageClient from "./HomePageClient";
import { getInitialHomeProductList } from "@/lib/home-initial-feed";

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
  return Boolean(
    (spGet(sp, "q") ?? "").trim() ||
      (spGet(sp, "category") ?? "").trim() ||
      (spGet(sp, "subcategory") ?? "").trim() ||
      (spGet(sp, "sub_subcategory") ?? "").trim() ||
      (spGet(sp, "shop_id") ?? "").trim() ||
      (spGet(sp, "shop_name") ?? "").trim() ||
      (spGet(sp, "pro_lower_price") ?? "").trim() ||
      (spGet(sp, "pro_high_price") ?? "").trim() ||
      (spGet(sp, "min_price") ?? "").trim() ||
      (spGet(sp, "max_price") ?? "").trim()
  );
}

export default async function HomePage({
  searchParams,
}: {
  searchParams: Record<string, string | string[] | undefined>;
}) {
  const pageRaw = spGet(searchParams, "page");
  const currentPage = Math.max(
    1,
    Math.min(9999, parseInt(pageRaw || "1", 10) || 1)
  );
  const PAGE_SIZE = 48;
  const skip = (currentPage - 1) * PAGE_SIZE;

  const initialPlainHome = homeHasListingFilters(searchParams)
    ? null
    : await getInitialHomeProductList(skip, PAGE_SIZE);

  /** Nội dung không bọc Suspense riêng: layout đã có Suspense `{children}` với skeleton ổn định hơn. */
  return <HomePageClient initialPlainHome={initialPlainHome} />;
}
