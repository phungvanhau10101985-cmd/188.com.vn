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

  const copyShareUrl = useCallback(async () => {
    if (!shareUrl) return false;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(shareUrl);
      } else {
        throw new Error('clipboard-unavailable');
      }
      pushToast({
        title: isApproved ? 'Đã copy link giới thiệu' : 'Đã copy link',
        variant: 'success',
        durationMs: 2000,
      });
      return true;
    } catch {
      try {
        const ta = document.createElement('textarea');
        ta.value = shareUrl;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        const ok = document.execCommand('copy');
        document.body.removeChild(ta);
        if (!ok) throw new Error('execCommand-copy-failed');
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
    }
  }, [isApproved, pushToast, shareUrl]);

  return {
    isApproved,
    isLoading,
    shareUrl,
    copyShareUrl,
    analyticsMethod,
  };
}
