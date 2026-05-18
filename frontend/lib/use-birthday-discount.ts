'use client';

import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { apiClient } from '@/lib/api-client';
import {
  birthdayDiscountStateFromBackend,
  getBirthdayDiscountState,
  type BirthdayDiscountState,
} from '@/lib/birthday-discount';

let cachedBackendState: BirthdayDiscountState | null | undefined;
let inflightBackendState: Promise<BirthdayDiscountState | null> | null = null;
let cachedIdentityKey = '';

function loadBackendBirthdayPromoState(): Promise<BirthdayDiscountState | null> {
  if (cachedBackendState !== undefined) return Promise.resolve(cachedBackendState);
  if (inflightBackendState) return inflightBackendState;
  inflightBackendState = apiClient
    .getMyBirthdayPromoStatus()
    .then((data) => {
      const mapped = birthdayDiscountStateFromBackend(data);
      cachedBackendState = mapped;
      return mapped;
    })
    .catch(() => {
      cachedBackendState = null;
      return null;
    })
    .finally(() => {
      inflightBackendState = null;
    });
  return inflightBackendState;
}

export function useBirthdayDiscount(dateOfBirth?: string | null): BirthdayDiscountState {
  const { isAuthenticated, user } = useAuth();
  const localState = useMemo(
    () => getBirthdayDiscountState(dateOfBirth ?? user?.date_of_birth ?? null),
    [dateOfBirth, user?.date_of_birth]
  );
  const [backendState, setBackendState] = useState<BirthdayDiscountState | null>(null);
  const [backendResolved, setBackendResolved] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) {
      setBackendState(null);
      setBackendResolved(false);
      return;
    }
    setBackendResolved(false);
    const identityKey = `${user?.id ?? ''}:${user?.email ?? ''}`;
    if (identityKey !== cachedIdentityKey) {
      cachedIdentityKey = identityKey;
      cachedBackendState = undefined;
      inflightBackendState = null;
    }
    let active = true;
    loadBackendBirthdayPromoState()
      .then((data) => {
        if (!active) return;
        setBackendState(data);
        setBackendResolved(true);
      });
    return () => {
      active = false;
    };
  }, [isAuthenticated, user?.email, user?.id]);

  if (!isAuthenticated) {
    return localState;
  }
  if (!backendResolved) {
    return {
      active: false,
      percent: 0,
      daysUntil: null,
      nextBirthdayLabel: null,
    };
  }
  return backendState ?? localState;
}
