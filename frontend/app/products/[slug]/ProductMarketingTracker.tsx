'use client';

import type { Product } from '@/types/api';
import { useProductMarketingView } from '@/lib/use-product-marketing-view';

/**
 * Tracker gắn ở `page.tsx` — luôn chạy trên PDP có/không ladipage.
 * Tách khỏi shell UI để lỗi hydrate/render ladipage không nuốt ViewContent / view_item.
 */
export default function ProductMarketingTracker({
  product,
  slug,
}: {
  product: Product;
  slug: string;
}) {
  useProductMarketingView(product, slug);
  return null;
}
