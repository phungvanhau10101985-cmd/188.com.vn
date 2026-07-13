'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect, useState } from 'react';
import { getApiBaseUrl } from '@/lib/api-base';

type UnsubscribeState = 'loading' | 'success' | 'error' | 'missing';

type UnsubscribeResult = {
  ok: boolean;
  message: string;
  email_masked?: string;
  already_unsubscribed?: boolean;
};

function UnsubscribeContent() {
  const searchParams = useSearchParams();
  const token = (searchParams.get('token') || '').trim();
  const [state, setState] = useState<UnsubscribeState>(token ? 'loading' : 'missing');
  const [message, setMessage] = useState('');
  const [emailMasked, setEmailMasked] = useState('');

  const runUnsubscribe = useCallback(async () => {
    if (!token) {
      setState('missing');
      setMessage('Liên kết ngừng nhận tin không hợp lệ.');
      return;
    }
    setState('loading');
    try {
      const res = await fetch(
        `${getApiBaseUrl()}/email/unsubscribe?token=${encodeURIComponent(token)}`,
        { method: 'GET', cache: 'no-store' },
      );
      const data = (await res.json().catch(() => ({}))) as UnsubscribeResult & { detail?: string };
      if (!res.ok) {
        throw new Error(
          typeof data.detail === 'string'
            ? data.detail
            : data.message || 'Không thể xử lý yêu cầu ngừng nhận tin.',
        );
      }
      setMessage(data.message || 'Bạn đã ngừng nhận tin khuyến mãi.');
      setEmailMasked(data.email_masked || '');
      setState('success');
    } catch (err) {
      setState('error');
      setMessage(err instanceof Error ? err.message : 'Không thể xử lý yêu cầu ngừng nhận tin.');
    }
  }, [token]);

  useEffect(() => {
    void runUnsubscribe();
  }, [runUnsubscribe]);

  return (
    <div className="w-full max-w-md mx-auto">
      <div className="bg-white rounded-2xl shadow border border-gray-200 p-6 sm:p-8">
        <div className="text-center mb-6">
          <h1 className="text-xl font-bold text-gray-900">Ngừng nhận tin khuyến mãi</h1>
          <p className="text-sm text-gray-500 mt-1">188.com.vn</p>
        </div>

        {state === 'loading' && (
          <div className="text-center py-6">
            <div className="inline-block h-8 w-8 animate-spin rounded-full border-2 border-orange-500 border-t-transparent" aria-hidden />
            <p className="mt-4 text-sm text-gray-600">Đang xử lý yêu cầu của bạn…</p>
          </div>
        )}

        {state === 'success' && (
          <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-sm text-green-800">
            <p className="font-medium">Đã ghi nhận</p>
            <p className="mt-2">{message}</p>
            {emailMasked ? (
              <p className="mt-2 text-green-700">Email: {emailMasked}</p>
            ) : null}
            <p className="mt-3 text-green-700">
              Bạn vẫn nhận email về đơn hàng, giao hàng và xác minh tài khoản như bình thường.
            </p>
          </div>
        )}

        {(state === 'error' || state === 'missing') && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
            <p>{message}</p>
            {state === 'error' && token ? (
              <button
                type="button"
                onClick={() => void runUnsubscribe()}
                className="mt-3 underline font-medium"
              >
                Thử lại
              </button>
            ) : null}
          </div>
        )}

        <p className="mt-6 text-center text-sm text-gray-500">
          <Link href="/" className="text-orange-600 font-medium hover:underline">
            Về trang chủ
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function MarketingUnsubscribePage() {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 px-4 sm:px-6">
      <Suspense
        fallback={
          <div className="text-center text-sm text-gray-500">Đang tải…</div>
        }
      >
        <UnsubscribeContent />
      </Suspense>
    </div>
  );
}
