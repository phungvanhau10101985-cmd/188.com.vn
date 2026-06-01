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

    renderedRef.current = true;
    window.___gcfg = { lang: 'vi' };

    const payload = {
      merchant_id: merchantId,
      order_id: orderId,
      email,
      delivery_country: deliveryCountryForGoogleReviews(order),
      estimated_delivery_date: estimatedDeliveryDateForGoogleReviews(order),
      opt_in_style: 'BOTTOM_TRAY',
    };

    window.renderOptIn = function renderOptIn() {
      if (!window.gapi?.load) return;
      window.gapi.load('surveyoptin', function onSurveyReady() {
        window.gapi?.surveyoptin?.render(payload);
      });
    };

    const existing = document.querySelector(`script[src="${PLATFORM_SCRIPT}"]`);
    if (existing) {
      if (window.gapi) {
        window.renderOptIn();
      }
    } else {
      const script = document.createElement('script');
      script.src = PLATFORM_SCRIPT;
      script.async = true;
      script.defer = true;
      document.body.appendChild(script);
    }

    if (clearShowFlagAfterRender) {
      clearGoogleCustomerReviewsShowFlag(order.id);
    }
  }, [merchantId, order, clearShowFlagAfterRender]);

  return null;
}
