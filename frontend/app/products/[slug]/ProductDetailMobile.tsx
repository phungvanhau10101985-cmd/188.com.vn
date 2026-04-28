'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import type { Product } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { formatPrice, getDiscountPercentage } from '@/lib/utils';
import { getOptimizedImage } from '@/lib/image-utils';
import { hasVideoLink, parseVideoLink } from '@/lib/video-utils';
import RelatedProducts from '@/components/product-detail/RelatedProducts';
import ProductTabs from '@/components/product-detail/ProductTabs';
import ProductVariantModal from './components/ProductVariantModal/ProductVariantModal';
import ProductQAReviewCards from './components/ProductQAReviewCards/ProductQAReviewCards';
import ProductQASection from './components/ProductQASection/ProductQASection';
import ProductReviewSection from './components/ProductReviewSection/ProductReviewSection';
import { useToast } from '@/components/ToastProvider';
import { trackEvent } from '@/lib/analytics';

const RELATED_TABS = [
  { id: 'bestselling', label: 'Sản phẩm bán chạy' },
  { id: 'same_price', label: 'SP cùng loại cùng tầm giá' },
  { id: 'lower_price', label: 'SP cùng loại giá thấp hơn' },
  { id: 'higher_price', label: 'SP cùng loại giá cao hơn' },
];

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
  const [activeTab, setActiveTab] = useState(RELATED_TABS[0].id);
  const [variantModalOpen, setVariantModalOpen] = useState(false);
  const [qaModalOpen, setQaModalOpen] = useState(false);
  const [reviewsModalOpen, setReviewsModalOpen] = useState(false);
  /** Tồn ảo theo biến thể (key = productId_variantKey); lưu ở parent để sau khi mua tồn = 0 vẫn giữ, mở lại không mua thêm được. */
  const [displayStockByVariant, setDisplayStockByVariant] = useState<Record<string, number>>({});
  const { isAuthenticated } = useAuth();
  const { pushToast } = useToast();
  const [loyaltyStatus, setLoyaltyStatus] = useState<any>(null);

  const quantity = 1;
  const available = (product.available || 0) > 0;

  useEffect(() => {
    if (isAuthenticated) {
      apiClient.getMyLoyaltyStatus().then(setLoyaltyStatus).catch(() => {});
    }
  }, [isAuthenticated]);

  const loyaltyDiscountPercent = loyaltyStatus?.current_tier?.discount_percent || 0;
  const loyaltyDiscountAmount = (product.price * loyaltyDiscountPercent) / 100;
  const loyaltyTierName = loyaltyStatus?.current_tier?.name || 'L0';

  const openVariantModal = () => setVariantModalOpen(true);

  const images = [
    ...(product.main_image ? [product.main_image] : []),
    ...(product.images?.filter((img) => img !== product.main_image) || []),
  ];
  const hasVideo = hasVideoLink(product.video_link);
  const parsedVideo = parseVideoLink(product.video_link);

  // Khi có video: index 0 = video, sau đó mới đến ảnh. Video luôn hiển thị đầu tiên.
  const mediaCount = hasVideo ? 1 + images.length : images.length;
  const isShowingVideo = hasVideo && selectedImage === 0;
  const mainImage = isShowingVideo ? null : (images[hasVideo ? selectedImage - 1 : selectedImage] || product.main_image);
  const videoThumb = parsedVideo?.thumbUrl ?? null;

  const handleCopyLink = () => {
    const url = typeof window !== 'undefined' ? window.location.href : '';
    navigator.clipboard.writeText(url).then(() => {
      pushToast({ title: 'Đã copy link sản phẩm', variant: 'success', durationMs: 2000 });
      trackEvent('share_product', { method: 'copy_link', product_id: product.id });
    });
  };

  const productCode = product.code || product.product_id || '';

  return (
    <div className="md:hidden min-h-screen bg-white pb-32">
      {/* Tabs: Sản phẩm bán chạy, SP cùng loại... */}
      <div className="sticky top-0 z-10 bg-white border-b border-gray-100 overflow-x-auto scrollbar-hide">
        <div className="flex gap-2 min-w-max px-4 py-2">
          {RELATED_TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`flex-shrink-0 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
                activeTab === tab.id
                  ? 'bg-[#ea580c] text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="px-4 py-3">
        {/* Tiêu đề sản phẩm */}
        <h1 className="text-base font-bold text-gray-900 leading-tight mb-3 uppercase">
          {product.name}
          {isAuthenticated && loyaltyTierName !== 'L0' && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800 ml-2 align-middle">
              Hạng thành viên {loyaltyTierName}
            </span>
          )}
        </h1>

        {/* Main media: chỉ hiển thị video khi có video_url; video luôn ở index 0, sau đó mới ảnh */}
        <div className="relative rounded-xl overflow-hidden bg-gray-100 mb-2">
          <div className="aspect-[4/5] max-h-[70vh] relative">
            {isShowingVideo && parsedVideo ? (
              parsedVideo.kind === 'youtube' ? (
                <>
                  <iframe
                    title={`Video ${product.name}`}
                    src={`https://www.youtube.com/embed/${parsedVideo.urlOrId}?autoplay=0`}
                    className="absolute inset-0 w-full h-full"
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                    allowFullScreen
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
            ) : (
              <>
                <Image
                  src={getOptimizedImage(mainImage || product.main_image, { width: 600, height: 750 })}
                  alt={product.name}
                  fill
                  className="object-cover"
                  sizes="100vw"
                />
                <div className="absolute top-2 left-2 flex items-center gap-1.5 bg-black/50 text-white text-[10px] px-2 py-1 rounded">
                  <span className="font-medium truncate max-w-[140px]">{product.brand_name || '188 com vn'}</span>
                </div>
                <div className="absolute bottom-2 left-2 flex gap-2">
                  <button type="button" className="w-8 h-8 rounded-full bg-white/80 flex items-center justify-center" aria-label="Chia sẻ">
                    <svg className="w-4 h-4 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" /></svg>
                  </button>
                  <button type="button" className="w-8 h-8 rounded-full bg-white/80 flex items-center justify-center" aria-label="Đã xem">
                    <svg className="w-4 h-4 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                  </button>
                </div>
                <a href="https://zalo.me" target="_blank" rel="noopener noreferrer" className="absolute top-2 right-2 w-10 h-10 rounded-full bg-blue-500 flex items-center justify-center shadow-lg" aria-label="Zalo">
                  <span className="text-white text-xs font-bold">Z</span>
                </a>
              </>
            )}
          </div>
        </div>
        {productCode && (
          <p className="text-xs text-gray-600 mt-1.5 px-1">#{productCode}</p>
        )}

        {/* Thumbnail dưới khung ảnh chính: chỉ hiển thị nút video khi có video_url; video luôn đầu tiên */}
        {mediaCount > 1 && (
          <div className="flex items-center gap-2 overflow-x-auto scrollbar-hide py-2 -mx-4 px-4">
            {hasVideo && (
              <button
                type="button"
                onClick={() => setSelectedImage(0)}
                className={`relative flex-shrink-0 w-16 h-16 rounded-lg overflow-hidden border-2 ${
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
            {images.map((img, i) => {
              const mediaIndex = hasVideo ? i + 1 : i;
              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => setSelectedImage(mediaIndex)}
                  className={`relative flex-shrink-0 w-16 h-16 rounded-lg overflow-hidden border-2 ${
                    selectedImage === mediaIndex ? 'border-[#ea580c]' : 'border-gray-200'
                  }`}
                >
                  <Image
                    src={getOptimizedImage(img, { width: 64, height: 64 })}
                    alt=""
                    width={64}
                    height={64}
                    className="w-full h-full object-cover"
                  />
                </button>
              );
            })}
            <button
              type="button"
              onClick={handleCopyLink}
              className="flex-shrink-0 px-3 py-2 rounded-lg border border-gray-300 text-xs font-medium text-gray-700 hover:bg-gray-50"
            >
              Copy link
            </button>
          </div>
        )}

        {/* Mã sp */}
        {productCode && (
          <p className="text-xs text-gray-600 mb-2">Mã sp: {productCode}</p>
        )}

        {/* Giá + giá gốc, giảm giá, trả góp */}
        <div className="space-y-1 mb-3">
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="text-xl font-bold text-[#ea580c]">
              {formatPrice(product.price)}
            </span>
            {product.original_price && product.original_price > (product.price ?? 0) && (
              <>
                <span className="text-sm text-gray-500 line-through">
                  {formatPrice(product.original_price)}
                </span>
                <span className="bg-red-500 text-white px-1.5 py-0.5 rounded text-xs font-bold">
                  -{getDiscountPercentage(product.original_price, product.price ?? 0)}%
                </span>
              </>
            )}
          </div>
        </div>

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
          <p className="text-xs text-gray-700 leading-snug">
            🚚 Giao hàng toàn quốc – Miễn phí đơn từ 500k. 🔁 Đổi trả trong 7 ngày nếu sản phẩm lỗi hoặc không đúng mô tả.{' '}
            <Link href="/policies/shipping" className="text-[#ea580c] hover:underline">
              👉 Xem chi tiết tại Chính sách giao hàng và Chính sách đổi trả.
            </Link>
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
        <p className="text-xs mb-4">
          <Link href="/policies/reviews" className="text-[#ea580c] hover:underline">
            Bấm để xem Chính sách quản lý đánh giá và quản lý chất lượng sản phẩm
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

      {/* Sticky bottom bar: Trang chủ, Liên hệ, Thích | THÊM GIỎ | MUA HÀNG */}
      <div className="fixed bottom-0 left-0 right-0 z-30 bg-gray-100 border-t border-gray-200 safe-area-pb md:hidden">
        {/* Loyalty Discount Message */}
        {isAuthenticated && loyaltyDiscountAmount > 0 && (
          <div className="bg-green-50 border-b border-green-100 px-2 py-1 text-center">
            <span className="text-[10px] text-green-700 font-medium flex items-center justify-center gap-1">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>
              Hạng <strong>{loyaltyTierName}</strong> giảm <strong>{formatPrice(loyaltyDiscountAmount)}</strong> khi mua hàng
            </span>
          </div>
        )}
        <div className="flex items-center h-14 px-2 gap-2">
          <Link href="/" className="flex flex-col items-center justify-center flex-shrink-0 w-12 text-gray-600">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /></svg>
            <span className="text-[10px]">Trang chủ</span>
          </Link>
          <Link href="/info/lien-he" className="flex flex-col items-center justify-center flex-shrink-0 w-12 text-gray-600">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>
            <span className="text-[10px]">Liên hệ</span>
          </Link>
          <button
            type="button"
            onClick={() => onToggleFavorite(product)}
            className={`flex flex-col items-center justify-center flex-shrink-0 w-12 ${
              isFavorited ? 'text-red-500' : 'text-gray-600'
            }`}
          >
            <svg className="w-6 h-6" fill={isFavorited ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" /></svg>
            <span className="text-[10px]">Thích {product.likes ?? 0}</span>
          </button>
          <div className="flex-1 flex gap-2 justify-end">
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
