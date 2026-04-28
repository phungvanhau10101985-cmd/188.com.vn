'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Suspense } from 'react';

function CompleteInner() {
  const sp = useSearchParams();
  const code = sp.get('code') || '';
  const needsDeposit = sp.get('needs_deposit') === '1';

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-6 py-12">
      <div className="bg-white border border-gray-200 rounded-2xl p-8 max-w-lg w-full text-center shadow-sm">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Cảm ơn bạn đã đặt hàng</h1>
        {code ? (
          <p className="text-sm text-gray-700 mb-2">
            Mã đơn: <strong className="text-orange-600">{code}</strong>
          </p>
        ) : null}
        <p className="text-sm text-gray-600 mb-6">
          Chúng tôi đã ghi nhận đơn hàng. Thông tin xác nhận sẽ được gửi qua email bạn đã nhập (nếu có cấu hình gửi
          mail).
        </p>
        {needsDeposit ? (
          <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-lg text-amber-900 text-sm text-left">
            Đơn hàng cần đặt cọc. Vui lòng{' '}
            <Link href="/auth/login?redirect=/account/orders" className="underline font-medium">
              đăng nhập
            </Link>{' '}
            cùng email đã đặt hàng để xem đơn và thanh toán cọc, hoặc liên hệ hỗ trợ kèm mã đơn.
          </div>
        ) : null}
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            href="/"
            className="px-5 py-2.5 bg-orange-500 text-white rounded-lg font-medium hover:bg-orange-600 text-center"
          >
            Về trang chủ
          </Link>
          <Link
            href="/auth/login?redirect=/account/orders"
            className="px-5 py-2.5 border border-gray-300 rounded-lg font-medium hover:bg-gray-50 text-center"
          >
            Đăng nhập để theo dõi đơn
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function CheckoutCompletePage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-gray-50 flex items-center justify-center text-gray-600 text-sm">
          Đang tải…
        </div>
      }
    >
      <CompleteInner />
    </Suspense>
  );
}
