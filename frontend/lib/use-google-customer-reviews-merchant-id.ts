'use client';

import { useEffect, useState } from 'react';
import { useGoogleCustomerReviewsMerchantIdFromLayout } from '@/components/GoogleCustomerReviewsMerchantProvider';
import { fetchPublicSiteEmbeds } from '@/lib/site-embeds-public';

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
    let cancelled = false;
    fetchPublicSiteEmbeds()
      .then((data) => {
        if (cancelled) return;
        const n = data.googleCustomerReviewsMerchantId;
        if (typeof n === 'number' && n > 0) setMerchantId(n);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [fromLayout]);

  return fromLayout !== undefined ? fromLayout : merchantId;
}
