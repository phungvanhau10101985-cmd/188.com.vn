// frontend/app/products/[slug]/components/ProductInfo/ProductInfo.tsx - ĐÃ SỬA LỖI PROPS
'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import Link from 'next/link';
import { Product } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { formatPrice, getDiscountPercentage, displayableBrandOrOrigin } from '@/lib/utils';
import VariantSelector from '@/components/product-detail/VariantSelector';
import { colorLabelForCart } from '@/lib/product-color-variant';
import ProductActions from './ProductActions';
import ProductQAReviewCards from '../ProductQAReviewCards/ProductQAReviewCards';
import ProductVariantModal from '../ProductVariantModal/ProductVariantModal';
import { useToast } from '@/components/ToastProvider';
import { trackEvent } from '@/lib/analytics';
import {
  openNanoAiTryOnEmbed,
  buildNanoAiTryOnCtxFrom188Product,
  NANO_AI_CTX_SOURCE_PRODUCT_PDP,
} from '@/lib/nanoai-hosted-chat';

interface ProductInfoProps {
  product: Product;
  onAddToCart: (product: Product, quantity: number, selectedSize?: string, selectedColor?: string) => void;
  onToggleFavorite: (product: Product) => void;
  onBuyNow: (product: Product, quantity: number, selectedSize?: string, selectedColor?: string) => void;
  onOpenQA?: () => void;
  onOpenReviews?: () => void;
  onColorImageChange?: (imageUrl: string | null) => void;
  isCartLoading?: boolean;
  isFavorited?: boolean;
}

