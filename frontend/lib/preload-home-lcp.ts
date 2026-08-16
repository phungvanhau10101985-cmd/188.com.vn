import { preload } from 'react-dom';
import { LISTING_CARD_IMAGE, getOptimizedImage } from '@/lib/image-utils';
import type { HeroCategoryTilesResponse, ProductListResponse } from '@/types/api';

/** Gọi từ server page — preload ảnh LCP tiềm năng, không đổi UI. */
export function preloadHomeLcpImages(
  initialPlainHome: ProductListResponse | null,
  initialHeroCategories: HeroCategoryTilesResponse | null
): void {
  const heroTile = initialHeroCategories?.tiles?.find(
    (t) => (t.level === 2 || t.level === 3) && t.image_url
  );
  const firstProduct = initialPlainHome?.products?.[0];

  const heroHref = heroTile?.image_url
    ? getOptimizedImage(heroTile.image_url, { ...LISTING_CARD_IMAGE })
    : null;
  const productHref = firstProduct?.main_image
    ? getOptimizedImage(firstProduct.main_image, { ...LISTING_CARD_IMAGE })
    : null;

  const href = heroHref ?? productHref;
  if (!href || href.startsWith('data:')) return;

  preload(href, { as: 'image', fetchPriority: 'high' });
}
