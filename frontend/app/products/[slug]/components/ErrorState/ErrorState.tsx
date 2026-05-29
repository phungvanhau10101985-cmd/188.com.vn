// frontend/app/products/[slug]/components/ErrorState/ErrorState.tsx
'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

interface ErrorStateProps {
  error: string | null;
}

const REDIRECT_DELAY_MS = 2000;

export default function ErrorState({ error }: ErrorStateProps) {
  const router = useRouter();

  useEffect(() => {
    const timer = setTimeout(() => {
      router.replace('/');
    }, REDIRECT_DELAY_MS);
    return () => clearTimeout(timer);
  }, [router]);

  return (
    <div className="max-w-4xl mx-auto px-4 py-16 text-center">
      <div className="text-6xl mb-4">😢</div>
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Không tìm thấy sản phẩm</h1>
      <p className="text-gray-600 mb-2">{error}</p>
      <p className="text-gray-500 text-sm mb-6">Đang chuyển về trang chủ sau 2 giây…</p>
      <Link 
        href="/"
        className="bg-[#ea580c] text-white px-6 py-3 rounded-lg hover:bg-[#c2410c] transition-colors inline-block"
      >
        ← Quay lại trang chủ
      </Link>
    </div>
  );
}
