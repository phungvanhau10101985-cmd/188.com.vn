// frontend/app/products/[slug]/components/ProductInfo/ProductActions.tsx - ĐÃ SỬA LỖI PROPS
'use client';

import { useCallback, useLayoutEffect, useState } from 'react';
import { Product } from '@/types/api';
import {
  buildNanoAiGatewayPayloadFrom188Product,
  nanoAiGatewayButtonDataset,
  NANO_AI_CTX_SOURCE_PRODUCT_PDP,
} from '@/lib/nanoai-hosted-chat';
import { useNanoAiMessaging } from '@/lib/use-nanoai-messaging';

interface ProductActionsProps {
  product: Product;
  /** Ảnh SP đang xem (gallery / màu) — gửi vào cổng NanoAI. */
  viewingImageUrl?: string | null;
  quantity: number;
  selectedSize: string;
  selectedColor: string;
  available: boolean;
  /** false khi SP có size/màu nhưng khách chưa chọn đủ — chặn thêm giỏ / mua ngay */
  variantsComplete?: boolean;
  /** Gợi ý khi hover (ví dụ chưa chọn size) */
  variantSelectionHint?: string;
  onAddToCart: (product: Product, quantity: number, selectedSize?: string, selectedColor?: string) => void;
  onToggleFavorite: (product: Product) => void;
  onBuyNow: (product: Product, quantity: number, selectedSize?: string, selectedColor?: string) => void;
  isCartLoading?: boolean;
  isFavorited?: boolean;
}

export default function ProductActions({
  product,
  viewingImageUrl,
  quantity,
  selectedSize,
  selectedColor,
  available,
  variantsComplete = true,
  variantSelectionHint,
  onAddToCart,
  onToggleFavorite,
  onBuyNow,
  isCartLoading = false,
  isFavorited = false
}: ProductActionsProps) {
  const { openTryOnForProduct } = useNanoAiMessaging();
  /** Tránh hydration mismatch: server luôn isLoading=false; client có thể còn state từ CartProvider khi soft-nav. */
  const [uiCartLoading, setUiCartLoading] = useState(false);
  useLayoutEffect(() => {
    setUiCartLoading(isCartLoading);
  }, [isCartLoading]);

  const canPurchase = available && !uiCartLoading && variantsComplete;
  const blockHint = !variantsComplete ? variantSelectionHint : undefined;

  const nanoPayload = buildNanoAiGatewayPayloadFrom188Product(product, {
    imageUrl: viewingImageUrl,
  });
  const tryOnAttrs = nanoAiGatewayButtonDataset(nanoPayload, 'try_on');

  const handleNanoAiTryOn = useCallback(() => {
    void openTryOnForProduct(product, {
      imageUrl: viewingImageUrl,
      ctxSource: NANO_AI_CTX_SOURCE_PRODUCT_PDP,
      source: 'product_detail_actions',
    });
  }, [openTryOnForProduct, product, viewingImageUrl]);

  const handleAddToCart = () => {
    onAddToCart(product, quantity, selectedSize, selectedColor);
  };

  const handleBuyNow = () => {
    onBuyNow(product, quantity, selectedSize, selectedColor);
  };

  const handleToggleFavorite = () => {
    onToggleFavorite(product);
  };

  return (
    <div className="pt-3">
      <div className="flex flex-col sm:flex-row gap-2">
        <button
          type="button"
          onClick={handleAddToCart}
          disabled={!canPurchase}
          title={blockHint}
          className={`flex-1 py-3 px-4 rounded-lg font-semibold text-sm transition-all flex items-center justify-center space-x-2 group ${
            canPurchase
              ? 'bg-gray-500 hover:bg-gray-600 text-white shadow hover:shadow-md'
              : 'bg-gray-300 text-gray-500 cursor-not-allowed'
          } ${uiCartLoading ? 'opacity-70' : ''}`}
        >
          <span className="text-base group-hover:scale-105 transition-transform">🛒</span>
          <span>{uiCartLoading ? 'Đang thêm...' : 'Thêm Vào Giỏ'}</span>
        </button>
        <button
          type="button"
          onClick={handleBuyNow}
          disabled={!canPurchase}
          title={blockHint}
          className={`flex-1 py-3 px-4 rounded-lg font-semibold text-sm transition-all ${
            canPurchase
              ? 'bg-[#ea580c] hover:bg-[#c2410c] text-white shadow hover:shadow-md'
              : 'bg-gray-300 text-gray-500 cursor-not-allowed'
          } ${uiCartLoading ? 'opacity-70' : ''}`}
        >
          {uiCartLoading ? 'Đang xử lý...' : 'Mua ngay'}
        </button>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            {...tryOnAttrs}
            onClick={handleNanoAiTryOn}
            className="w-11 h-11 rounded-lg font-semibold text-xs bg-[#ea580c] text-white hover:bg-[#c2410c] transition-colors flex flex-col items-center justify-center gap-0.5"
            aria-label="Thử đồ với NanoAI"
          >
            <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"
              />
            </svg>
            <span className="text-[9px] leading-none">Thử đồ</span>
          </button>
          <button
            onClick={handleToggleFavorite}
            disabled={uiCartLoading}
            className={`w-11 h-11 border-2 rounded-lg flex items-center justify-center transition-all shrink-0 ${
              uiCartLoading
                ? 'border-gray-300 bg-gray-100 cursor-not-allowed opacity-70'
                : isFavorited
                  ? 'border-red-400 bg-red-50 text-red-500'
                  : 'border-pink-300 hover:bg-pink-50 hover:border-pink-400'
            }`}
            title={isFavorited ? 'Bỏ yêu thích' : 'Thêm vào yêu thích'}
          >
            {isFavorited ? '❤️' : '🤍'}
          </button>
        </div>
      </div>
    </div>
  );
}
