'use client';

import GoogleCustomerReviewsOptIn, { type GoogleCustomerReviewsOrder } from '@/components/GoogleCustomerReviewsOptIn';
import {
  isOrderEligibleForGoogleReviewsOptIn,
  shouldShowGoogleCustomerReviewsForOrder,
} from '@/lib/google-customer-reviews';
import { useGoogleCustomerReviewsMerchantId } from '@/lib/use-google-customer-reviews-merchant-id';

type Props = {
  order: GoogleCustomerReviewsOrder & { status?: string };
};

/** Opt-in GCR trên trang xác nhận đơn — chỉ khi admin bật và trong cửa sổ sau đặt hàng. */
export default function OrderGoogleCustomerReviews({ order }: Props) {
  const merchantId = useGoogleCustomerReviewsMerchantId();

  if (!merchantId || !order?.id) return null;
  if (!isOrderEligibleForGoogleReviewsOptIn(order)) return null;
  if (!shouldShowGoogleCustomerReviewsForOrder(order.id, order.created_at)) return null;

  return <GoogleCustomerReviewsOptIn merchantId={merchantId} order={order} />;
}
