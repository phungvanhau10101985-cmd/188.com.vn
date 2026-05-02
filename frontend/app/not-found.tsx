'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

export default function NotFound() {
  const router = useRouter();

  useEffect(() => {
    const id = window.setTimeout(() => {
      router.replace('/');
    }, 1000);
    return () => window.clearTimeout(id);
  }, [router]);

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center px-4 text-center">
      <p className="text-6xl font-bold text-[#ea580c] mb-2 tabular-nums">404</p>
      <p className="text-gray-800 font-medium mb-1">Không tìm thấy trang</p>
      <p className="text-sm text-gray-500 mb-6">Đang chuyển về trang chủ sau 1 giây…</p>
      <Link href="/" className="text-[#ea580c] font-semibold hover:underline">
        Về trang chủ ngay
      </Link>
    </div>
  );
}
