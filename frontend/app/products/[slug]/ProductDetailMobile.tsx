'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import type { Product } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { formatPrice, getDiscountPercentage } from '@/lib/utils';
import { mergeProductGalleryPhotoUrls } from '@/lib/product-gallery-merge';
import { ProductFillImage, GalleryThumbImage } from '@/components/product-detail/HideOnImageError';
import { reportUnreachableProductMedia } from '@/lib/report-broken-product-media';
import { getOptimizedImage } from '@/lib/image-utils';
import { hasVideoLink, parseVideoLink, buildYoutubeEmbedSrc } from '@/lib/video-utils';
import RelatedProducts from '@/components/product-detail/RelatedProducts';
import ProductTabs from '@/components/product-detail/ProductTabs';
import ProductVariantModal from './components/ProductVariantModal/ProductVariantModal';
import ProductQAReviewCards from './components/ProductQAReviewCards/ProductQAReviewCards';
import ProductQASection from './components/ProductQASection/ProductQASection';
import ProductReviewSection from './components/ProductReviewSection/ProductReviewSection';
import BirthdayPromoBanner from '@/components/BirthdayPromoBanner';
import BirthdaySavingsCard from '@/components/BirthdaySavingsCard';
import { applyBirthdayDiscount } from '@/lib/birthday-discount';
import { useBirthdayDiscount } from '@/lib/use-birthday-discount';
import AffiliateShareBar, { ProductShareIconButton } from '@/components/affiliate/AffiliateShareBar';
import { useAffiliatePageShare } from '@/lib/use-affiliate-page-share';
import { trackEvent } from '@/lib/analytics';

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
}

