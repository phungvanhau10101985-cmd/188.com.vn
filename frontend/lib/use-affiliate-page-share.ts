'use client';

import { useCallback, useMemo } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { useToast } from '@/components/ToastProvider';
import { appendReferralToUrl } from '@/lib/affiliate-ref';
import { useApprovedAffiliate } from '@/lib/use-approved-affiliate';

type ShareOptions = {
  shareTitle?: string;
  analyticsMethod?: string;
};

export function useAffiliatePageShare(options: ShareOptions = {}) {
  const { shareTitle, analyticsMethod = 'affiliate_share' } = options;
  const { isApproved, referralCode, isLoading } = useApprovedAffiliate();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { pushToast } = useToast();

  const pageUrl = useMemo(() => {
    if (typeof window === 'undefined') return '';
    const qs = searchParams.toString();
    return `${window.location.origin}${pathname}${qs ? `?${qs}` : ''}`;
  }, [pathname, searchParams]);

  const shareUrl = useMemo(() => {
    if (!pageUrl) return '';
    if (isApproved && referralCode) return appendReferralToUrl(pageUrl, referralCode);
    return pageUrl;
  }, [isApproved, pageUrl, referralCode]);

  const canNativeShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function';

  const copyShareUrl = useCallback(async () => {
    if (!shareUrl) return false;
    try {
      await navigator.clipboard.writeText(shareUrl);
      pushToast({
        title: isApproved ? 'Đã copy link giới thiệu' : 'Đã copy link',
        variant: 'success',
        durationMs: 2000,
      });
      return true;
    } catch {
      pushToast({ title: 'Không copy được link', variant: 'error', durationMs: 2500 });
      return false;
    }
  }, [isApproved, pushToast, shareUrl]);

  const nativeShare = useCallback(async () => {
    if (!shareUrl) return;
    if (canNativeShare) {
      try {
        await navigator.share({
          title: shareTitle || (typeof document !== 'undefined' ? document.title : '188.com.vn'),
          url: shareUrl,
        });
        return;
      } catch (err) {
        if ((err as Error)?.name === 'AbortError') return;
      }
    }
    await copyShareUrl();
  }, [canNativeShare, copyShareUrl, shareTitle, shareUrl]);

  return {
    isApproved,
    isLoading,
    shareUrl,
    canNativeShare,
    copyShareUrl,
    nativeShare,
    analyticsMethod,
  };
}
