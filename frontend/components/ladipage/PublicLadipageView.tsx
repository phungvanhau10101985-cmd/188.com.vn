'use client';

import { useMemo, useState } from 'react';
import type { Product } from '@/types/api';
import type { LadipageSection } from '@/lib/admin-api';
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

/**
 * Render read-only — trang public `/lp/<slug>` (danh mục / nhiều SP).
 * Remarketing: seed top 2 lúc vào trang + ViewContent 1 SP khi mở modal / vào PDP.
 */
export default function PublicLadipageView({
  slug,
  sections,
  resolvedProductIds,
  initialProducts,
}: PublicLadipageViewProps) {
  const source = `ladipage:${slug}`;
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
                      <span aria-hidden="true" className="ml-2 text-base leading-none">
                        →
                      </span>
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
