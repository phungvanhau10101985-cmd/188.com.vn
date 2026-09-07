'use client';

import { useMemo } from 'react';
import type { Product } from '@/types/api';
import { useBirthdayDiscount } from '@/lib/use-birthday-discount';
import { useFlashSale } from '@/lib/use-flash-sale';
import { useSiteSale } from '@/lib/use-site-sale';
import { productShowsClearanceOnCard } from '@/lib/warehouse-clearance';
import {
  mergeProductFlashSale,
  productForCatalogCardPricing,
  resolveProductDisplayPricing,
} from '@/lib/site-sale';

/** Giá + badge lưới: flash merge, sale trùng tháng, sinh nhật (đã trần 15%). */
export function useCatalogProductPricing(product: Product) {
  const birthdayDiscount = useBirthdayDiscount();
  const { state: siteSaleState } = useSiteSale();
  const { byId: flashById } = useFlashSale();
  const showsClearance = productShowsClearanceOnCard(product);
  const productForMainPricing = useMemo(
    () => productForCatalogCardPricing(mergeProductFlashSale(product, flashById), siteSaleState),
    [product, siteSaleState, flashById],
  );
  const pricing = resolveProductDisplayPricing(
    productForMainPricing,
    showsClearance ? false : birthdayDiscount.active,
    birthdayDiscount.percent,
  );
  const catalogListPrice =
    productForMainPricing.site_sale?.list_price ?? productForMainPricing.price ?? 0;
  return {
    pricing,
    displayPrice: pricing.displayPrice,
    birthdayDiscount,
    birthdayBadgeActive: birthdayDiscount.active && !showsClearance,
    catalogSiteSale: productForMainPricing.site_sale,
    catalogListPrice,
    showsClearance,
  };
}
