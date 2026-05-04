'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/** Legacy URL: checkout được gộp vào /cart (giỏ + địa chỉ + đặt hàng). */
export default function CheckoutRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/cart');
  }, [router]);
  return (
    <div className="min-h-[40vh] flex items-center justify-center px-6 text-sm text-gray-600">
      Đang chuyển tới giỏ hàng...
    </div>
  );
}
