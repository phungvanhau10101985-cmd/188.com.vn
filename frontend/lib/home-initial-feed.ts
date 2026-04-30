/**
 * SSR: danh sách sản phẩm trang chủ (không lọc URL) — giảm LCP/FCP mobile bằng cách
 * có dữ liệu ngay trước khi client fetch home-feed cá nhân hóa.
 */

import type { ProductListResponse } from "@/types/api";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001/api/v1";

const LAYOUT_FETCH_TIMEOUT_MS = 8000;
const isDev = process.env.NODE_ENV === "development";
const disableCache =
  process.env.NEXT_PUBLIC_DISABLE_CACHE === "1" ||
  process.env.DISABLE_CACHE === "1";
const REVALIDATE_HOME = isDev || disableCache ? 0 : 45;

export async function getInitialHomeProductList(
  skip = 0,
  limit = 48
): Promise<ProductListResponse | null> {
  try {
    const params = new URLSearchParams({
      skip: String(skip),
      limit: String(limit),
      is_active: "true",
    });
    const res = await fetch(`${API_BASE}/products/?${params}`, {
      next: { revalidate: REVALIDATE_HOME },
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.timeout(LAYOUT_FETCH_TIMEOUT_MS),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as ProductListResponse;
    if (!Array.isArray(data?.products)) return null;
    const pageNum = Math.floor(skip / limit) + 1;
    return {
      ...data,
      page: pageNum,
      size: limit,
    };
  } catch {
    return null;
  }
}
