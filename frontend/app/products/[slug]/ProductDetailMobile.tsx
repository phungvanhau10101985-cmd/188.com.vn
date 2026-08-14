'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import type { Product } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { formatPrice } from '@/lib/utils';
import { mergeProductGalleryPhotoUrls } from '@/lib/product-gallery-merge';
import { ProductFillImage, GalleryThumbImage } from '@/components/product-detail/HideOnImageError';
import MobileProductMediaCarousel, {
  MobileProductMediaSlide,
  type MobileProductMediaCarouselHandle,
} from '@/components/product-detail/MobileProductMediaCarousel';
import { reportUnreachableProductMedia } from '@/lib/report-broken-product-media';
import { getOptimizedImage } from '@/lib/image-utils';
import { hasVideoLink, parseVideoLink, buildYoutubeEmbedSrc } from '@/lib/video-utils';
import AgeGenderRecommendationSection from '@/components/AgeGenderRecommendationSection';
import SectionErrorBoundary from '@/components/ui/SectionErrorBoundary';
import ProductTabs from '@/components/product-detail/ProductTabs';
import ProductVariantModal from './components/ProductVariantModal/ProductVariantModal';
import ProductQAReviewCards from './components/ProductQAReviewCards/ProductQAReviewCards';
import ProductQASection from './components/ProductQASection/ProductQASection';
import ProductReviewSection from './components/ProductReviewSection/ProductReviewSection';
import BirthdayPromoBanner from '@/components/BirthdayPromoBanner';
import BirthdaySavingsCard from '@/components/BirthdaySavingsCard';
import ProductPromoPriceBlock from '@/components/product-detail/ProductPromoPriceBlock';
import { mergeProductSiteSaleFromCalendar, resolveProductDisplayPricing } from '@/lib/site-sale';
import { applyGoogleAutomatedDiscountToPricing } from '@/lib/google-automated-discount';
import type { GoogleAutomatedDiscountSsrPayload } from '@/lib/google-automated-discount';
import { useGoogleAutomatedDiscount } from '@/lib/use-google-automated-discount';
import { useSiteSale } from '@/lib/use-site-sale';
import { useBirthdayDiscount } from '@/lib/use-birthday-discount';
import AffiliateShareBar, { ProductShareIconButton } from '@/components/affiliate/AffiliateShareBar';
import { useAffiliatePageShare } from '@/lib/use-affiliate-page-share';
import { trackEvent } from '@/lib/analytics';
import NanoAiLauncherGatewaySync from '@/components/NanoAiLauncherGatewaySync';
import {
  buildNanoAiGatewayPayloadFrom188Product,
  NANO_AI_CTX_SOURCE_PRODUCT_PDP,
} from '@/lib/nanoai-hosted-chat';
import { useNanoAiMessaging } from '@/lib/use-nanoai-messaging';
import WarehouseClearanceBlock from '@/components/product-detail/WarehouseClearanceBlock';
import {
  canOrderAnyVariant,
  canOrderSourceProduct,
  warehouseVariantsInStock,
} from '@/lib/warehouse-clearance';

function formatLikeCount(n: unknown): string {
  const v = Math.max(0, Math.floor(Number(n)) || 0);
  return new Intl.NumberFormat('vi-VN').format(v);
}

interface ProductDetailMobileProps {
  product: Product;
  isFavorited: boolean;
  isCartLoading: boolean;
  onAddToCart: (p: Product, qty: number, size?: string, color?: string) => void;
  onBuyNow: (p: Product, qty: number, size?: string, color?: string) => void;
  onToggleFavorite: (p: Product) => void;
  initialGoogleDiscount?: GoogleAutomatedDiscountSsrPayload | null;
}

