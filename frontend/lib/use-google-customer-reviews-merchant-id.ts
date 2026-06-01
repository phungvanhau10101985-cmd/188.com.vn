'use client';

import { useEffect, useState } from 'react';
import { useGoogleCustomerReviewsMerchantIdFromLayout } from '@/components/GoogleCustomerReviewsMerchantProvider';
import { getApiBaseUrl } from '@/lib/api-base';

export function useGoogleCustomerReviewsMerchantId(): number | null {
  const fromLayout = useGoogleCustomerReviewsMerchantIdFromLayout();
  const [merchantId, setMerchantId] = useState<number | null>(
    fromLayout === undefined ? null : fromLayout,
  );

  useEffect(() => {
    if (fromLayout !== undefined) {
      setMerchantId(fromLayout);
      return;
    }
    const base = getApiBaseUrl();
    let cancelled = false;
    fetch(`${base}/embed-codes/public`, { cache: 'no-store' })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: { google_customer_reviews_merchant_id?: unknown } | null) => {
        if (cancelled || !data) return;
        const raw = data.google_customer_reviews_merchant_id;
        const n = typeof raw === 'number' ? raw : Number.parseInt(String(raw ?? ''), 10);
        if (Number.isFinite(n) && n > 0) setMerchantId(n);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [fromLayout]);

  return fromLayout !== undefined ? fromLayout : merchantId;
}
