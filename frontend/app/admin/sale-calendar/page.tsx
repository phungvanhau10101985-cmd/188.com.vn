'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/** Trang cũ — cài đặt sale đã gộp vào Khuyến mãi. */
export default function AdminSaleCalendarRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/admin/promotions#site-sale');
  }, [router]);

  return (
    <div className="p-6 text-sm text-gray-500">
      Đang chuyển sang Khuyến mãi…
    </div>
  );
}
