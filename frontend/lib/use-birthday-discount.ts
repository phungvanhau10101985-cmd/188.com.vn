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
      cachedBackendState = birthdayDiscountStateFromBackend(data);
      return cachedBackendState;
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

  useEffect(() => {
    if (!isAuthenticated) {
      setBackendState(null);
      return;
    }
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
      });
    return () => {
      active = false;
    };
  }, [isAuthenticated, user?.email, user?.id]);

  return backendState ?? localState;
}
