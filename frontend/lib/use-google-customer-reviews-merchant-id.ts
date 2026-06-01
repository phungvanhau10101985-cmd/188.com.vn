'use client';

import { useEffect, useState } from 'react';

export function useGoogleCustomerReviewsMerchantId(): number | null {
  const [merchantId, setMerchantId] = useState<number | null>(null);

  useEffect(() => {
    const base = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, '') || 'http://localhost:8001/api/v1';
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
  }, []);

  return merchantId;
}
