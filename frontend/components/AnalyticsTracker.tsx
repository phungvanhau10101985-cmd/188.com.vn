'use client';

import { useEffect, useRef } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { trackEvent } from '@/lib/analytics';
import { trackMetaPageView } from '@/lib/meta-pixel';
import { trackTikTokPageView } from '@/lib/tiktok-pixel';
import { trackGoogleAdsRouteRetail } from '@/lib/google-ads-gtag';
import { persistMetaClickIds, patchMetaAdvancedMatching, resetMetaAdvancedMatching } from '@/lib/meta-attribution';
import { useAuth } from '@/features/auth/hooks/useAuth';

export default function AnalyticsTracker() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { user, isAuthenticated } = useAuth();
  const lastPathRef = useRef<string>('');
  /** Chuỗi ổn định — tránh effect chạy lại khi object `searchParams` đổi tham chiếu (Next.js). */
  const searchKey = searchParams?.toString() ?? '';

  useEffect(() => {
    persistMetaClickIds();
    if (isAuthenticated && user) {
      patchMetaAdvancedMatching({
        email: user.email,
        phone: user.phone,
        fullName: user.full_name,
        gender: user.gender,
        dateOfBirth: user.date_of_birth ? String(user.date_of_birth) : null,
        userId: user.id,
        country: 'vn',
      });
    } else if (!isAuthenticated) {
      resetMetaAdvancedMatching();
    }
  }, [
    isAuthenticated,
    user?.id,
    user?.email,
    user?.phone,
    user?.full_name,
    user?.gender,
    user?.date_of_birth,
  ]);

  useEffect(() => {
    persistMetaClickIds();
    const path = `${pathname}${searchKey ? `?${searchKey}` : ''}`;
    if (lastPathRef.current === path) return;
    lastPathRef.current = path;
    trackEvent('page_view', {
      path,
      title: typeof document !== 'undefined' ? document.title : '',
    });
    trackMetaPageView(path);
    trackTikTokPageView(path);
    trackGoogleAdsRouteRetail(path);
  }, [pathname, searchKey]);

  return null;
}
