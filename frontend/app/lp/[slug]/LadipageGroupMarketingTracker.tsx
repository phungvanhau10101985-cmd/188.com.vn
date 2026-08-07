'use client';

import type { Product } from '@/types/api';
import { useLadipageGroupMarketingView } from '@/lib/use-ladipage-group-marketing-view';

/**
 * Tracker gắn ở `/lp/[slug]/page.tsx` — chỉ cho Ladipage nhiều SP / danh mục.
 * Tách khỏi UI để sự kiện Meta + TikTok + Google luôn bắn khi có danh sách SP.
 */
export default function LadipageGroupMarketingTracker({
  products,
  listName,
}: {
  products: Product[];
  listName?: string;
}) {
  useLadipageGroupMarketingView(products.length >= 2 ? products : null, listName);
  return null;
}
