'use client';

import { useEffect, useRef } from 'react';
import type { Product } from '@/types/api';
import { trackMetaViewContentProduct, trackMetaViewContentProducts } from '@/lib/meta-pixel';
import { trackTikTokViewContentProduct, trackTikTokViewContentProducts } from '@/lib/tiktok-pixel';
import {
  peekGoogleAdsConversionsFingerprint,
  trackGoogleAdsViewItemList,
  trackGoogleAdsViewItemProduct,
} from '@/lib/google-ads-gtag';
import { useProductMarketingView } from '@/lib/use-product-marketing-view';

/** Số SP đại diện khi vào `/lp` — đủ tín hiệu danh mục, không loãng cả lưới. */
export const LADIPAGE_LANDING_SEED_LIMIT = 2;

/**
 * Vào `/lp` danh mục: ViewContent nhóm **top N** (bán chạy) + tên landing.
 * Biết khách quan tâm danh mục / nhóm SP nổi bật — không gắn hết 12–60 id.
 */
export function useLadipageLandingSeedView(
  products: Product[] | null | undefined,
  listName?: string,
): void {
  const trackedRef = useRef(false);
  const adsConvCfgFp = peekGoogleAdsConversionsFingerprint();

  useEffect(() => {
    if (!products?.length) return;
    const seed = products.slice(0, LADIPAGE_LANDING_SEED_LIMIT);
    if (seed.length < 1) return;

    if (trackedRef.current) {
      if (seed.length >= 2) {
        trackGoogleAdsViewItemList(seed, listName);
      } else {
        trackGoogleAdsViewItemProduct(seed[0]!);
      }
      return;
    }
    trackedRef.current = true;

    if (seed.length === 1) {
      trackMetaViewContentProduct(seed[0]!, { routeKey: `lp-seed:${listName ?? ''}` });
      trackTikTokViewContentProduct(seed[0]!, { routeKey: `lp-seed:${listName ?? ''}` });
      trackGoogleAdsViewItemProduct(seed[0]!);
      return;
    }

    trackMetaViewContentProducts(seed, { contentName: listName });
    trackTikTokViewContentProducts(seed, { contentName: listName });
    trackGoogleAdsViewItemList(seed, listName);
  }, [products, listName, adsConvCfgFp]);
}

/** Mở modal mua = quan tâm rõ 1 SP. */
export function useLadipageProductInterestView(
  product: Product | null | undefined,
  active: boolean,
  routeKey: string,
): void {
  useProductMarketingView(active ? product : null, routeKey);
}
