// frontend/app/products/[slug]/components/ErrorState/ErrorState.tsx
'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { resolveProductGroupListingPath } from '@/lib/product-oos-redirect';

interface ErrorStateProps {
  error: string | null;
  /** Slug PDP đang mở — thử redirect nhóm OOS trước khi về trang chủ. */
  slug?: string;
}

const HOME_FALLBACK_DELAY_MS = 1200;

export default function ErrorState({ error, slug }: ErrorStateProps) {
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;
    let homeTimer: ReturnType<typeof setTimeout> | undefined;

    const scheduleHome = () => {
      homeTimer = setTimeout(() => {
        if (!cancelled) router.replace('/');
      }, HOME_FALLBACK_DELAY_MS);
    };

    const key = (slug || '').trim();
    if (!key) {
      scheduleHome();
      return () => {
        cancelled = true;
        if (homeTimer) clearTimeout(homeTimer);
      };
    }

    resolveProductGroupListingPath(key, { allowCache: true })
      .then((listingPath) => {
        if (cancelled) return;
        if (listingPath) {
          router.replace(listingPath);
          return;
        }
        scheduleHome();
      })
      .catch(() => {
        if (!cancelled) scheduleHome();
      });

    return () => {
      cancelled = true;
      if (homeTimer) clearTimeout(homeTimer);
    };
  }, [router, slug]);

  return (
    <div className="max-w-4xl mx-auto px-4 py-16 text-center">
      <div className="text-6xl mb-4">😢</div>
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Không tìm thấy sản phẩm</h1>
      <p className="text-gray-600 mb-2">{error}</p>
      <p className="text-gray-500 text-sm mb-6">
        Đang tìm nhóm sản phẩm liên quan hoặc chuyển về trang chủ sau 2 giây…
      </p>
      <Link 
        href="/"
        className="bg-[#ea580c] text-white px-6 py-3 rounded-lg hover:bg-[#c2410c] transition-colors inline-block"
      >
        ← Quay lại trang chủ
      </Link>
    </div>
  );
}
