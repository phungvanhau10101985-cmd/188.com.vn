'use client';

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import type { Product } from '@/types/api';
import type { LadipageSection } from '@/lib/admin-api';
import { apiClient } from '@/lib/api-client';
import { useCart } from '@/features/cart/hooks/useCart';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useToast } from '@/components/ToastProvider';
import { ProductReviewsProvider } from '@/lib/product-reviews-context';
import ProductGallery from '@/app/products/[slug]/components/ProductGallery/ProductGallery';
import ProductInfo from '@/app/products/[slug]/components/ProductInfo/ProductInfo';
import ProductTabs from '@/components/product-detail/ProductTabs';
import ProductQASection from '@/app/products/[slug]/components/ProductQASection/ProductQASection';
import ProductReviewSection from '@/app/products/[slug]/components/ProductReviewSection/ProductReviewSection';
import AgeGenderRecommendationSection from '@/components/AgeGenderRecommendationSection';
import { trackEvent } from '@/lib/analytics';
import { trackMetaViewContentProduct } from '@/lib/meta-pixel';
import { trackTikTokViewContentProduct } from '@/lib/tiktok-pixel';
import { trackGoogleAdsViewItemProduct } from '@/lib/google-ads-gtag';
import { buildAddToCartRequestFromProduct, trackMarketingAddToCartIntent } from '@/lib/marketing-add-to-cart';
import type { GoogleAutomatedDiscountSsrPayload } from '@/lib/google-automated-discount';
import { buildAuthLoginHrefFromFullPath, getBrowserReturnLocation } from '@/lib/auth-redirect';
import { queuePendingCartAfterLogin } from '@/features/cart/pending-cart-session';
import HeroSection from './HeroSection';
import HighlightsSection from './HighlightsSection';
import MaterialSection from './MaterialSection';
import TrustCtaSection from './TrustCtaSection';
import FaqSection from './FaqSection';
import LadipageTrustStrip from './LadipageTrustStrip';
import ProductBuyModal from './ProductBuyModal';
import { buildHeroCarouselUrlsFromProduct } from '@/lib/ladipage-utils';
import type {
  FaqSectionData,
  HeroSectionData,
  HighlightsSectionData,
  MaterialSectionData,
  TrustCtaSectionData,
} from './types';

interface SingleProductLadipageViewProps {
  slug: string;
  product: Product;
  sections: LadipageSection[];
  initialGoogleDiscount?: GoogleAutomatedDiscountSsrPayload | null;
}

/**
 * Ladipage 1 SP — nội dung AI bổ sung trên PDP `/products/...`, giữ nguyên mọi chức năng sản phẩm.
 */
