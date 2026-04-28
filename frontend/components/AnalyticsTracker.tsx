'use client';

import { useEffect, useRef } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { trackEvent } from '@/lib/analytics';

export default function AnalyticsTracker() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const lastPathRef = useRef<string>('');

  useEffect(() => {
    const query = searchParams?.toString() ?? '';
    const path = `${pathname}${query ? `?${query}` : ''}`;
    if (lastPathRef.current === path) return;
    lastPathRef.current = path;
    trackEvent('page_view', {
      path,
      title: typeof document !== 'undefined' ? document.title : '',
    });
  }, [pathname, searchParams]);

  return null;
}
