'use client';

import { useEffect } from 'react';
import type { Product } from '@/types/api';
import { trackMetaViewContentProduct } from '@/lib/meta-pixel';
import { trackTikTokViewContentProduct } from '@/lib/tiktok-pixel';
import {
  peekGoogleAdsConversionsFingerprint,
  trackGoogleAdsViewItemProduct,
} from '@/lib/google-ads-gtag';

/**
 * ViewContent / view_item cho 1 sản phẩm (PDP thường + ladipage 1 SP trên `/products/...`).
 *
 * Dùng useEffect (không useLayoutEffect): bắn sau hydrate, khi fbq/ttq/gtag đã load —
 * tránh ViewContent vào stub queue rồi mất (Pixel Helper chỉ còn PageView).
 */
export function useProductMarketingView(
  product: Product | null | undefined,
  routeKey: string,
): void {
  const adsConvCfgFp = peekGoogleAdsConversionsFingerprint();
  const productKey = product?.id != null ? String(product.id) : '';

  useEffect(() => {
    if (!product?.id) return;
    trackMetaViewContentProduct(product, { routeKey });
    trackTikTokViewContentProduct(product, { routeKey });
  }, [routeKey, productKey, product]);

  useEffect(() => {
    if (!product?.id) return;
    trackGoogleAdsViewItemProduct(product);
  }, [productKey, product, adsConvCfgFp]);
}
