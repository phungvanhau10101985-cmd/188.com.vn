'use client';

import Link from 'next/link';

interface OrderItemLike {
  product_id?: number | null;
}

interface OrderLike {
  id: number;
  status: string;
  items?: OrderItemLike[];
}

const REVIEWABLE_STATUSES = ['delivered', 'completed'];

export function canOrderBeReviewed(order: OrderLike): boolean {
  return REVIEWABLE_STATUSES.includes(order.status);
}

export function getUniqueReviewableProductIds(order: OrderLike): number[] {
  if (!canOrderBeReviewed(order)) return [];
  const ids = (order.items || [])
    .map((i) => i.product_id)
    .filter((id): id is number => id != null);
  return [...new Set(ids)];
}

export function getUnreviewedProductIds(order: OrderLike, reviewedProductIds: Set<number>): number[] {
  return getUniqueReviewableProductIds(order).filter((id) => !reviewedProductIds.has(id));
}

interface OrderReviewActionsProps {
  order: OrderLike;
  reviewedProductIds: Set<number>;
  onReviewProduct: (productId: number) => void;
  /** Nút chính (cam) */
  primaryClassName?: string;
  /** Nút phụ (xám) */
  secondaryClassName?: string;
}

const defaultPrimary =
  'inline-flex min-h-[44px] items-center px-4 py-2 bg-[#ea580c] text-white rounded-lg text-sm font-medium hover:bg-[#c2410c] active:bg-[#c2410c]';
const defaultSecondary =
  'inline-flex min-h-[44px] items-center px-4 py-2 bg-gray-200 text-gray-800 rounded-lg text-sm font-medium hover:bg-gray-300 active:bg-gray-300';

export default function OrderReviewActions({
  order,
  reviewedProductIds,
  onReviewProduct,
  primaryClassName = defaultPrimary,
  secondaryClassName = defaultSecondary,
}: OrderReviewActionsProps) {
  if (!canOrderBeReviewed(order)) return null;

  const uniqueIds = getUniqueReviewableProductIds(order);
  if (uniqueIds.length === 0) return null;

  const unreviewed = getUnreviewedProductIds(order, reviewedProductIds);

  if (unreviewed.length === 0) {
    return (
      <Link href={`/account/orders/${order.id}/review`} className={secondaryClassName}>
        Xem đánh giá
      </Link>
    );
  }

  if (unreviewed.length === 1) {
    return (
      <button type="button" onClick={() => onReviewProduct(unreviewed[0])} className={primaryClassName}>
        Đánh giá
      </button>
    );
  }

  return (
    <Link href={`/account/orders/${order.id}/review`} className={primaryClassName}>
      Đánh giá ({unreviewed.length} sản phẩm)
    </Link>
  );
}