export default function ProductDetailMobile({
  product,
  isFavorited,
  isCartLoading,
  onAddToCart,
  onBuyNow,
  onToggleFavorite,
}: ProductDetailMobileProps) {
  const [selectedImage, setSelectedImage] = useState(0);
  const thumbStripRef = useRef<HTMLDivElement>(null);
  const thumbButtonRefs = useRef<Record<number, HTMLButtonElement | null>>({});
  const touchStartRef = useRef<{ x: number; y: number } | null>(null);
  const [variantModalOpen, setVariantModalOpen] = useState(false);
  const [qaModalOpen, setQaModalOpen] = useState(false);
  const [reviewsModalOpen, setReviewsModalOpen] = useState(false);
  /** Tồn ảo theo biến thể (key = productId_variantKey); lưu ở parent để sau khi mua tồn = 0 vẫn giữ, mở lại không mua thêm được. */
  const [displayStockByVariant, setDisplayStockByVariant] = useState<Record<string, number>>({});
  const { isAuthenticated } = useAuth();
  const { copyShareUrl, isApproved: isAffiliateApproved } = useAffiliatePageShare({ shareTitle: product.name });
  const [loyaltyStatus, setLoyaltyStatus] = useState<any>(null);

  const quantity = 1;
  const available = (product.available || 0) > 0;

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
  const displayPrice = birthdayDiscount.active
    ? applyBirthdayDiscount(product.price || 0, birthdayDiscount.percent)
    : product.price || 0;
  const birthdayDiscountAmount = Math.max(0, (product.price || 0) - displayPrice);
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

  useEffect(() => {
    setSelectedImage((prev) => {
      const n = visiblePhotoUrls.length;
      if (hasVideo) {
        if (prev === 0) return prev;
        if (prev > n) return n >= 1 ? n : 0;
        return prev;
      }
      if (n === 0) return 0;
      if (prev >= n) return n - 1;
      return prev;
    });
  }, [hasVideo, visiblePhotoUrls]);

  // Khi có video: index 0 = video, sau đó mới đến ảnh. Video luôn hiển thị đầu tiên.
  const mediaCount = hasVideo ? 1 + visiblePhotoUrls.length : visiblePhotoUrls.length;
  const isShowingVideo = hasVideo && selectedImage === 0;
  const goPrevMedia = useCallback(() => {
    setSelectedImage((i) => Math.max(0, i - 1));
  }, []);
  const goNextMedia = useCallback(() => {
    setSelectedImage((i) => Math.min(mediaCount - 1, i + 1));
  }, [mediaCount]);

  useEffect(() => {
    const btn = thumbButtonRefs.current[selectedImage];
    const strip = thumbStripRef.current;
    if (!btn || !strip) return;
    const stripRect = strip.getBoundingClientRect();
    const btnRect = btn.getBoundingClientRect();
    const left = btn.offsetLeft - strip.offsetLeft - (stripRect.width - btnRect.width) / 2;
    strip.scrollTo({ left: Math.max(0, left), behavior: 'smooth' });
  }, [selectedImage, visiblePhotoUrls.length, hasVideo]);

  const handleMainTouchStart = useCallback((e: React.TouchEvent) => {
    const t = e.touches[0];
    if (!t) return;
    touchStartRef.current = { x: t.clientX, y: t.clientY };
  }, []);

  const handleMainTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      const start = touchStartRef.current;
      touchStartRef.current = null;
      if (!start || mediaCount <= 1) return;
      const t = e.changedTouches[0];
      if (!t) return;
      const dx = t.clientX - start.x;
      const dy = t.clientY - start.y;
      if (Math.abs(dx) < 48 || Math.abs(dx) < Math.abs(dy) * 1.2) return;
      if (dx < 0) goNextMedia();
      else goPrevMedia();
    },
    [mediaCount, goNextMedia, goPrevMedia],
  );

  const mainImageRaw = isShowingVideo
    ? null
    : (visiblePhotoUrls[hasVideo ? selectedImage - 1 : selectedImage] ?? null);
  const videoThumb = parsedVideo?.thumbUrl ?? null;

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
    <div className="md:hidden min-h-screen bg-white pb-32">
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

        <div className="image_list mb-2">
        {/* Main media: chỉ hiển thị video khi có video_url; video luôn ở index 0, sau đó mới ảnh */}
        {isShowingVideo && parsedVideo ? (
        <div
          className="relative rounded-xl overflow-hidden bg-gray-100 mb-2 touch-pan-y"
          onTouchStart={handleMainTouchStart}
          onTouchEnd={handleMainTouchEnd}
        >
          <div className="aspect-[4/5] max-h-[70vh] relative">
            {isShowingVideo && parsedVideo ? (
              parsedVideo.kind === 'youtube' ? (
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
              )
            ) : null}
          </div>
        </div>
        ) : mainImageRaw ? (
        <div
          className="relative rounded-xl overflow-hidden bg-gray-100 mb-2 touch-pan-y"
          onTouchStart={handleMainTouchStart}
          onTouchEnd={handleMainTouchEnd}
        >
          <ProductFillImage
            src={getOptimizedImage(mainImageRaw, { width: 600, height: 750 })}
            alt={product.name}
            onBroken={() => markBrokenPhoto(mainImageRaw)}
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
        </div>
        ) : null}
        {/* Thumbnail dưới khung ảnh chính: chỉ hiển thị nút video khi có video_url; video luôn đầu tiên */}
        {mediaCount > 1 && (
          <div
            ref={thumbStripRef}
            className="product-gallery-thumb-strip flex items-center gap-2 overflow-x-auto scrollbar-hide snap-x snap-mandatory touch-pan-x overscroll-x-contain py-2 -mx-4 px-4"
            style={{ WebkitOverflowScrolling: 'touch' }}
            aria-label="Thư viện ảnh sản phẩm"
          >
            {hasVideo && (
              <button
                ref={(el) => {
                  thumbButtonRefs.current[0] = el;
                }}
                type="button"
                onClick={() => setSelectedImage(0)}
                className={`relative flex-shrink-0 w-16 h-16 snap-center snap-always rounded-lg overflow-hidden border-2 ${
                  selectedImage === 0 ? 'border-[#ea580c]' : 'border-gray-200'
                }`}
                aria-label="Xem video"
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
            {visiblePhotoUrls.map((img, i) => {
              const mediaIndex = hasVideo ? i + 1 : i;
              return (
                <GalleryThumbImage
                  key={img}
                  src={getOptimizedImage(img, { width: 64, height: 64 })}
                  selected={selectedImage === mediaIndex}
                  onClick={() => setSelectedImage(mediaIndex)}
                  onBroken={() => markBrokenPhoto(img)}
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
          </div>
        )}

        </div>

        {productCode && (
          <p className="text-xs text-gray-600 mb-2">
            Mã sp: <span className="copy-code-product">{productCode}</span>
          </p>
        )}

        {/* Giá + giá gốc, giảm giá, trả góp */}
        <div className="space-y-2 mb-3 rounded-2xl border border-orange-100 bg-orange-50/50 p-3">
          {birthdayDiscount.active && birthdayDiscountAmount > 0 && (
            <div className="inline-flex items-center gap-1.5 rounded-full bg-pink-600 px-2.5 py-1 text-[11px] font-bold text-white shadow-sm">
              <span aria-hidden>🎂</span>
              Giá sinh nhật đã giảm {birthdayDiscount.percent}%
            </div>
          )}
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="text-2xl font-extrabold text-[#ea580c]">
              {formatPrice(displayPrice)}
            </span>
            {birthdayDiscount.active && birthdayDiscountAmount > 0 && (
              <>
                <span className="inline-flex items-baseline gap-1 rounded-full border border-gray-300 bg-white px-2.5 py-1 text-xs font-semibold text-gray-700 shadow-sm">
                  <span className="text-[10px] font-medium text-gray-500">Giá gốc</span>
                  <span className="text-sm text-gray-800 line-through decoration-1 decoration-gray-400">
                    {formatPrice(product.price)}
                  </span>
                </span>
                <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-pink-700 ring-1 ring-pink-200">
                  Tiết kiệm {formatPrice(birthdayDiscountAmount)}
                </span>
              </>
            )}
            {product.original_price && product.original_price > (product.price ?? 0) && (
              <>
                {!birthdayDiscount.active && (
                  <span className="text-sm text-gray-500 line-through">
                    {formatPrice(product.original_price)}
                  </span>
                )}
                <span className="bg-red-500 text-white px-1.5 py-0.5 rounded text-xs font-bold">
                  -{getDiscountPercentage(product.original_price, product.price ?? 0)}%
                </span>
              </>
            )}
          </div>
        </div>

        <BirthdaySavingsCard
          percent={birthdayDiscount.percent}
          savings={birthdayDiscountAmount}
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
          <ProductTabs product={product} />
        </div>

        <ProductReviewSection product={product} modalOnly modalOpen={reviewsModalOpen} onModalClose={() => setReviewsModalOpen(false)} onModalOpen={() => setReviewsModalOpen(true)} />
        <ProductQASection product={product} modalOnly modalOpen={qaModalOpen} onModalClose={() => setQaModalOpen(false)} onModalOpen={() => setQaModalOpen(true)} />

        {/* Related products - 1 block, tab chỉ đổi filter sau */}
        <div className="border-t border-gray-100 pt-4">
          <RelatedProducts currentProduct={product} />
        </div>
      </div>

      {/* Sticky bottom bar: Trang · Thử đồ · Thích | THÊM GIỎ | MUA HÀNG */}
      <div className="fixed bottom-0 left-0 right-0 z-30 bg-gray-100 border-t border-gray-200 safe-area-pb md:hidden">
        {/* Loyalty Discount Message */}
        {birthdayDiscount.active && birthdayDiscountAmount > 0 && (
          <div className="bg-pink-600 border-b border-pink-700 px-2 py-1 text-center">
            <span className="text-[10px] text-white font-semibold flex items-center justify-center gap-1">
              <span aria-hidden>🎁</span>
              Giá sinh nhật: tiết kiệm <strong>{formatPrice(birthdayDiscountAmount)}</strong>
            </span>
          </div>
        )}
        {isAuthenticated && loyaltyDiscountAmount > 0 && (
          <div className="bg-green-50 border-b border-green-100 px-2 py-1 text-center">
            <span className="text-[10px] text-green-700 font-medium flex items-center justify-center gap-1">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>
              Hạng <strong>{loyaltyTierName}</strong> giảm <strong>{formatPrice(loyaltyDiscountAmount)}</strong> khi mua hàng
            </span>
          </div>
        )}
        <div className="flex items-center h-14 px-2 gap-2">
          <nav
            className="flex shrink-0 items-center gap-px border-r border-gray-200 pr-2 mr-0.5"
            aria-label="Lối tắt"
          >
            <Link
              href="/"
              className="flex w-12 flex-none flex-col items-center justify-center gap-px py-0 text-gray-600 active:opacity-70"
              aria-label="Trang chủ"
            >
              <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
              </svg>
              <span className="flex flex-col items-center gap-0 leading-none">
                <span className="text-[10px] text-gray-600">Trang</span>
                <span className="text-[10px] text-gray-600">chủ</span>
              </span>
            </Link>
            <button
              type="button"
              data-nanoai-try-on
              className="flex w-12 flex-none flex-col items-center justify-center gap-px py-0 text-[#ea580c] active:opacity-70"
              aria-label="Thử đồ với NanoAI"
            >
              <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" aria-hidden>
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"
                />
              </svg>
              <span className="flex flex-col items-center gap-0 leading-none">
                <span className="text-[10px] font-medium text-[#ea580c]">Thử</span>
                <span className="text-[10px] font-medium text-[#ea580c]">đồ</span>
              </span>
            </button>
            <button
              type="button"
              onClick={() => onToggleFavorite(product)}
              aria-label={`Thích, ${formatLikeCount(product.likes)} lượt`}
              className={`flex w-12 flex-none flex-col items-center justify-center gap-px py-0 active:opacity-70 ${
                isFavorited ? 'text-red-500' : 'text-gray-600'
              }`}
            >
              <svg className="w-5 h-5 shrink-0" fill={isFavorited ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
              </svg>
              <span className="flex flex-col items-center gap-0 leading-none text-center">
                <span className="text-[10px] leading-none">Thích</span>
                <span className="text-[10px] font-semibold tabular-nums leading-none tracking-tight">
                  {formatLikeCount(product.likes)}
                </span>
              </span>
            </button>
          </nav>
          <div className="flex flex-1 gap-2 justify-end min-w-0">
            <button
              type="button"
              onClick={openVariantModal}
              disabled={!available}
              className="flex-1 max-w-[120px] py-2.5 rounded-lg font-semibold text-sm bg-gray-500 text-white hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              THÊM GIỎ
            </button>
            <button
              type="button"
              onClick={openVariantModal}
              disabled={!available}
              className="flex-1 max-w-[120px] py-2.5 rounded-lg font-semibold text-sm bg-[#ea580c] text-white hover:bg-[#c2410c] disabled:opacity-50 disabled:cursor-not-allowed"
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
