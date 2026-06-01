'use client';

import { useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { useGoogleCustomerReviewsMerchantId } from '@/lib/use-google-customer-reviews-merchant-id';

const WIDGET_SCRIPT_SRC = 'https://www.gstatic.com/shopping/merchant/merchantwidget.js';
const SCRIPT_ID = 'merchantWidgetScript';

declare global {
  interface Window {
    merchantwidget?: {
      start: (opts: {
        merchant_id: number;
        region?: string;
        position?: string;
        language?: string;
      }) => void;
    };
  }
}

/** Huy hiệu Đánh giá khách hàng qua Google (điểm người bán) — bật/tắt qua admin google/customer_reviews. */
export default function GoogleCustomerReviewsBadge() {
  const merchantId = useGoogleCustomerReviewsMerchantId();
  const pathname = usePathname();
  const startedRef = useRef(false);

  useEffect(() => {
    if (!merchantId || startedRef.current) return;
    if (pathname?.startsWith('/admin')) return;

    const startBadge = () => {
      if (startedRef.current || !window.merchantwidget?.start) return;
      if (document.getElementById('google-merchantwidget-iframe-wrapper')) return;
      startedRef.current = true;
      try {
        window.merchantwidget.start({
          merchant_id: merchantId,
          region: 'VN',
          language: 'vi',
        });
      } catch {
        startedRef.current = false;
      }
    };

    const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
    if (existing) {
      if (window.merchantwidget) startBadge();
      else existing.addEventListener('load', startBadge);
      return () => existing.removeEventListener('load', startBadge);
    }

    const script = document.createElement('script');
    script.id = SCRIPT_ID;
    script.src = WIDGET_SCRIPT_SRC;
    script.defer = true;
    script.addEventListener('load', startBadge);
    document.body.appendChild(script);

    return () => {
      script.removeEventListener('load', startBadge);
    };
  }, [merchantId, pathname]);

  return null;
}
