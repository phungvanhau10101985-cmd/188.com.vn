import type { Product } from '@/types/api';

/** Gộp batch SP cùng shop — bỏ trùng id. */
export function mergeSameShopProductBatch(
  prev: Product[],
  batch: Product[]
): { merged: Product[]; addedCount: number } {
  if (!batch.length) {
    return { merged: prev, addedCount: 0 };
  }
  const seen = new Set(prev.map((p) => p.id));
  const merged = [...prev];
  let addedCount = 0;
  for (const p of batch) {
    if (seen.has(p.id)) continue;
    seen.add(p.id);
    merged.push(p);
    addedCount += 1;
  }
  return { merged, addedCount };
}

/**
 * Total từ API có thể là pool DB; nếu batch đầu < limit thì thường đã hết SP hiển thị được.
 */
export function normalizeSameShopTotal(
  loadedCount: number,
  reportedTotal: number,
  pageLimit: number
): number {
  const reported = Math.max(0, reportedTotal);
  if (loadedCount > 0 && loadedCount < pageLimit && reported > loadedCount) {
    return loadedCount;
  }
  return reported;
}

/** Hết dữ liệu phân trang — dừng «Xem thêm». */
export function sameShopTotalWhenExhausted(currentLength: number): number {
  return Math.max(0, currentLength);
}
