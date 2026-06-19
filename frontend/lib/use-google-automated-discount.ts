'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  capturePv2FromLocation,
  extractPv2FromSearch,
  getGoogleAutomatedDiscountForProduct,
  GOOGLE_AUTOMATED_DISCOUNT_UPDATED_EVENT,
  touchGoogleAutomatedDiscountSession,
  type GoogleAutomatedDiscountRecord,
} from '@/lib/google-automated-discount';

/** Giá chiết khấu Google cho một offer_id (product_id feed GMC). */
export function useGoogleAutomatedDiscount(
  offerId: string | null | undefined,
  product?: { product_id?: string | null; code?: string | null },
) {
  const [record, setRecord] = useState<GoogleAutomatedDiscountRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const syncFromStore = useCallback(() => {
    const id = String(offerId || '').trim();
    if (!id && !product?.product_id) {
      setRecord(null);
      return;
    }
    const cached = product
      ? getGoogleAutomatedDiscountForProduct(product)
      : getGoogleAutomatedDiscountForProduct({ product_id: id });
    if (cached) {
      touchGoogleAutomatedDiscountSession(cached.offerId);
      setRecord(getGoogleAutomatedDiscountForProduct(product ?? { product_id: id }));
      return;
    }
    setRecord(null);
  }, [offerId, product]);

  const refresh = useCallback(async () => {
    const id = String(offerId || product?.product_id || '').trim();
    syncFromStore();
    const cached = product
      ? getGoogleAutomatedDiscountForProduct(product)
      : id
        ? getGoogleAutomatedDiscountForProduct({ product_id: id })
        : null;
    if (cached) {
      setRecord(cached);
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
      // Xác thực JWT trước (không ép khớp offer) — Capture global cũng gọi song song.
      const saved = await capturePv2FromLocation(window.location.search);
      if (!saved) {
        setRecord(null);
        return;
      }
      const matched = product
        ? getGoogleAutomatedDiscountForProduct(product)
        : getGoogleAutomatedDiscountForProduct({ product_id: id });
      if (matched) {
        setRecord(matched);
      } else {
        setRecord(null);
        setError('Giá chiết khấu không áp dụng cho sản phẩm này.');
      }
    } catch (err) {
      setRecord(null);
      setError(err instanceof Error ? err.message : 'Không áp dụng được giá Google.');
    } finally {
      setLoading(false);
    }
  }, [offerId, product, syncFromStore]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onUpdated = () => {
      syncFromStore();
      void refresh();
    };
    window.addEventListener(GOOGLE_AUTOMATED_DISCOUNT_UPDATED_EVENT, onUpdated);
    return () => window.removeEventListener(GOOGLE_AUTOMATED_DISCOUNT_UPDATED_EVENT, onUpdated);
  }, [refresh, syncFromStore]);

  useEffect(() => {
    if (!record) return;
    touchGoogleAutomatedDiscountSession(record.offerId);
  }, [record]);

  return { record, loading, error, refresh };
}
