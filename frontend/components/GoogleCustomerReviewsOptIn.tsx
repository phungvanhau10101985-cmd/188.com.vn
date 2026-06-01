'use client';

import { useEffect, useRef } from 'react';
import {
  clearGoogleCustomerReviewsShowFlag,
  deliveryCountryForGoogleReviews,
  estimatedDeliveryDateForGoogleReviews,
} from '@/lib/google-customer-reviews';

export type GoogleCustomerReviewsOrder = {
  id: number;
  order_code: string;
  customer_email?: string | null;
  estimated_delivery?: string | null;
  created_at?: string | null;
  customer_address?: string | null;
};

declare global {
  interface Window {
    renderOptIn?: () => void;
    gapi?: { load: (name: string, cb: () => void) => void; surveyoptin?: { render: (o: Record<string, unknown>) => void } };
    ___gcfg?: { lang: string };
  }
}

const PLATFORM_SCRIPT = 'https://apis.google.com/js/platform.js?onload=renderOptIn';

type Props = {
  merchantId: number;
  order: GoogleCustomerReviewsOrder;
  /** Sau khi gọi render — xóa cờ session «vừa đặt hàng». */
  clearShowFlagAfterRender?: boolean;
};

export default function GoogleCustomerReviewsOptIn({
  merchantId,
  order,
  clearShowFlagAfterRender = true,
}: Props) {
  const renderedRef = useRef(false);

  useEffect(() => {
    if (!merchantId || renderedRef.current) return;
    const email = (order.customer_email || '').trim();
    const orderId = (order.order_code || '').trim();
    if (!email || !orderId || !email.includes('@')) return;

    window.___gcfg = { lang: 'vi' };

    const payload = {
      merchant_id: merchantId,
      order_id: orderId,
      email,
      delivery_country: deliveryCountryForGoogleReviews(order),
      estimated_delivery_date: estimatedDeliveryDateForGoogleReviews(order),
      opt_in_style: 'BOTTOM_TRAY',
    };

    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const invokeRender = () => {
      const attempt = (n = 0) => {
        if (cancelled || renderedRef.current) return;
        if (window.gapi?.load) {
          window.gapi.load('surveyoptin', function onSurveyReady() {
            if (cancelled || renderedRef.current) return;
            window.gapi?.surveyoptin?.render(payload);
            renderedRef.current = true;
            if (clearShowFlagAfterRender) {
              clearGoogleCustomerReviewsShowFlag(order.id);
            }
          });
          return;
        }
        if (n < 24) {
          retryTimer = setTimeout(() => attempt(n + 1), 250);
        }
      };
      attempt();
    };

    window.renderOptIn = invokeRender;

    const existing = document.querySelector('script[src*="apis.google.com/js/platform.js"]');
    if (existing) {
      invokeRender();
      if (!window.gapi) existing.addEventListener('load', invokeRender);
      return () => {
        cancelled = true;
        if (retryTimer) clearTimeout(retryTimer);
        existing.removeEventListener('load', invokeRender);
      };
    }

    const script = document.createElement('script');
    script.src = PLATFORM_SCRIPT;
    script.async = true;
    script.defer = true;
    script.addEventListener('load', invokeRender);
    document.body.appendChild(script);
    invokeRender();

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      script.removeEventListener('load', invokeRender);
    };
  }, [merchantId, order, clearShowFlagAfterRender]);

  return null;
}
