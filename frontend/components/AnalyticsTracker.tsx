'use client';

import { useEffect, useRef } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { trackEvent } from '@/lib/analytics';
import { trackMetaPageView, trackMetaViewContentProduct } from '@/lib/meta-pixel';
import { trackGoogleAdsRouteRetail } from '@/lib/google-ads-gtag';

export default function AnalyticsTracker() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const lastPathRef = useRef<string>('');
  const lastPdpFallbackPathRef = useRef<string>('');
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
    trackGoogleAdsRouteRetail(path);
  }, [pathname, searchKey]);

  useEffect(() => {
    if (!pathname?.startsWith('/products/')) return;
    const path = `${pathname}${searchKey ? `?${searchKey}` : ''}`;
    if (lastPdpFallbackPathRef.current === path) return;
    lastPdpFallbackPathRef.current = path;

    const parts = pathname.split('/').filter(Boolean);
    const rawSlug = parts[1] || '';
    if (!rawSlug) return;

    let cancelled = false;
    const decodedSlug = (() => {
      try {
        return decodeURIComponent(rawSlug);
      } catch {
        return rawSlug;
      }
    })();

    const tid = window.setTimeout(() => {
      void fetch(
        `/api/v1/products/by-slug/${encodeURIComponent(decodedSlug)}?attach_group_listing=true`,
        { method: 'GET', cache: 'no-store' }
      )
        .then(async (res) => {
          if (!res.ok) return null;
          return (await res.json()) as Record<string, unknown> | null;
        })
        .then((product) => {
          if (cancelled || !product) return;
          const id = Number(product.id);
          if (!Number.isFinite(id) || id <= 0) return;
          trackMetaViewContentProduct(product as any, { routeKey: path });
        })
        .catch(() => {
          /* fallback best-effort */
        });
    }, 180);

    return () => {
      cancelled = true;
      window.clearTimeout(tid);
    };
  }, [pathname, searchKey]);

  return null;
}
