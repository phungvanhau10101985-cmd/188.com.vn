'use client';

import { useEffect, useRef } from 'react';
import type { Product } from '@/types/api';
import { trackMetaViewContentProducts } from '@/lib/meta-pixel';
import { trackTikTokViewContentProducts } from '@/lib/tiktok-pixel';
import {
  peekGoogleAdsConversionsFingerprint,
  trackGoogleAdsViewItemList,
} from '@/lib/google-ads-gtag';

/**
 * Tracking nhóm cho Ladipage danh mục / nhiều SP (`/lp/...`).
 * Meta ViewContent (product_group) + TikTok ViewContent + Google view_item_list.
 * Không dùng cho ladipage 1 SP (đó là PDP `/products/...`).
 */
export function useLadipageGroupMarketingView(
  products: Product[] | null | undefined,
  listName?: string,
): void {
  const trackedRef = useRef(false);
  const adsConvCfgFp = peekGoogleAdsConversionsFingerprint();

  useEffect(() => {
    if (!products?.length || products.length < 2) return;
    if (trackedRef.current) {
      /** Re-fire Google khi conversion/AW config load muộn (dedupe trong helper). */
      trackGoogleAdsViewItemList(products, listName);
      return;
    }
    trackedRef.current = true;
    trackMetaViewContentProducts(products, { contentName: listName });
    trackTikTokViewContentProducts(products, { contentName: listName });
    trackGoogleAdsViewItemList(products, listName);
  }, [products, listName, adsConvCfgFp]);
}
