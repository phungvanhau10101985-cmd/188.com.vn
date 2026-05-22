'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { apiClient } from '@/lib/api-client';

type ApprovedAffiliateSnapshot = {
  referralCode: string | null;
  isApproved: boolean;
  isLoading: boolean;
};

const cache = new Map<number, { referralCode: string; isApproved: boolean }>();

export function useApprovedAffiliate(): ApprovedAffiliateSnapshot {
  const { isAuthenticated, user, isLoading: authLoading } = useAuth();
  const [state, setState] = useState<ApprovedAffiliateSnapshot>({
    referralCode: null,
    isApproved: false,
    isLoading: true,
  });

  useEffect(() => {
    if (authLoading) return;

    if (!isAuthenticated || !user?.id) {
      setState({ referralCode: null, isApproved: false, isLoading: false });
      return;
    }

    const cached = cache.get(user.id);
    if (cached) {
      setState({
        referralCode: cached.isApproved ? cached.referralCode : null,
        isApproved: cached.isApproved,
        isLoading: false,
      });
      return;
    }

    let cancelled = false;
    apiClient
      .getAffiliateMe()
      .then((me) => {
        if (cancelled) return;
        const isApproved = me.affiliate_status === 'approved';
        const referralCode = (me.referral_code || '').trim().toUpperCase();
        cache.set(user.id, { referralCode, isApproved });
        setState({
          referralCode: isApproved && referralCode ? referralCode : null,
          isApproved,
          isLoading: false,
        });
      })
      .catch(() => {
        if (!cancelled) {
          setState({ referralCode: null, isApproved: false, isLoading: false });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [authLoading, isAuthenticated, user?.id]);

  return state;
}
