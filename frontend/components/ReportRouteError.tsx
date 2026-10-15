'use client';

import { useEffect } from 'react';
import { reportSiteError } from '@/lib/report-site-error';

/** Ghi lỗi từ error boundary của Next (trang giỏ, sản phẩm, thanh toán…). */
export default function ReportRouteError({
  error,
}: {
  error: Error & { digest?: string };
}) {
  useEffect(() => {
    reportSiteError({
      message: error?.message || 'Lỗi trang',
      stack: error?.stack,
      digest: error?.digest,
    });
  }, [error]);
  return null;
}
