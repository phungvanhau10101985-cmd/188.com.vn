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
  const { openConsultForProduct, openTryOnForProduct } = useNanoAiMessaging();
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
  const consultAttrs = nanoAiGatewayButtonDataset(nanoPayload, 'consult');
  const tryOnAttrs = nanoAiGatewayButtonDataset(nanoPayload, 'try_on');

  const handleNanoAiConsult = useCallback(() => {
    void openConsultForProduct(product, {
      imageUrl: viewingImageUrl,
      source: 'product_detail_actions',
    });
  }, [openConsultForProduct, product, viewingImageUrl]);

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
    <div className="space-y-2 pt-3">
      <div className="flex flex-col sm:flex-row gap-2">
        <button
          type="button"
          {...consultAttrs}
          onClick={handleNanoAiConsult}
          className="flex-1 py-2.5 px-4 rounded-lg font-semibold text-sm border-2 border-[#ea580c] text-[#ea580c] bg-white hover:bg-orange-50 transition-colors"
        >
          Tư vấn nhắn tin
        </button>
        <button
          type="button"
          {...tryOnAttrs}
          onClick={handleNanoAiTryOn}
          className="flex-1 py-2.5 px-4 rounded-lg font-semibold text-sm bg-[#ea580c] text-white hover:bg-[#c2410c] transition-colors"
        >
          Thử đồ
        </button>
      </div>
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
        <span>
          {uiCartLoading ? 'Đang thêm...' : 'Thêm Vào Giỏ'}
        </span>
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
  );
}
