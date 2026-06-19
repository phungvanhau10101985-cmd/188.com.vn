'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  capturePv2FromLocation,
  extractPv2FromSearch,
  getGoogleAutomatedDiscountForOffer,
  touchGoogleAutomatedDiscountSession,
  type GoogleAutomatedDiscountRecord,
} from '@/lib/google-automated-discount';

/** Giá chiết khấu Google cho một offer_id (product_id feed GMC). */
export function useGoogleAutomatedDiscount(offerId: string | null | undefined) {
  const [record, setRecord] = useState<GoogleAutomatedDiscountRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const id = String(offerId || '').trim();
    if (!id) {
      setRecord(null);
      return;
    }

    const cached = getGoogleAutomatedDiscountForOffer(id);
    if (cached) {
      touchGoogleAutomatedDiscountSession(id);
      setRecord(getGoogleAutomatedDiscountForOffer(id));
      return;
    }

    if (typeof window === 'undefined') return;
    const token = extractPv2FromSearch(window.location.search);
    if (!token) {
      setRecord(null);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const saved = await capturePv2FromLocation(window.location.search, id);
      setRecord(saved);
    } catch (err) {
      setRecord(null);
      setError(err instanceof Error ? err.message : 'Không áp dụng được giá Google.');
    } finally {
      setLoading(false);
    }
  }, [offerId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const id = String(offerId || '').trim();
    if (!id || !record) return;
    touchGoogleAutomatedDiscountSession(id);
  }, [offerId, record]);

  return { record, loading, error, refresh };
}
