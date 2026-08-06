'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import type { Product } from '@/types/api';
import type { LadipageSection } from '@/lib/admin-api';
import { trackMetaViewContentProducts } from '@/lib/meta-pixel';
import { trackTikTokViewContentProducts } from '@/lib/tiktok-pixel';
import { trackGoogleAdsViewItemList } from '@/lib/google-ads-gtag';
import HeroSection from './HeroSection';
import HighlightsSection from './HighlightsSection';
import MaterialSection from './MaterialSection';
import TrustCtaSection from './TrustCtaSection';
import FaqSection from './FaqSection';
import ProductsGridSection from './ProductsGridSection';
import LadipageTrustStrip from './LadipageTrustStrip';
import MobileStickyCta from './MobileStickyCta';
import ProductBuyModal from './ProductBuyModal';
import { buildHeroCarouselUrlsFromProduct } from '@/lib/ladipage-utils';
import type {
  FaqSectionData,
  HeroSectionData,
  HighlightsSectionData,
  MaterialSectionData,
  TrustCtaSectionData,
} from './types';

interface PublicLadipageViewProps {
  slug: string;
  title?: string;
  sections: LadipageSection[];
  resolvedProductIds: number[];
  /** Sản phẩm đã fetch server-side — hiển thị ngay trong HTML cho SEO. */
  initialProducts?: Product[];
}

/** Render read-only (không sửa) — dùng cho trang public `/lp/<slug>`. */
export default function PublicLadipageView({
  slug,
  title,
  sections,
  resolvedProductIds,
  initialProducts,
}: PublicLadipageViewProps) {
  const source = `ladipage:${slug}`;
  const trackedRef = useRef(false);
  const [buyModalOpen, setBuyModalOpen] = useState(false);
  const singleProduct = useMemo(() => {
    if (resolvedProductIds.length !== 1) return null;
    if (initialProducts?.length === 1) return initialProducts[0];
    return null;
  }, [resolvedProductIds.length, initialProducts]);

  const scrollToProducts = () => {
    document.getElementById('ladipage-products')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const handlePrimaryCta = () => {
    if (singleProduct) {
      setBuyModalOpen(true);
      return;
    }
    scrollToProducts();
  };

  /** ViewContent/view_item_list nhóm sản phẩm — bắn đúng 1 lần khi lưới sản phẩm tải xong. */
  const handleProductsLoaded = useCallback(
    (products: Product[]) => {
      if (trackedRef.current || products.length === 0) return;
      trackedRef.current = true;
      trackMetaViewContentProducts(products, { contentName: title });
      trackTikTokViewContentProducts(products, { contentName: title });
      trackGoogleAdsViewItemList(products, title);
    },
    [title],
  );

  return (
    <div className="mx-auto max-w-6xl px-4 pb-24 md:pb-8">
      {sections.map((section) => {
        switch (section.section_type) {
          case 'hero': {
            const heroData = section.data as HeroSectionData;
            const carouselImages = singleProduct
              ? buildHeroCarouselUrlsFromProduct(singleProduct, heroData.image_url)
              : undefined;
            return (
              <div key={section.id}>
                <HeroSection
                  data={heroData}
                  carouselImages={carouselImages}
                  ctaSlot={
                    <button
                      type="button"
                      onClick={handlePrimaryCta}
                      className="inline-flex items-center justify-center rounded-full bg-orange-600 px-7 py-3.5 text-sm font-bold text-white shadow-lg shadow-orange-600/25 transition hover:-translate-y-0.5 hover:bg-orange-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-600"
                    >
                      {singleProduct ? 'Mua ngay' : 'Khám phá sản phẩm'}
                      <span aria-hidden="true" className="ml-2 text-base leading-none">→</span>
                    </button>
                  }
                />
                <LadipageTrustStrip />
              </div>
            );
          }
          case 'highlights':
            return <HighlightsSection key={section.id} data={section.data as HighlightsSectionData} />;
          case 'material':
            return <MaterialSection key={section.id} data={section.data as MaterialSectionData} />;
          case 'products_grid':
            return (
              <ProductsGridSection
                key={section.id}
                productIds={resolvedProductIds}
                initialProducts={initialProducts}
                source={source}
                onProductsLoaded={handleProductsLoaded}
              />
            );
          case 'trust_cta':
            return (
              <TrustCtaSection
                key={section.id}
                data={section.data as TrustCtaSectionData}
                onCtaClick={handlePrimaryCta}
              />
            );
          case 'faq':
            return <FaqSection key={section.id} data={section.data as FaqSectionData} />;
          default:
            return null;
        }
      })}
      <MobileStickyCta
        label={singleProduct ? 'Mua ngay' : 'Xem sản phẩm'}
        onClick={handlePrimaryCta}
      />
      {singleProduct ? (
        <ProductBuyModal
          product={singleProduct}
          isOpen={buyModalOpen}
          onClose={() => setBuyModalOpen(false)}
          source={source}
        />
      ) : null}
    </div>
  );
}
