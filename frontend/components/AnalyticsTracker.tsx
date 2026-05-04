'use client';

import { useEffect, useRef } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { trackEvent } from '@/lib/analytics';
import { trackMetaPageView } from '@/lib/meta-pixel';

export default function AnalyticsTracker() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const lastPathRef = useRef<string>('');
  /** Chuỗi ổn định — tránh effect chạy lại khi object `searchParams` đổi tham chiếu (Next.js). */
  const searchKey = searchParams?.toString() ?? '';

  useEffect(() => {
    const path = `${pathname}${searchKey ? `?${searchKey}` : ''}`;
    if (lastPathRef.current === path) return;
    lastPathRef.current = path;
    trackEvent('page_view', {
      path,
      title: typeof document !== 'undefined' ? document.title : '',
    });
    trackMetaPageView(path);
  }, [pathname, searchKey]);

  return null;
}
