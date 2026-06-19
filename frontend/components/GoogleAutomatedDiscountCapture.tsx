'use client';

import { useEffect } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import {
  capturePv2FromLocation,
  extractPv2FromSearch,
} from '@/lib/google-automated-discount';

/**
 * Đọc pv2 từ URL (quảng cáo Mua sắm) và lưu phiên giá chiết khấu Google.
 */
export default function GoogleAutomatedDiscountCapture() {
  const searchParams = useSearchParams();
  const pathname = usePathname();

  useEffect(() => {
    const search = searchParams?.toString() ? `?${searchParams.toString()}` : window.location.search;
    const token = extractPv2FromSearch(search);
    if (!token) return;

    let cancelled = false;
    capturePv2FromLocation(search)
      .then(() => {
        if (cancelled || typeof window === 'undefined') return;
        // Giữ pv2 trên URL để Google kiểm tra tích hợp; không xóa tham số.
      })
      .catch((err) => {
        if (cancelled) return;
        console.warn('[GoogleAutomatedDiscount]', err instanceof Error ? err.message : err);
      });

    return () => {
      cancelled = true;
    };
  }, [pathname, searchParams]);

  return null;
}