export default function SingleProductLadipageView({
  slug,
  product,
  sections,
  initialGoogleDiscount = null,
}: SingleProductLadipageViewProps) {
  const router = useRouter();
  const { addToCart, isLoading: cartLoading } = useCart();
  const { isAuthenticated } = useAuth();
  const { pushToast } = useToast();

  const [isFavorited, setIsFavorited] = useState(false);
  const [qaModalOpen, setQaModalOpen] = useState(false);
  const [reviewsModalOpen, setReviewsModalOpen] = useState(false);
  const [selectedColorImage, setSelectedColorImage] = useState<string | null>(null);
  const [buyModalOpen, setBuyModalOpen] = useState(false);
  const trackedRef = useRef(false);

  const source = `product:${slug}`;

  useEffect(() => {
    if (!product?.id) return;
    apiClient.trackProductView(product.id, {
      id: product.id,
      product_id: product.product_id,
      name: product.name,
      price: product.price,
      main_image: product.main_image,
      brand_name: product.brand_name,
      slug: product.slug,
    }).catch(() => {});
  }, [product?.id, product?.name, product?.price, product?.main_image, product?.brand_name, product?.slug, product?.product_id]);

  useEffect(() => {
    if (!product?.id) return;
    apiClient.isProductFavorited(product.id).then((r) => setIsFavorited(r.is_favorited)).catch(() => setIsFavorited(false));
  }, [product?.id]);

  /** ViewContent/view_item — 1 sản phẩm, đúng như trang chi tiết sản phẩm thật. */
  useLayoutEffect(() => {
    if (!product?.id || trackedRef.current) return;
    trackedRef.current = true;
    trackMetaViewContentProduct(product, { routeKey: slug });
    trackTikTokViewContentProduct(product, { routeKey: slug });
    trackGoogleAdsViewItemProduct(product);
  }, [product, slug]);

  const handleAddToCart = async (p: Product, quantity: number, selectedSize?: string, selectedColor?: string) => {
    const payload = buildAddToCartRequestFromProduct(p, quantity, selectedSize, selectedColor);
    trackMarketingAddToCartIntent(payload);
    if (!isAuthenticated) {
      queuePendingCartAfterLogin(payload);
      pushToast({
        title: 'Đăng nhập để thêm giỏ',
        description: 'Sau đăng nhập bạn sẽ được chuyển tới giỏ hàng với sản phẩm đã chọn.',
        variant: 'info',
        durationMs: 3200,
      });
      router.push(buildAuthLoginHrefFromFullPath('/cart'));
      trackEvent('add_to_cart_click', { product_id: p.id, quantity, status: 'requires_login', source });
      return;
    }
    try {
      await addToCart(payload);
      pushToast({ title: 'Đã thêm vào giỏ hàng', variant: 'success', durationMs: 2000 });
      trackEvent('add_to_cart_click', { product_id: p.id, quantity, source });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      pushToast({ title: 'Không thể thêm vào giỏ hàng', description: message, variant: 'error', durationMs: 3000 });
    }
  };

  const handleBuyNow = async (p: Product, quantity: number, selectedSize?: string, selectedColor?: string) => {
    const payload = buildAddToCartRequestFromProduct(p, quantity, selectedSize, selectedColor);
    trackMarketingAddToCartIntent(payload);
    if (!isAuthenticated) {
      queuePendingCartAfterLogin(payload);
      pushToast({
        title: 'Đăng nhập để mua hàng',
        description: 'Sau đăng nhập bạn sẽ được chuyển tới giỏ hàng với sản phẩm đã chọn.',
        variant: 'info',
        durationMs: 3200,
      });
      router.push(buildAuthLoginHrefFromFullPath('/cart'));
      trackEvent('buy_now', { product_id: p.id, quantity, status: 'requires_login', source });
      return;
    }
    try {
      await addToCart(payload, { skipAddedPopup: true });
      trackEvent('buy_now', { product_id: p.id, quantity, source });
      router.push('/cart');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      pushToast({ title: 'Không thể mua hàng', description: message, variant: 'error', durationMs: 3000 });
    }
  };

  const handleToggleFavorite = async (p: Product) => {
    try {
      if (isFavorited) {
        await apiClient.removeFromFavorites(p.id);
        setIsFavorited(false);
        trackEvent('favorite_remove', { product_id: p.id, source });
        pushToast({ title: 'Đã bỏ yêu thích', variant: 'success', durationMs: 2000 });
      } else {
        await apiClient.addToFavorites(p.id, {
          id: p.id,
          product_id: p.product_id,
          name: p.name,
          price: p.price,
          main_image: p.main_image,
          brand_name: p.brand_name,
          slug: p.slug,
        });
        setIsFavorited(true);
        trackEvent('favorite_add', { product_id: p.id, source });
        pushToast({ title: 'Đã thêm vào yêu thích', variant: 'success', durationMs: 2000 });
      }
    } catch (err: unknown) {
      if (err instanceof Error && (err.message.includes('Authentication') || err.message.includes('401'))) {
        pushToast({ title: 'Vui lòng đăng nhập lại', variant: 'info', durationMs: 2500 });
        router.push(buildAuthLoginHrefFromFullPath(getBrowserReturnLocation()));
      } else {
        pushToast({
          title: 'Không thể cập nhật yêu thích',
          description: err instanceof Error ? err.message : 'Vui lòng thử lại',
          variant: 'error',
          durationMs: 3000,
        });
      }
    }
  };

  const heroSection = sections.find((s) => s.section_type === 'hero');
  const heroData = (heroSection?.data as HeroSectionData | undefined) ?? null;
  const heroCarouselImages = useMemo(() => {
    if (!heroSection || !heroData) return [];
    return buildHeroCarouselUrlsFromProduct(product, heroData.image_url);
  }, [heroSection, heroData, product]);
  const highlightsSection = sections.find((s) => s.section_type === 'highlights');
  const materialSection = sections.find((s) => s.section_type === 'material');
  const trustCtaSection = sections.find((s) => s.section_type === 'trust_cta');
  const faqSection = sections.find((s) => s.section_type === 'faq');

  const openBuyModal = () => setBuyModalOpen(true);

  /** Hero copy chỉ hiện khi khác tên SP — tránh trùng h1 trong ProductInfo. */
  const mobileHeroBlurb = useMemo(() => {
    const norm = (s: string) =>
      s
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9\s]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
    const productTitle = (product.name || '').trim();
    const headline = (heroData?.headline || '').trim();
    const sub = (heroData?.subheadline || '').trim();
    const nProduct = norm(productTitle);
    const nHeadline = norm(headline);
    const nSub = norm(sub);
    const overlaps = (a: string, b: string) =>
      !!a && !!b && (a === b || a.includes(b) || b.includes(a));

    const showHeadline = !!headline && !overlaps(nHeadline, nProduct);
    const showSub =
      !!sub &&
      !overlaps(nSub, nProduct) &&
      (!showHeadline || !overlaps(nSub, nHeadline));

    return { showHeadline, headline, showSub, sub };
  }, [heroData?.headline, heroData?.subheadline, product.name]);

  const renderProductInfo = (opts?: { enableMobileStickyBar?: boolean; compactMobile?: boolean }) => (
    <ProductInfo
      product={product}
      viewingImageUrl={selectedColorImage}
      onAddToCart={handleAddToCart}
      onToggleFavorite={handleToggleFavorite}
      onBuyNow={handleBuyNow}
      onOpenQA={() => setQaModalOpen(true)}
      onOpenReviews={() => setReviewsModalOpen(true)}
      isCartLoading={cartLoading}
      isFavorited={isFavorited}
      onColorImageChange={setSelectedColorImage}
      initialGoogleDiscount={initialGoogleDiscount}
      enableMobileStickyBar={opts?.enableMobileStickyBar}
      compactMobile={opts?.compactMobile}
    />
  );

  const renderLadipageSections = () => (
    <>
      {highlightsSection && <HighlightsSection data={highlightsSection.data as HighlightsSectionData} />}
      {materialSection && <MaterialSection data={materialSection.data as MaterialSectionData} />}
      <div className="border-t border-gray-100 pt-2">
        <ProductTabs product={product} />
      </div>
      {trustCtaSection && (
        <TrustCtaSection data={trustCtaSection.data as TrustCtaSectionData} onCtaClick={openBuyModal} />
      )}
      {faqSection && <FaqSection data={faqSection.data as FaqSectionData} />}
      <AgeGenderRecommendationSection excludeProductId={product.id} className="mt-6" />
    </>
  );

  return (
    <ProductReviewsProvider productId={product.id}>
      {/* Mobile: gallery gọn + badge/blurb (không trùng tên SP) + buy-box */}
      <div className="md:hidden overflow-x-hidden bg-white pb-28">
        <ProductGallery
          layout="bleed"
          product={product}
          selectedImageUrl={selectedColorImage}
          onSelectImage={setSelectedColorImage}
        />

        {/* Badge + blurb: cùng cỡ/đậm với tên SP (text-base font-bold), nét mảnh */}
        <div className="px-4 pt-2.5 pb-1">
          <p className="inline-flex items-center gap-1.5 rounded-full border border-orange-200 bg-orange-50/80 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-orange-700">
            <span className="h-1.5 w-1.5 rounded-full bg-orange-500" aria-hidden />
            Gợi ý dành cho bạn
          </p>
          {mobileHeroBlurb.showHeadline ? (
            <p className="mt-2 text-base font-bold leading-snug tracking-tight text-orange-800">
              {mobileHeroBlurb.headline}
            </p>
          ) : null}
          {mobileHeroBlurb.showSub ? (
            <p className="mt-1 text-base font-bold leading-snug tracking-tight text-gray-600">
              {mobileHeroBlurb.sub}
            </p>
          ) : null}
        </div>

        <div id="ladipage-buy-box" className="scroll-mt-4 px-4 pt-1.5">
          {renderProductInfo({ enableMobileStickyBar: true, compactMobile: true })}
        </div>

        <div className="px-4 pt-2">{renderLadipageSections()}</div>
      </div>

      {/* Desktop: giữ hero marketing + gallery cạnh thông tin mua */}
      <div className="mx-auto hidden max-w-6xl px-4 pb-8 md:block">
        {heroSection && heroData && (
          <HeroSection
            data={heroData}
            carouselImages={heroCarouselImages}
            ctaSlot={
              <button
                type="button"
                onClick={openBuyModal}
                className="inline-flex items-center justify-center rounded-full bg-orange-600 px-7 py-3.5 text-sm font-bold text-white shadow-lg shadow-orange-600/25 transition hover:-translate-y-0.5 hover:bg-orange-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-600"
              >
                Mua ngay
                <span aria-hidden="true" className="ml-2 text-base leading-none">
                  →
                </span>
              </button>
            }
          />
        )}
        <LadipageTrustStrip />

        <div className="scroll-mt-6 grid grid-cols-1 gap-6 py-6 lg:grid-cols-[1fr_1fr]">
          <div className="self-start">
            <ProductGallery
              product={product}
              selectedImageUrl={selectedColorImage}
              onSelectImage={setSelectedColorImage}
            />
          </div>
          {renderProductInfo()}
        </div>

        {renderLadipageSections()}
      </div>

      <ProductBuyModal
        product={product}
        isOpen={buyModalOpen}
        onClose={() => setBuyModalOpen(false)}
        source={source}
      />

      <ProductQASection
        product={product}
        modalOnly
        modalOpen={qaModalOpen}
        onModalClose={() => setQaModalOpen(false)}
        onModalOpen={() => setQaModalOpen(true)}
      />
      <ProductReviewSection
        product={product}
        modalOnly
        modalOpen={reviewsModalOpen}
        onModalClose={() => setReviewsModalOpen(false)}
        onModalOpen={() => setReviewsModalOpen(true)}
      />
    </ProductReviewsProvider>
  );
}
