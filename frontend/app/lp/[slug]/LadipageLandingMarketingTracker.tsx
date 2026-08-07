'use client';

import type { Product } from '@/types/api';
import { useLadipageLandingSeedView } from '@/lib/use-ladipage-group-marketing-view';

/**
 * Vào `/lp` nhiều SP: seed remarketing bằng top 2 SP (không cả lưới).
 * Modal mua / PDP bổ sung ViewContent từng SP khách chọn.
 */
export default function LadipageLandingMarketingTracker({
  products,
  listName,
}: {
  products: Product[];
  listName?: string;
}) {
  useLadipageLandingSeedView(products.length > 0 ? products : null, listName);
  return null;
}