export default function ProductInfo({ 
  product, 
  onAddToCart, 
  onToggleFavorite, 
  onBuyNow,
  onOpenQA,
  onOpenReviews,
  onColorImageChange,
  isCartLoading = false,
  isFavorited = false
}: ProductInfoProps) {
  const [selectedSize, setSelectedSize] = useState('');
  const [selectedColorIndex, setSelectedColorIndex] = useState(-1);
  const [quantity, setQuantity] = useState(1);
  const actionsRef = useRef<HTMLDivElement | null>(null);
  const [showStickyActions, setShowStickyActions] = useState(false);
  const [variantModalOpen, setVariantModalOpen] = useState(false);
  const [variantModalAction, setVariantModalAction] = useState<'add' | 'buy' | 'both'>('both');
  const [displayStockByVariant, setDisplayStockByVariant] = useState<Record<string, number>>({});
  const { isAuthenticated } = useAuth();
  const { pushToast } = useToast();
  const [loyaltyStatus, setLoyaltyStatus] = useState<any>(null);

  const handleNanoAiTryOn = useCallback(async () => {
    const ctx = buildNanoAiTryOnCtxFrom188Product(product);
    const result = await openNanoAiTryOnEmbed(ctx, NANO_AI_CTX_SOURCE_PRODUCT_PDP);
    if (!result.ok) {
      if (result.reason === 'no_chat_config') {
        pushToast({
          title: 'Chưa mở được thử đồ',
          description:
            'Kiểm tra mã nhúng NanoAI (data-chat-url trên script) hoặc biến NEXT_PUBLIC_NANOAI_CHAT_URL trong frontend.',
          variant: 'info',
          durationMs: 4200,
        });
      } else {
        pushToast({
          title: 'Chưa mở được khung chat',
          description: 'Bấm biểu tượng chat NanoAI góc màn hình — ngữ cảnh sản phẩm đã được gửi kèm.',
          variant: 'info',
          durationMs: 4200,
        });
      }
      return;
    }
    trackEvent('nanoai_try_on_open', {
      product_id: product.id,
      source: 'product_detail_desktop_sticky',
      mode: result.mode,
    });
  }, [product, pushToast]);

  const available = (product.available || 0) > 0;
  const hasDiscount = product.original_price && product.original_price > product.price;

  useEffect(() => {
    if (isAuthenticated) {
      apiClient.getMyLoyaltyStatus().then(setLoyaltyStatus).catch(() => {});
    }
  }, [isAuthenticated]);

  const loyaltyDiscountPercent = loyaltyStatus?.current_tier?.discount_percent || 0;
  const loyaltyDiscountAmount = (product.price * loyaltyDiscountPercent) / 100;
  const loyaltyTierName = loyaltyStatus?.current_tier?.name || 'L0';

  const colorList = product.colors || [];
  const selectedColorForCart =
    selectedColorIndex >= 0 && colorList[selectedColorIndex]
      ? colorLabelForCart(colorList, selectedColorIndex)
      : '';

  const hasSizes = (product.sizes?.length ?? 0) > 0;
  const hasColors = colorList.length > 0;
  /** Bắt buộc chọn size/màu khi SP khai báo — tránh thêm giỏ khi size còn trống */
  const variantsComplete =
    (!hasSizes || selectedSize.trim() !== '') &&
    (!hasColors || selectedColorForCart.trim() !== '');
  const variantSelectionHint = !variantsComplete
    ? hasSizes && !selectedSize.trim()
      ? 'Vui lòng chọn kích thước'
      : hasColors && !selectedColorForCart.trim()
        ? 'Vui lòng chọn màu sắc'
        : 'Vui lòng chọn biến thể'
    : undefined;

  useEffect(() => {
    const n = colorList.length;
    setSelectedColorIndex(n > 0 ? 0 : -1);
  }, [product.id, colorList.length]);

  useEffect(() => {
    if (!actionsRef.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        setShowStickyActions(!entry.isIntersecting);
      },
      { root: null, threshold: 0.1 }
    );
    observer.observe(actionsRef.current);
    return () => observer.disconnect();
  }, []);

  const handleColorChange = (colorIndex: number, _colorName: string, colorImage?: string) => {
    setSelectedColorIndex(colorIndex);
    onColorImageChange?.(colorImage || null);
  };

  const openVariantModal = () => {
    setVariantModalAction('both');
    setVariantModalOpen(true);
  };

  return (
    <div className="space-y-4 md:pb-20">
      {/* Product Name and Basic Info */}
      <div>
        <h1 className="text-xl font-bold text-gray-900 mb-1 leading-snug">
          {product.name}
          {isAuthenticated && loyaltyTierName !== 'L0' && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800 ml-2 align-middle">
              Hạng thành viên {loyaltyTierName}
            </span>
          )}
        </h1>
        {displayableBrandOrOrigin(product.brand_name) && (
          <p className="text-sm text-gray-600 mb-2">Thương hiệu: {displayableBrandOrOrigin(product.brand_name)}</p>
        )}
        
        <p className="text-xs text-gray-500 mb-2">
          Mã SP:{' '}
          <span className="copy-code-product font-mono text-gray-700">
            {product.code?.trim() || product.product_id || '—'}
          </span>
        </p>

        <div className="flex items-center space-x-3 mb-2 text-sm">
          <div className="flex items-center space-x-1">
            <span className="text-yellow-400 text-base">★</span>
            <span className="font-semibold text-gray-700">
              {product.rating_point?.toFixed(1) || '0.0'}
            </span>
          </div>
          <span className="text-gray-400">•</span>
          <span className="text-gray-600">{product.rating_total || 0} đánh giá</span>
          <span className="text-gray-400">•</span>
          <span className="text-gray-600">{product.purchases || 0} đã bán</span>
        </div>
      </div>

      {/* Price Section */}
      <div className="space-y-1">
        <div className="flex items-baseline space-x-2 flex-wrap gap-y-0.5">
          <span className="text-2xl font-bold text-[#ea580c]">
            {formatPrice(product.price)}
          </span>
          {hasDiscount && (
            <>
              <span className="text-lg text-gray-500 line-through">
                {formatPrice(product.original_price!)}
              </span>
              <span className="bg-red-500 text-white px-1.5 py-0.5 rounded text-xs font-bold">
                -{getDiscountPercentage(product.original_price!, product.price)}%
              </span>
            </>
          )}
        </div>
      </div>

      {/* Variant Selectors */}
      <VariantSelector
        sizes={product.sizes || []}
        colors={colorList}
        selectedSize={selectedSize}
        selectedColorIndex={selectedColorIndex}
        onSizeChange={setSelectedSize}
        onColorChange={handleColorChange}
      />

      {/* Quantity Selector */}
      <div className="space-y-1.5">
        <h3 className="font-semibold text-gray-900 text-sm">Số lượng mua:</h3>
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setQuantity(Math.max(1, quantity - 1))}
            className="w-8 h-8 border border-gray-300 rounded flex items-center justify-center hover:bg-gray-50 text-sm"
          >
            -
          </button>
          <span className="w-10 text-center font-semibold text-sm">{quantity}</span>
          <button
            onClick={() => setQuantity(quantity + 1)}
            className="w-8 h-8 border border-gray-300 rounded flex items-center justify-center hover:bg-gray-50 text-sm"
          >
            +
          </button>
        </div>
      </div>

      {/* Tổng số */}
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-semibold text-gray-900">Tổng số:</span>
        <span className="text-lg font-bold text-[#ea580c]">{formatPrice((product.price || 0) * quantity)}</span>
      </div>

      {/* Loyalty Discount Message */}
      {isAuthenticated && loyaltyDiscountAmount > 0 && (
        <div className="text-sm text-green-600 font-medium bg-green-50 p-2 rounded-lg border border-green-100 flex items-center gap-2">
          <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>
          <span>Hạng thành viên <strong>{loyaltyTierName}</strong> giảm <strong>{formatPrice(loyaltyDiscountAmount * quantity)}</strong> khi mua hàng</span>
        </div>
      )}

      {/* Action Buttons */}
      <div ref={actionsRef}>
        <ProductActions
          product={product}
          quantity={quantity}
          selectedSize={selectedSize}
          selectedColor={selectedColorForCart}
          available={available}
          variantsComplete={variantsComplete}
          variantSelectionHint={variantSelectionHint}
          onAddToCart={onAddToCart}
          onToggleFavorite={onToggleFavorite}
          onBuyNow={onBuyNow}
          isCartLoading={isCartLoading}
          isFavorited={isFavorited}
        />
      </div>

      {/* Giao hàng & Đổi trả */}
      <div className="border-t border-gray-100 pt-3">
        <p className="text-xs text-gray-700 leading-snug">
          🚚 Giao hàng toàn quốc – Miễn phí đơn từ 500k. 🔁 Đổi trả trong 7 ngày nếu sản phẩm lỗi hoặc không đúng mô tả.{' '}
          <span className="text-[#ea580c]">
            👉 Xem chi tiết tại{' '}
            <Link href="/info/chinh-sach-giao-hang" className="hover:underline font-medium">
              Chính sách giao hàng
            </Link>{' '}
            và{' '}
            <Link href="/info/doi-tra-hoan-tien" className="hover:underline font-medium">
              Chính sách đổi trả
            </Link>
            .
          </span>
        </p>
      </div>

      {/* Thống kê: Đã bán, Lượt thích, Đánh giá */}
      <div className="flex flex-wrap items-center gap-3 text-xs text-gray-600">
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

      {/* Dịch vụ */}
      <div>
        <p className="text-xs text-gray-700 leading-snug">
          <strong className="text-gray-900">Dịch vụ:</strong> thanh toán khi nhận hàng, đổi size nếu không vừa, xem hàng trước khi nhận.
        </p>
      </div>

      {/* Lưu ý */}
      <div>
        <p className="font-semibold text-gray-900 text-xs mb-1">Lưu ý:</p>
        <ul className="list-disc list-inside text-xs text-gray-700 space-y-0.5 leading-snug">
          <li>Sản phẩm váy, áo, quần cắt may có thể chênh lệch 1 – 2 (cm).</li>
          <li>Do ánh sáng và thiết bị chụp hình, màu sắc hình ảnh và thực tế có thể có chênh lệch nhỏ.</li>
        </ul>
      </div>

      {/* Chính sách đánh giá */}
      <p className="text-xs">
        <Link href="/info/chinh-sach-danh-gia" className="text-[#ea580c] hover:underline">
          Bấm để xem Chính sách quản lý đánh giá và quản lý chất lượng sản phẩm
        </Link>
      </p>

      <ProductQAReviewCards
        product={product}
        onOpenQA={onOpenQA}
        onOpenReviews={onOpenReviews}
        layout="grid"
      />

      {/* Sticky bottom actions (desktop) */}
      {showStickyActions && (
        <div className="hidden md:block">
          <div className="fixed bottom-0 left-0 right-0 z-30 bg-gray-100 border-t border-gray-200">
            <div className="max-w-7xl mx-auto px-4">
              <div className="flex items-center justify-center h-14">
                <div className="flex items-center gap-3">
                  <Link href="/" className="flex flex-col items-center justify-center flex-shrink-0 w-14 text-gray-600">
                  <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /></svg>
                  <span className="text-[11px]">Trang chủ</span>
                  </Link>
                  <button
                    type="button"
                    onClick={() => void handleNanoAiTryOn()}
                    className="flex flex-col items-center justify-center flex-shrink-0 w-14 text-[#ea580c] hover:opacity-90 active:opacity-75"
                    aria-label="Thử đồ với NanoAI"
                  >
                    <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"
                      />
                    </svg>
                    <span className="text-[11px] font-medium">Thử đồ</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => onToggleFavorite(product)}
                    disabled={isCartLoading}
                    className={`flex flex-col items-center justify-center flex-shrink-0 w-14 ${
                      isFavorited ? 'text-red-500' : 'text-gray-600'
                    } ${isCartLoading ? 'opacity-70 cursor-not-allowed' : ''}`}
                  >
                    <svg className="w-7 h-7" fill={isFavorited ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" /></svg>
                    <span className="text-[11px]">Thích {product.likes ?? 0}</span>
                  </button>
                </div>
                <div className="flex items-center gap-2 ml-2">
                  <button
                    onClick={openVariantModal}
                    disabled={!available || isCartLoading}
                    className={`min-w-[160px] px-4 py-2.5 rounded-lg font-semibold text-sm transition-all whitespace-nowrap ${
                      available && !isCartLoading
                        ? 'bg-gray-500 text-white hover:bg-gray-600'
                        : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                    } ${isCartLoading ? 'opacity-70' : ''}`}
                  >
                    {isCartLoading ? 'ĐANG THÊM...' : 'THÊM GIỎ'}
                  </button>
                  <button
                    onClick={openVariantModal}
                    disabled={!available || isCartLoading}
                    className={`min-w-[160px] px-4 py-2.5 rounded-lg font-semibold text-sm transition-all whitespace-nowrap ${
                      available && !isCartLoading
                        ? 'bg-[#ea580c] text-white hover:bg-[#c2410c]'
                        : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                    } ${isCartLoading ? 'opacity-70' : ''}`}
                  >
                    {isCartLoading ? 'ĐANG XỬ LÝ...' : 'MUA HÀNG'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <ProductVariantModal
        product={product}
        isOpen={variantModalOpen}
        onClose={() => setVariantModalOpen(false)}
        onAddToCart={onAddToCart}
        onBuyNow={onBuyNow}
        isCartLoading={isCartLoading}
        action={variantModalAction}
        displayStockByVariant={displayStockByVariant}
        setDisplayStockByVariant={setDisplayStockByVariant}
      />
    </div>
  );
}
