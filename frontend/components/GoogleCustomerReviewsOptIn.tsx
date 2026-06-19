'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  clearGoogleCustomerReviewsShowFlag,
  deliveryCountryForGoogleReviews,
  estimatedDeliveryDateForGoogleReviews,
  googleCustomerReviewsOptInStyle,
  googleCustomerReviewsPromptDelayMs,
  isLikelyMobileViewport,
  markGoogleCustomerReviewsHandled,
  maskEmailForGoogleCustomerReviews,
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
    gapi?: {
      load: (name: string, cb: () => void) => void;
      surveyoptin?: { render: (o: Record<string, unknown>) => void };
    };
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
  const cancelLoadRef = useRef<(() => void) | null>(null);
  const [promptOpen, setPromptOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  const email = (order.customer_email || '').trim();
  const orderId = (order.order_code || '').trim();
  const canRun = Boolean(merchantId && email && orderId && email.includes('@'));

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 767px)');
    const sync = () => setIsMobile(mq.matches);
    sync();
    mq.addEventListener('change', sync);
    return () => mq.removeEventListener('change', sync);
  }, []);

  useEffect(() => {
    if (!canRun) return;
    const delay = googleCustomerReviewsPromptDelayMs();
    const timer = window.setTimeout(() => setPromptOpen(true), delay);
    return () => window.clearTimeout(timer);
  }, [canRun]);

  useEffect(() => {
    if (!promptOpen) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prevOverflow;
    };
  }, [promptOpen]);

  useEffect(() => {
    return () => {
      cancelLoadRef.current?.();
    };
  }, []);

  const invokeGoogleRender = useCallback(() => {
    if (renderedRef.current || !canRun) {
      setSubmitting(false);
      return;
    }

    cancelLoadRef.current?.();
    window.___gcfg = { lang: 'vi' };

    const payload = {
      merchant_id: merchantId,
      order_id: orderId,
      email,
      delivery_country: deliveryCountryForGoogleReviews(order),
      estimated_delivery_date: estimatedDeliveryDateForGoogleReviews(order),
      opt_in_style: googleCustomerReviewsOptInStyle(),
    };

    let cancelled = false;
    let retryTimer: number | null = null;

    const cancel = () => {
      cancelled = true;
      if (retryTimer != null) {
        window.clearTimeout(retryTimer);
        retryTimer = null;
      }
    };
    cancelLoadRef.current = cancel;

    const attempt = (n = 0) => {
      if (cancelled || renderedRef.current) return;
      if (window.gapi?.load) {
        window.gapi.load('surveyoptin', function onSurveyReady() {
          if (cancelled || renderedRef.current) return;
          setPromptOpen(false);
          window.gapi?.surveyoptin?.render(payload);
          renderedRef.current = true;
          markGoogleCustomerReviewsHandled(order.id, 'accepted');
          if (clearShowFlagAfterRender) {
            clearGoogleCustomerReviewsShowFlag(order.id);
          }
          setSubmitting(false);
          cancelLoadRef.current = null;
        });
        return;
      }
      if (n < 24) {
        retryTimer = window.setTimeout(() => attempt(n + 1), 250);
      } else {
        setSubmitting(false);
        cancelLoadRef.current = null;
      }
    };

    const invokeRender = () => attempt();

    window.renderOptIn = invokeRender;

    const existing = document.querySelector('script[src*="apis.google.com/js/platform.js"]');
    if (existing) {
      invokeRender();
      if (!window.gapi) existing.addEventListener('load', invokeRender);
      return;
    }

    const script = document.createElement('script');
    script.src = PLATFORM_SCRIPT;
    script.async = true;
    script.defer = true;
    script.addEventListener('load', invokeRender);
    document.body.appendChild(script);
    invokeRender();
  }, [canRun, clearShowFlagAfterRender, email, merchantId, order, orderId]);

  const handleDecline = () => {
    markGoogleCustomerReviewsHandled(order.id, 'declined');
    clearGoogleCustomerReviewsShowFlag(order.id);
    setPromptOpen(false);
  };

  const handleAccept = () => {
    setSubmitting(true);
    invokeGoogleRender();
  };

  useEffect(() => {
    if (!promptOpen || submitting) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        markGoogleCustomerReviewsHandled(order.id, 'declined');
        clearGoogleCustomerReviewsShowFlag(order.id);
        setPromptOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [order.id, promptOpen, submitting]);

  if (!canRun || !promptOpen) return null;

  const maskedEmail = maskEmailForGoogleCustomerReviews(email);
  const mobile = isMobile || isLikelyMobileViewport();

  return (
    <div
      className={`fixed inset-0 z-[130] flex justify-center bg-black/50 ${
        mobile ? 'items-end p-0' : 'items-center p-4 sm:p-6'
      }`}
      role="dialog"
      aria-modal="true"
      aria-labelledby="gcr-prompt-title"
      onClick={handleDecline}
    >
      <div
        className={`w-full bg-white shadow-2xl border border-gray-100 overflow-hidden ${
          mobile
            ? 'max-w-none rounded-t-3xl border-b-0 max-h-[min(88dvh,640px)] flex flex-col'
            : 'max-w-md rounded-2xl'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {mobile ? (
          <div className="flex shrink-0 justify-center pt-2.5 pb-1" aria-hidden>
            <span className="h-1 w-10 rounded-full bg-gray-300" />
          </div>
        ) : null}

        <div className="bg-gradient-to-r from-orange-50 to-white px-5 py-4 border-b border-orange-100 shrink-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-[#ea580c]">188.com.vn</p>
          <h2 id="gcr-prompt-title" className="mt-1 text-lg font-bold text-gray-900 leading-snug">
            Chia sẻ trải nghiệm mua sắm?
          </h2>
        </div>

        <div
          className={`px-5 py-4 space-y-3 text-gray-700 leading-relaxed ${
            mobile ? 'overflow-y-auto text-[15px] flex-1' : 'text-sm'
          }`}
        >
          <p>
            {mobile
              ? 'Sau khi nhận hàng, Google có thể gửi email khảo sát ngắn để bạn đánh giá dịch vụ 188.com.vn.'
              : 'Sau khi nhận hàng, Google có thể gửi email khảo sát ngắn (~1 phút) để bạn đánh giá chất lượng dịch vụ của chúng tôi.'}
          </p>
          <p className="rounded-lg bg-gray-50 border border-gray-100 px-3 py-2.5 text-xs sm:text-sm text-gray-600 break-all">
            Email nhận khảo sát: <span className="font-medium text-gray-900">{maskedEmail}</span>
          </p>
        </div>

        <div
          className={`shrink-0 border-t border-gray-100 bg-white px-5 pt-3 ${
            mobile ? 'pb-[max(1rem,env(safe-area-inset-bottom))]' : 'pb-5'
          } flex flex-col gap-2 sm:flex-row sm:justify-end`}
        >
          <button
            type="button"
            onClick={handleAccept}
            disabled={submitting}
            className="inline-flex min-h-[48px] w-full sm:w-auto sm:min-w-[168px] items-center justify-center rounded-xl bg-[#ea580c] px-4 py-3 text-sm font-semibold text-white hover:bg-[#c2410c] active:bg-[#9a3412] disabled:opacity-60 touch-manipulation"
          >
            {submitting ? 'Đang mở xác nhận…' : 'Đồng ý nhận khảo sát'}
          </button>
          <button
            type="button"
            onClick={handleDecline}
            disabled={submitting}
            className="inline-flex min-h-[48px] w-full sm:w-auto items-center justify-center rounded-xl border border-gray-300 bg-white px-4 py-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 active:bg-gray-100 disabled:opacity-60 touch-manipulation"
          >
            Không, cảm ơn
          </button>
        </div>
      </div>
    </div>
  );
}
