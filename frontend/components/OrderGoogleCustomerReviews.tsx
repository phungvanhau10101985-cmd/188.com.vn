'use client';

import GoogleCustomerReviewsOptIn, { type GoogleCustomerReviewsOrder } from '@/components/GoogleCustomerReviewsOptIn';
import { useAuth } from '@/features/auth/hooks/useAuth';
import {
  isOrderEligibleForGoogleReviewsOptIn,
  markGoogleCustomerReviewsForOrder,
  shouldShowGoogleCustomerReviewsForOrder,
} from '@/lib/google-customer-reviews';
import { useGoogleCustomerReviewsMerchantId } from '@/lib/use-google-customer-reviews-merchant-id';
import { useEffect } from 'react';

type Props = {
  order: GoogleCustomerReviewsOrder & {
    status?: string;
    requires_deposit?: boolean;
    deposit_paid?: number | string | null;
  };
  /** Trang «đã cọc» — luôn thử hiện tray Google (không phụ thuộc session 48h). */
  showAfterDepositSuccess?: boolean;
};

/** Opt-in GCR trên trang xác nhận đơn — chỉ khi admin bật và trong cửa sổ sau đặt hàng. */
export default function OrderGoogleCustomerReviews({ order, showAfterDepositSuccess = false }: Props) {
  const merchantId = useGoogleCustomerReviewsMerchantId();
  const { user } = useAuth();

  useEffect(() => {
    if (showAfterDepositSuccess && order?.id) {
      markGoogleCustomerReviewsForOrder(order.id);
    }
  }, [showAfterDepositSuccess, order?.id]);

  if (!merchantId || !order?.id) return null;
  if (!isOrderEligibleForGoogleReviewsOptIn(order)) return null;

  const inShowWindow =
    showAfterDepositSuccess ||
    shouldShowGoogleCustomerReviewsForOrder(order.id, order.created_at);
  if (!inShowWindow) return null;

  const accountEmail = (user?.email || '').trim();
  const orderEmail = (order.customer_email || '').trim();
  const customer_email = orderEmail.includes('@') ? orderEmail : accountEmail.includes('@') ? accountEmail : orderEmail;

  return (
    <GoogleCustomerReviewsOptIn
      merchantId={merchantId}
      order={{ ...order, customer_email }}
    />
  );
}