export default function ProductDetailMobile({
  product,
  isFavorited,
  isCartLoading,
  onAddToCart,
  onBuyNow,
  onToggleFavorite,
  initialGoogleDiscount = null,
}: ProductDetailMobileProps) {
  const [selectedImage, setSelectedImage] = useState(0);
  const thumbStripRef = useRef<HTMLElement>(null);
  const thumbButtonRefs = useRef<Record<number, HTMLButtonElement | null>>({});
  const mediaCarouselRef = useRef<MobileProductMediaCarouselHandle>(null);
  const [variantModalOpen, setVariantModalOpen] = useState(false);
  const [qaModalOpen, setQaModalOpen] = useState(false);
  const [reviewsModalOpen, setReviewsModalOpen] = useState(false);
  /** Tồn ảo theo biến thể (key = productId_variantKey); lưu ở parent để sau khi mua tồn = 0 vẫn giữ, mở lại không mua thêm được. */
  const [displayStockByVariant, setDisplayStockByVariant] = useState<Record<string, number>>({});
  const { isAuthenticated } = useAuth();
  const { copyShareUrl, isApproved: isAffiliateApproved } = useAffiliatePageShare({ shareTitle: product.name });
  const { openTryOnForProduct } = useNanoAiMessaging();
  const [loyaltyStatus, setLoyaltyStatus] = useState<any>(null);

  const quantity = 1;
  const sourceAvailable = canOrderSourceProduct(product);
  const warehouseInStock = warehouseVariantsInStock(product);
  const available = sourceAvailable;
  const canShowStickyBuy = canOrderAnyVariant(product);

  useEffect(() => {
    if (!isAuthenticated) return;
    let idleHandle: number | undefined;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    const load = () => {
      apiClient.getMyLoyaltyStatus().then(setLoyaltyStatus).catch(() => {});
    };
    if (typeof window !== 'undefined' && 'requestIdleCallback' in window) {
      idleHandle = window.requestIdleCallback(load, { timeout: 3500 });
    } else {
      timeoutId = setTimeout(load, 0);
    }
    return () => {
      if (idleHandle !== undefined && typeof window !== 'undefined' && 'cancelIdleCallback' in window) {
        window.cancelIdleCallback(idleHandle);
      }
      if (timeoutId !== undefined) clearTimeout(timeoutId);
    };
  }, [isAuthenticated]);

  const birthdayDiscount = useBirthdayDiscount();
  const { state: siteSaleState } = useSiteSale();
  const productForPricing = useMemo(
    () => mergeProductSiteSaleFromCalendar(product, siteSaleState),
    [product, siteSaleState],
  );
  const { record: googleDiscount, error: googleDiscountError } = useGoogleAutomatedDiscount(
    product.product_id,
    product,
    initialGoogleDiscount,
  );
  const pricingBase = useMemo(
    () =>
      resolveProductDisplayPricing(
        productForPricing,
        birthdayDiscount.active,
        birthdayDiscount.percent,
      ),
    [productForPricing, birthdayDiscount.active, birthdayDiscount.percent],
  );
  const pricing = useMemo(
    () =>
      applyGoogleAutomatedDiscountToPricing(
        product.product_id,
        pricingBase,
        product,
        googleDiscount,
      ),
    [product, pricingBase, googleDiscount],
  );
  const isClearancePdp = product.is_warehouse_clearance === true;
  const displayPrice = pricing.displayPrice;
  const birthdaySavingsAmount = pricing.birthdaySavingsAmount;
  const loyaltyDiscountPercent = loyaltyStatus?.current_tier?.discount_percent || 0;
  const loyaltyDiscountAmount = (displayPrice * loyaltyDiscountPercent) / 100;
  const loyaltyTierName = loyaltyStatus?.current_tier?.name || 'L0';

  const openVariantModal = () => setVariantModalOpen(true);

  const hasVideo = hasVideoLink(product.video_link);
  const parsedVideo = parseVideoLink(product.video_link);

  const galleryPhotoUrls = useMemo(() => mergeProductGalleryPhotoUrls(product), [product]);
  const [brokenPhoto, setBrokenPhoto] = useState<Record<string, true>>({});
  const markBrokenPhoto = useCallback(
    (rawUrl: string) => {
      const u = typeof rawUrl === 'string' ? rawUrl.trim() : '';
      if (!u) return;
      reportUnreachableProductMedia(product.id, u);
      setBrokenPhoto((prev) => (prev[u] ? prev : { ...prev, [u]: true }));
    },
    [product.id],
  );
  const visiblePhotoUrls = useMemo(
    () => galleryPhotoUrls.filter((u) => !brokenPhoto[u]),
    [galleryPhotoUrls, brokenPhoto],
  );

  // Hero order: ảnh đầu → video → ảnh còn lại. Không có ảnh thì video ở index 0.
  const videoIndex = hasVideo ? (visiblePhotoUrls.length > 0 ? 1 : 0) : -1;
  const mediaCount = hasVideo ? 1 + visiblePhotoUrls.length : visiblePhotoUrls.length;
  const isShowingVideo = hasVideo && selectedImage === videoIndex;

  const photoIndexFromMediaIndex = useCallback(
    (mediaIndex: number): number | null => {
      if (!hasVideo) return mediaIndex;
      if (mediaIndex === videoIndex) return null;
      if (visiblePhotoUrls.length === 0) return null;
      return mediaIndex < videoIndex ? mediaIndex : mediaIndex - 1;
    },
    [hasVideo, videoIndex, visiblePhotoUrls.length],
  );

  const mediaIndexFromPhotoIndex = useCallback(
    (photoIndex: number): number => {
      if (!hasVideo || visiblePhotoUrls.length === 0) return photoIndex;
      return photoIndex === 0 ? 0 : photoIndex + 1;
    },
    [hasVideo, visiblePhotoUrls.length],
  );

  useEffect(() => {
    setSelectedImage((prev) => {
      if (mediaCount <= 0) return 0;
      if (prev >= mediaCount) return mediaCount - 1;
      return prev;
    });
  }, [mediaCount]);

  const selectMediaIndex = useCallback((index: number) => {
    setSelectedImage(index);
    mediaCarouselRef.current?.scrollToIndex(index);
  }, []);

  useEffect(() => {
    const btn = thumbButtonRefs.current[selectedImage];
    const strip = thumbStripRef.current;
    if (!btn || !strip) return;
    const stripRect = strip.getBoundingClientRect();
    const btnRect = btn.getBoundingClientRect();
    const left = btn.offsetLeft - strip.offsetLeft - (stripRect.width - btnRect.width) / 2;
    strip.scrollTo({ left: Math.max(0, left), behavior: 'auto' });
  }, [selectedImage, visiblePhotoUrls.length, hasVideo]);

  const mainImageRaw = isShowingVideo
    ? null
    : (() => {
        const photoIdx = photoIndexFromMediaIndex(selectedImage);
        return photoIdx == null ? null : (visiblePhotoUrls[photoIdx] ?? null);
      })();
  const videoThumb = parsedVideo?.thumbUrl ?? null;
  const firstPhotoUrl = visiblePhotoUrls[0] ?? null;
  const restPhotoUrls = visiblePhotoUrls.slice(1);
  const [heroAspect, setHeroAspect] = useState<string | undefined>();

  useEffect(() => {
    setHeroAspect(undefined);
  }, [firstPhotoUrl]);

  const handleHeroNaturalSize = useCallback((width: number, height: number) => {
    if (width < 2 || height < 2) return;
    setHeroAspect((prev) => prev ?? `${width} / ${height}`);
  }, []);

  const photoFrameClass = 'relative w-full bg-gray-100';
  const videoFrameClass = 'relative w-full overflow-hidden bg-black';
  const videoFrameStyle = { aspectRatio: heroAspect ?? '3 / 4' };

  const nanoPayload = buildNanoAiGatewayPayloadFrom188Product(product, {
    imageUrl: mainImageRaw,
  });

  const handleNanoAiTryOn = useCallback(() => {
    void openTryOnForProduct(product, {
      imageUrl: mainImageRaw,
      ctxSource: NANO_AI_CTX_SOURCE_PRODUCT_PDP,
      source: 'product_detail_mobile',
    });
  }, [openTryOnForProduct, product, mainImageRaw]);

  const handleCopyLink = () => {
    void copyShareUrl().then((ok) => {
      if (ok) {
        trackEvent('share_product', {
          method: isAffiliateApproved ? 'copy_affiliate_link' : 'copy_link',
          product_id: product.id,
        });
      }
    });
  };

  const productCode = product.code || product.product_id || '';

  return (
    <div className="md:hidden min-h-screen overflow-x-hidden bg-white pb-28">
      <NanoAiLauncherGatewaySync payload={nanoPayload} />

      {/* Hero gallery: full-width theo tỉ lệ ảnh gốc, vuốt ngang */}
      <SectionErrorBoundary>
      <div className="image_list w-full overflow-x-hidden bg-gray-50">
        {mediaCount > 0 && (
          <div className="relative w-full">
            <MobileProductMediaCarousel
              ref={mediaCarouselRef}
              selectedIndex={selectedImage}
              onSelectedIndexChange={setSelectedImage}
              slideCount={mediaCount}
              renderOverlay={
                mediaCount > 1
                  ? (liveIndex) => (
                      <>
                        <div className="pointer-events-none absolute top-3 right-3 z-[1] rounded-full bg-black/55 px-2.5 py-1 text-[11px] font-medium tabular-nums text-white">
                          {liveIndex + 1}/{mediaCount}
                        </div>
                        <div className="pointer-events-none absolute bottom-3 left-0 right-0 z-[1] flex items-center justify-center gap-1.5">
                          {Array.from({ length: mediaCount }, (_, i) => (
                            <span
                              key={i}
                              className={
                                i === liveIndex
                                  ? 'h-1.5 w-4 rounded-full bg-white shadow-sm'
                                  : 'h-1.5 w-1.5 rounded-full bg-white/55'
                              }
                            />
                          ))}
                        </div>
                      </>
                    )
                  : undefined
              }
            >
              {firstPhotoUrl ? (
                <MobileProductMediaSlide key={firstPhotoUrl} className="bg-gray-100">
                  <ProductFillImage
                    src={getOptimizedImage(firstPhotoUrl, { width: 960, hideProductPng: true })}
                    alt={product.name}
                    frameClassName={photoFrameClass}
                    fit="natural"
                    priority
                    onNaturalSize={handleHeroNaturalSize}
                    onBroken={() => markBrokenPhoto(firstPhotoUrl)}
                  >
                    <div className="absolute top-2 left-2 flex items-center gap-1.5 bg-black/50 text-white text-[10px] px-2 py-1 rounded">
                      <span className="font-medium truncate max-w-[140px]">{product.brand_name || '188 com vn'}</span>
                    </div>
                    <div className="absolute bottom-2 left-2 flex gap-2">
                      <ProductShareIconButton shareTitle={product.name} />
                      <Link href="/da-xem" className="w-8 h-8 rounded-full bg-white/80 flex items-center justify-center" aria-label="Sản phẩm đã xem">
                        <svg className="w-4 h-4 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                      </Link>
                    </div>
                  </ProductFillImage>
                </MobileProductMediaSlide>
              ) : null}
              {hasVideo && parsedVideo ? (
                <MobileProductMediaSlide className="bg-gray-100">
                  <div className={videoFrameClass} style={videoFrameStyle}>
                    {parsedVideo.kind === 'youtube' ? (
                      <>
                        <iframe
                          title={`Video ${product.name}`}
                          src={buildYoutubeEmbedSrc(parsedVideo.urlOrId)}
                          className="absolute inset-0 w-full h-full"
                          loading="lazy"
                          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share; fullscreen"
                          allowFullScreen
                          referrerPolicy="strict-origin-when-cross-origin"
                        />
                        <div className="absolute top-2 left-2 flex items-center gap-1.5 bg-black/50 text-white text-[10px] px-2 py-1 rounded">
                          <span className="w-5 h-5 rounded-full bg-white/80 flex items-center justify-center text-black font-bold text-[10px]">T</span>
                          <span className="font-medium truncate max-w-[120px]">{product.brand_name || '188 com vn Thời Trang'}</span>
                        </div>
                        <div className="absolute bottom-0 left-0 right-0 bg-black text-white text-xs py-2 px-3 flex items-center justify-center gap-2">
                          <svg className="w-5 h-5 shrink-0" viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" /></svg>
                          Xem trên YouTube
                        </div>
                      </>
                    ) : (
                      <>
                        <video
                          src={parsedVideo.urlOrId}
                          controls
                          className="absolute inset-0 w-full h-full object-contain bg-black"
                          playsInline
                        />
                        <div className="absolute top-2 left-2 flex items-center gap-1.5 bg-black/50 text-white text-[10px] px-2 py-1 rounded">
                          <span className="font-medium truncate max-w-[120px]">{product.brand_name || '188 com vn'}</span>
                        </div>
                      </>
                    )}
                  </div>
                </MobileProductMediaSlide>
              ) : null}
              {restPhotoUrls.map((img) => (
                <MobileProductMediaSlide key={img} className="bg-gray-100">
                  <ProductFillImage
                    src={getOptimizedImage(img, { width: 960, hideProductPng: true })}
                    alt={product.name}
                    frameClassName={photoFrameClass}
                    fit="natural"
                    onBroken={() => markBrokenPhoto(img)}
                  >
                    <div className="absolute top-2 left-2 flex items-center gap-1.5 bg-black/50 text-white text-[10px] px-2 py-1 rounded">
                      <span className="font-medium truncate max-w-[140px]">{product.brand_name || '188 com vn'}</span>
                    </div>
                    <div className="absolute bottom-2 left-2 flex gap-2">
                      <ProductShareIconButton shareTitle={product.name} />
                      <Link href="/da-xem" className="w-8 h-8 rounded-full bg-white/80 flex items-center justify-center" aria-label="Sản phẩm đã xem">
                        <svg className="w-4 h-4 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                      </Link>
                    </div>
                  </ProductFillImage>
                </MobileProductMediaSlide>
              ))}
            </MobileProductMediaCarousel>
          </div>
        )}

        {/* Thumbnail: vuốt ngang xem toàn bộ ảnh */}
        {mediaCount > 1 && (
          <nav
            ref={thumbStripRef}
            className="product-gallery-thumb-strip flex items-center gap-2 overflow-x-auto scrollbar-hide snap-x snap-mandatory py-2 px-4"
            style={{ WebkitOverflowScrolling: 'touch' }}
            aria-label="Thư viện ảnh sản phẩm"
          >
            {firstPhotoUrl ? (
              <GalleryThumbImage
                key={firstPhotoUrl}
                src={getOptimizedImage(firstPhotoUrl, { width: 64, height: 64, hideProductPng: true })}
                selected={selectedImage === 0}
                onClick={() => selectMediaIndex(0)}
                onBroken={() => markBrokenPhoto(firstPhotoUrl)}
                buttonRef={(el) => {
                  thumbButtonRefs.current[0] = el;
                }}
              />
            ) : null}
            {hasVideo && (
              <button
                ref={(el) => {
                  thumbButtonRefs.current[videoIndex] = el;
                }}
                type="button"
                onClick={() => selectMediaIndex(videoIndex)}
                className={`relative flex-shrink-0 w-16 h-16 snap-center snap-always rounded-lg overflow-hidden border-2 ${
                  selectedImage === videoIndex ? 'border-[#ea580c]' : 'border-gray-200'
                }`}
                aria-label="Xem video"
                aria-current={selectedImage === videoIndex ? 'true' : undefined}
              >
                {videoThumb ? (
                  <Image src={videoThumb} alt="Video" width={64} height={64} className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full bg-gray-800 flex items-center justify-center" />
                )}
                <span className="absolute inset-0 flex items-center justify-center bg-black/30 rounded-lg">
                  <svg className="w-6 h-6 text-white" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
                </span>
              </button>
            )}
            {restPhotoUrls.map((img, i) => {
              const photoIndex = i + 1;
              const mediaIndex = mediaIndexFromPhotoIndex(photoIndex);
              return (
                <GalleryThumbImage
                  key={img}
                  src={getOptimizedImage(img, { width: 64, height: 64, hideProductPng: true })}
                  selected={selectedImage === mediaIndex}
                  onClick={() => selectMediaIndex(mediaIndex)}
                  onBroken={() => markBrokenPhoto(img)}
                  buttonRef={(el) => {
                    thumbButtonRefs.current[mediaIndex] = el;
                  }}
                />
              );
            })}
            <button
              type="button"
              onClick={handleCopyLink}
              className="flex-shrink-0 snap-center px-3 py-2 rounded-lg border border-gray-300 text-xs font-medium text-gray-700 hover:bg-gray-50"
            >
              {isAffiliateApproved ? 'Copy link giới thiệu' : 'Copy link'}
            </button>
          </nav>
        )}
      </div>
      </SectionErrorBoundary>

      <div className="px-4 py-3">
        <BirthdayPromoBanner
          active={birthdayDiscount.active}
          percent={birthdayDiscount.percent}
          nextBirthdayLabel={birthdayDiscount.nextBirthdayLabel}
          compact
          className="mb-3"
        />

        {/* Tiêu đề sản phẩm */}
        <h1 className="text-base font-bold text-gray-900 leading-tight mb-3 uppercase">
          {product.name}
          {isAuthenticated && loyaltyTierName !== 'L0' && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800 ml-2 align-middle">
              Hạng thành viên {loyaltyTierName}
            </span>
          )}
        </h1>

        <AffiliateShareBar shareTitle={product.name} className="mb-3" />

        {productCode && (
          <p className="text-xs text-gray-600 mb-2">
            Mã sp: <span className="copy-code-product">{productCode}</span>
          </p>
        )}

        {/* Giá + giá gốc, giảm giá, trả góp */}
        <div className="mb-3 rounded-2xl border border-orange-100 bg-orange-50/50 p-3">
          <ProductPromoPriceBlock
            displayPrice={displayPrice}
            compareUnitPrice={pricing.compareUnitPrice}
            savingsAmount={pricing.savingsAmount}
            expectedSalePrice={pricing.expectedSalePrice}
            sitePhase={googleDiscount ? null : pricing.sitePhase}
            sitePercent={googleDiscount ? 0 : pricing.sitePercent}
            siteLabel={googleDiscount ? null : pricing.siteLabel}
            countdownTo={googleDiscount ? null : pricing.countdownTo}
            birthdayActive={googleDiscount ? false : birthdayDiscount.active}
            birthdayPercent={birthdayDiscount.percent}
            clearanceHighlight={isClearancePdp}
            promoLabel={isClearancePdp ? 'Thanh lý kho' : googleDiscount ? 'Google Shopping' : null}
            activePriceLabel={googleDiscount ? 'Giá ưu đãi Google' : null}
            suppressSiteSaleBanners={!!googleDiscount}
            size="sm"
          />
          {googleDiscount ? (
            <p className="mt-2 text-xs text-emerald-800">
              Giá ưu đãi từ quảng cáo Google Shopping.
            </p>
          ) : googleDiscountError ? (
            <p className="mt-2 text-xs text-red-700">{googleDiscountError}</p>
          ) : null}
        </div>

        <BirthdaySavingsCard
          active={birthdayDiscount.active}
          percent={birthdayDiscount.percent}
          savings={birthdaySavingsAmount}
          nextBirthdayLabel={birthdayDiscount.nextBirthdayLabel}
          compact
          className="mb-3"
        />

        {/* Thống kê: Đã bán, Lượt thích, Đánh giá */}
        <div className="flex flex-wrap items-center gap-3 text-xs text-gray-600 mb-3">
          <span className="flex items-center gap-1">
            <span className="text-gray-400">🛒</span> Đã bán: <strong className="text-gray-900">{product.purchases ?? 0}</strong>
          </span>
          <span className="flex items-center gap-1">
            <span className="text-red-400">♥</span> Lượt thích: <strong className="text-gray-900">{product.likes ?? 0}</strong>
          </span>
          <span className="flex items-center gap-1">
            <span className="text-amber-400">★</span> Đánh giá: <strong className="text-gray-900">{product.rating_point?.toFixed(1) ?? '0'}/5</strong> ({(product.rating_total ?? 0)} lượt)
          </span>
        </div>

        {/* Giao hàng & Đổi trả */}
        <div className="border-t border-gray-100 pt-3 mb-3">
          <p className="text-xs text-gray-900 leading-snug">
            🚚 Giao hàng toàn quốc – Miễn phí đơn từ 500k. 🔁 Đổi trả trong 7 ngày nếu sản phẩm lỗi hoặc không đúng mô tả.{' '}
            👉 Xem chi tiết tại{' '}
            <Link href="/info/chinh-sach-giao-hang" className="text-[#ea580c] hover:underline font-medium">
              Chính sách giao hàng
            </Link>{' '}
            và{' '}
            <Link href="/info/doi-tra-hoan-tien" className="text-[#ea580c] hover:underline font-medium">
              Chính sách đổi trả
            </Link>
            .
          </p>
        </div>

        {product.source_oos && warehouseInStock.length > 0 ? (
          <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-600 mb-3">
            Hàng order nguồn tạm hết — chọn <strong>Thanh lý trong kho</strong> bên dưới.
          </div>
        ) : null}

        <WarehouseClearanceBlock
          product={product}
          onAddToCart={onAddToCart}
          onBuyNow={onBuyNow}
          isCartLoading={isCartLoading}
        />

        {/* Dịch vụ */}
        <div className="mb-3">
          <p className="text-xs text-gray-700 leading-snug">
            <strong className="text-gray-900">Dịch vụ:</strong> thanh toán khi nhận hàng, đổi size nếu không vừa, xem hàng trước khi nhận.
          </p>
        </div>

        {/* Lưu ý */}
        <div className="mb-3">
          <p className="font-semibold text-gray-900 text-xs mb-1">Lưu ý:</p>
          <ul className="list-disc list-inside text-xs text-gray-700 space-y-0.5 leading-snug">
            <li>Sản phẩm váy, áo, quần cắt may có thể chênh lệch 1 – 2 (cm).</li>
            <li>Do ánh sáng và thiết bị chụp hình, màu sắc hình ảnh và thực tế có thể có chênh lệch nhỏ.</li>
          </ul>
        </div>

        {/* Chính sách đánh giá */}
        <p className="text-xs text-gray-900 mb-4">
          Bấm để xem{' '}
          <Link href="/info/chinh-sach-danh-gia" className="text-[#ea580c] hover:underline">
            Chính sách quản lý đánh giá và quản lý chất lượng sản phẩm
          </Link>
        </p>

        {/* Đánh giá + Câu hỏi (giống desktop, đặt trên Mô tả sản phẩm) */}
        <div className="mb-4">
          <ProductQAReviewCards
            product={product}
            onOpenQA={() => setQaModalOpen(true)}
            onOpenReviews={() => setReviewsModalOpen(true)}
            layout="stack"
          />
        </div>

        {/* Mô tả & Thông tin sản phẩm (tabs như desktop) */}
        <div className="mb-4">
          <SectionErrorBoundary>
            <ProductTabs product={product} />
          </SectionErrorBoundary>
        </div>

        <ProductReviewSection product={product} modalOnly modalOpen={reviewsModalOpen} onModalClose={() => setReviewsModalOpen(false)} onModalOpen={() => setReviewsModalOpen(true)} />
        <ProductQASection product={product} modalOnly modalOpen={qaModalOpen} onModalClose={() => setQaModalOpen(false)} onModalOpen={() => setQaModalOpen(true)} />

        {/* RelatedProducts đã hiển thị sẵn trong tab "Mô tả" của ProductTabs — không lặp lại ở đây. */}
        <SectionErrorBoundary>
          <AgeGenderRecommendationSection excludeProductId={product.id} className="mt-4 border-t border-gray-100 pt-4" />
        </SectionErrorBoundary>
      </div>

      {/* Sticky bottom bar: Trang · Thử đồ · Thích | THÊM GIỎ | MUA HÀNG */}
      <div className="fixed bottom-0 left-0 right-0 z-[100] border-t border-gray-200 bg-gray-100 md:hidden pointer-events-auto" data-188-pdp-sticky-actions data-188-pdp-sticky-mobile data-188-skip-draggable>
        {/* Loyalty Discount Message */}
        {birthdayDiscount.active && birthdaySavingsAmount > 0 && (
          <div className="border-b border-pink-700 bg-pink-600 px-2 py-0.5 text-center">
            <span className="flex items-center justify-center gap-1 text-[9px] font-semibold text-white">
              <span aria-hidden>🎁</span>
              Giá sinh nhật: tiết kiệm <strong>{formatPrice(birthdaySavingsAmount)}</strong>
            </span>
          </div>
        )}
        {isAuthenticated && loyaltyDiscountAmount > 0 && (
          <div className="border-b border-green-100 bg-green-50 px-2 py-0.5 text-center">
            <span className="flex items-center justify-center gap-1 text-[9px] font-medium text-green-700">
              <svg className="h-2.5 w-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>
              Hạng <strong>{loyaltyTierName}</strong> giảm <strong>{formatPrice(loyaltyDiscountAmount)}</strong>
            </span>
          </div>
        )}
        <div
          className="flex min-h-[48px] items-stretch gap-1.5 px-1.5 py-0.5 pb-[max(2px,env(safe-area-inset-bottom,0px))]"
          data-188-mobile-bar="labeled"
        >
          <nav
            className="mr-0.5 flex shrink-0 items-stretch gap-px border-r border-gray-200 pr-1.5"
            aria-label="Lối tắt"
          >
            <Link
              href="/"
              className="flex w-11 flex-none flex-col items-center justify-center gap-0.5 py-0.5 text-gray-600 active:opacity-70"
              aria-label="Trang chủ"
            >
              <svg className="h-[17px] w-[17px] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
              </svg>
              <span className="flex flex-col items-center leading-[1.05]">
                <span className="text-[10px]">Trang</span>
                <span className="text-[10px]">chủ</span>
              </span>
            </Link>
            <button
              type="button"
              onClick={handleNanoAiTryOn}
              className="flex w-11 flex-none flex-col items-center justify-center gap-0.5 py-0.5 text-[#ea580c] active:opacity-70"
              aria-label="Thử đồ với NanoAI"
            >
              <svg className="h-[17px] w-[17px] shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" aria-hidden>
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"
                />
              </svg>
              <span className="flex flex-col items-center leading-[1.05]">
                <span className="text-[10px] font-medium">Thử</span>
                <span className="text-[10px] font-medium">đồ</span>
              </span>
            </button>
            <button
              type="button"
              onClick={() => onToggleFavorite(product)}
              aria-label={`Thích, ${formatLikeCount(product.likes)} lượt`}
              className={`flex w-11 flex-none flex-col items-center justify-center gap-0.5 py-0.5 active:opacity-70 ${
                isFavorited ? 'text-red-500' : 'text-gray-600'
              }`}
            >
              <svg className="h-[17px] w-[17px] shrink-0" fill={isFavorited ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
              </svg>
              <span className="flex flex-col items-center leading-[1.05] text-center">
                <span className="text-[10px]">Thích</span>
                <span className="text-[10px] font-semibold tabular-nums tracking-tight">
                  {formatLikeCount(product.likes)}
                </span>
              </span>
            </button>
          </nav>
          <div className="flex min-w-0 flex-1 items-stretch gap-1">
            <button
              type="button"
              onClick={openVariantModal}
              disabled={!canShowStickyBuy}
              className="flex flex-1 items-center justify-center rounded-md bg-gray-500 text-[11px] font-semibold text-white hover:bg-gray-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              THÊM GIỎ
            </button>
            <button
              type="button"
              onClick={openVariantModal}
              disabled={!canShowStickyBuy}
              className="flex flex-1 items-center justify-center rounded-md bg-[#ea580c] text-[11px] font-semibold text-white hover:bg-[#c2410c] disabled:cursor-not-allowed disabled:opacity-50"
            >
              MUA HÀNG
            </button>
          </div>
        </div>
      </div>

      {/* Modal chọn biến thể: tồn ảo lưu ở đây để sau khi mua (tồn ảo = 0) mở lại vẫn thấy 0, không mua thêm được */}
      <ProductVariantModal
        product={product}
        isOpen={variantModalOpen}
        onClose={() => setVariantModalOpen(false)}
        onAddToCart={onAddToCart}
        onBuyNow={onBuyNow}
        isCartLoading={isCartLoading}
        action="both"
        displayStockByVariant={displayStockByVariant}
        setDisplayStockByVariant={setDisplayStockByVariant}
      />
    </div>
  );
}
