// frontend/app/products/[slug]/components/ProductInfo/ProductActions.tsx - ĐÃ SỬA LỖI PROPS
'use client';

import { Product } from '@/types/api';

interface ProductActionsProps {
  product: Product;
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
  const canPurchase = available && !isCartLoading && variantsComplete;
  const blockHint = !variantsComplete ? variantSelectionHint : undefined;

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
    <div className="flex flex-col sm:flex-row gap-2 pt-3">
      <button
        type="button"
        onClick={handleAddToCart}
        disabled={!canPurchase}
        title={blockHint}
        className={`flex-1 py-3 px-4 rounded-lg font-semibold text-sm transition-all flex items-center justify-center space-x-2 group ${
          canPurchase
            ? 'bg-gray-500 hover:bg-gray-600 text-white shadow hover:shadow-md'
            : 'bg-gray-300 text-gray-500 cursor-not-allowed'
        } ${isCartLoading ? 'opacity-70' : ''}`}
      >
        <span className="text-base group-hover:scale-105 transition-transform">🛒</span>
        <span>
          {isCartLoading ? 'Đang thêm...' : 'Thêm Vào Giỏ'}
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
        } ${isCartLoading ? 'opacity-70' : ''}`}
      >
        {isCartLoading ? 'Đang xử lý...' : 'Mua ngay'}
      </button>
      
      <button
        onClick={handleToggleFavorite}
        disabled={isCartLoading}
        className={`w-11 h-11 border-2 rounded-lg flex items-center justify-center transition-all shrink-0 ${
          isCartLoading 
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
  );
}
