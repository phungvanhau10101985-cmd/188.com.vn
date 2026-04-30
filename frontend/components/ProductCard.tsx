// frontend/components/ProductCard.tsx - FIXED VERSION
'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useState } from 'react';
import { Product } from '@/types/api';
import { formatPrice, getDiscountPercentage, truncateText } from '@/lib/utils';
import { getOptimizedImage } from '@/lib/image-utils';

interface ProductCardProps {
  product: Product;
  onAddToCart?: (product: Product) => void;
  onAddToFavorite?: (product: Product) => void;
  onQuickView?: (product: Product) => void;
  size?: 'small' | 'medium' | 'large';
}

// Helper functions - ĐƯA LÊN ĐẦU ĐỂ TRÁNH LỖI HOISTING
const getImageSize = (size: string) => {
  switch (size) {
    case 'small':
      return { width: 200, height: 200 };
    case 'large':
      return { width: 400, height: 400 };
    case 'medium':
    default:
      return { width: 300, height: 300 };
  }
};

// CSS classes theo size
const getSizeClasses = (size: string) => {
  switch (size) {
    case 'small':
      return {
        container: 'p-2',
        image: 'aspect-square',
        name: 'text-xs min-h-[1.5rem]',
        price: 'text-sm',
        button: 'py-1 px-2 text-xs'
      };
    case 'large':
      return {
        container: 'p-4',
        image: 'aspect-square',
        name: 'text-base min-h-[2.5rem]',
        price: 'text-lg',
        button: 'py-3 px-4 text-base'
      };
    case 'medium':
    default:
      return {
        container: 'p-3',
        image: 'aspect-square',
        name: 'text-sm min-h-[2rem]',
        price: 'text-base',
        button: 'py-2 px-3 text-sm'
      };
  }
};

export default function ProductCard({ 
  product, 
  onAddToCart, 
  onAddToFavorite, 
  onQuickView,
  size = 'medium'
}: ProductCardProps) {
  const [imageError, setImageError] = useState(false);
  const [imageLoading, setImageLoading] = useState(true);
  
  const available = (product.available || 0) > 0;
  const hasDiscount = product.original_price && product.original_price > product.price;
  
  // Sử dụng image utils với kích thước tối ưu
  const imageUrl = getOptimizedImage(product.main_image, {
    width: getImageSize(size).width,
    height: getImageSize(size).height,
    quality: 85,
    fallbackStrategy: 'local'
  });

  // Tạo blur placeholder từ image utils
  const blurDataUrl = getOptimizedImage(undefined, { 
    width: 20, 
    height: 20 
  });

  const handleImageError = () => {
    setImageError(true);
    setImageLoading(false);
  };

  const handleImageLoad = () => {
    setImageLoading(false);
  };

  const handleAddToCart = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onAddToCart?.(product);
  };

  const handleAddToFavorite = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onAddToFavorite?.(product);
  };

  const handleQuickView = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onQuickView?.(product);
  };

  const sizeClasses = getSizeClasses(size);

  const productSlug = product.slug || product.product_id || (product.id != null ? String(product.id) : '');
  const productHref = productSlug ? `/products/${productSlug}` : '#';

  return (
    <div className={`product-card group bg-white rounded-xl border border-gray-100 shadow-sm hover:shadow-lg hover:border-orange-200 overflow-hidden ${sizeClasses.container}`}>
      {/* Image Section */}
      <div className={`relative overflow-hidden bg-gray-50 rounded-t-xl ${sizeClasses.image}`}>
        <Link href={productHref}>
          {!imageError ? (
            <>
              {imageLoading && (
                <div className="absolute inset-0 bg-gray-200 animate-pulse flex items-center justify-center">
                  <div className="text-gray-400 text-xs">Đang tải...</div>
                </div>
              )}
              <Image
                src={imageUrl}
                alt={product.name}
                fill
                className={`object-cover group-hover:scale-105 transition-transform duration-300 ${
                  imageLoading ? 'opacity-0' : 'opacity-100'
                }`}
                onError={handleImageError}
                onLoad={handleImageLoad}
                sizes="(max-width: 768px) 50vw, (max-width: 1200px) 33vw, 25vw"
                placeholder="blur"
                blurDataURL={blurDataUrl}
                priority={false}
              />
            </>
          ) : (
            <div className="w-full h-full flex items-center justify-center bg-gray-200">
              <div className="text-center text-gray-500">
                <div className="text-xl mb-1">📦</div>
                <div className="text-xs">Không có hình ảnh</div>
              </div>
            </div>
          )}
        </Link>

        {/* Discount Badge */}
        {hasDiscount && !imageError && (
          <div className="absolute top-2 left-2 bg-red-500 text-white px-1.5 py-0.5 rounded-full text-xs font-bold shadow-md">
            -{getDiscountPercentage(product.original_price!, product.price)}%
          </div>
        )}

        {/* Action Buttons */}
        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity duration-300 space-y-1">
          <button
            onClick={handleQuickView}
            className="bg-white p-1.5 rounded-full shadow-md hover:bg-gray-50 transition-colors hover:scale-110 transform text-xs"
            title="Xem nhanh"
          >
            👁️
          </button>
          <button
            onClick={handleAddToFavorite}
            className="bg-white p-1.5 rounded-full shadow-md hover:bg-gray-50 transition-colors hover:scale-110 transform text-xs"
            title="Thêm vào yêu thích"
          >
            ❤️
          </button>
        </div>

        {/* Out of Stock Overlay */}
        {!available && (
          <div className="absolute inset-0 bg-black bg-opacity-40 flex items-center justify-center">
            <span className="bg-white px-2 py-1 rounded text-xs font-medium text-gray-900">
              Hết hàng
            </span>
          </div>
        )}
      </div>

      {/* Product Info */}
      <div className="space-y-2">
        {/* Brand */}
        {product.brand_name && (
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded">
              {truncateText(product.brand_name, 12)}
            </span>
            <div className="flex items-center text-xs text-gray-500">
              <span className="text-yellow-400">★</span>
              <span className="mx-0.5">{product.rating_point || 0}</span>
              <span>({product.rating_total || 0})</span>
            </div>
          </div>
        )}

        {/* Product Name */}
        <Link href={productHref}>
          <h3 className={`font-medium text-gray-900 leading-tight line-clamp-2 hover:text-orange-500 transition-colors cursor-pointer ${sizeClasses.name}`}>
            {truncateText(product.name, size === 'small' ? 40 : 50)}
          </h3>
        </Link>

        {/* Price */}
        <div className="space-y-1">
          <div className="flex items-baseline space-x-1">
            <span className={`font-bold text-red-600 ${sizeClasses.price}`}>
              {formatPrice(product.price)}
            </span>
            {hasDiscount && (
              <span className="text-xs text-gray-500 line-through">
                {formatPrice(product.original_price!)}
              </span>
            )}
          </div>
          
          {/* Installment */}
          {product.price && product.price > 1000000 && (
            <div className="text-xs text-green-600 font-medium">
              Trả góp 0% • {formatPrice(product.price / 6)}/tháng
            </div>
          )}
        </div>

        {/* Stats */}
        <div className="flex justify-between items-center text-xs text-gray-500">
          <span>Đã bán: {product.purchases || 0}</span>
          <span className={`font-medium ${available ? 'text-green-600' : 'text-red-600'}`}>
            {available ? 'Còn hàng' : 'Hết hàng'}
          </span>
        </div>

        {/* Add to Cart Button - nút phụ màu xám (theme 188) */}
        <button 
          onClick={handleAddToCart}
          disabled={!available}
          className={`w-full rounded font-medium transition-all flex items-center justify-center space-x-1 ${
            available 
              ? 'bg-gray-500 hover:bg-gray-600 text-white shadow-sm hover:shadow-md' 
              : 'bg-gray-300 text-gray-500 cursor-not-allowed'
          } ${sizeClasses.button}`}
        >
          <span>🛒</span>
          <span>{available ? 'Thêm vào giỏ' : 'Hết hàng'}</span>
        </button>
      </div>
    </div>
  );
}

// Optimized Product Card cho ProductGrid (không có quick actions)
export const SimpleProductCard = ({ 
  product, 
  onFavorite,
  isFavorited = false,
  /** Ưu tiên tải ảnh đầu trang — cải thiện LCP (PSI) */
  priority = false,
}: { 
  product: Product;
  onFavorite: (productId: number, e: React.MouseEvent) => void | Promise<void>;
  /** Trạng thái thích từ server (khách + đăng nhập); mặc định false */
  isFavorited?: boolean;
  priority?: boolean;
}) => {
  const [imageError, setImageError] = useState(false);
  
  const imageUrl = getOptimizedImage(product.main_image, {
    width: 250,
    height: 250,
    quality: 80,
    fallbackStrategy: 'local'
  });
  const blurDataUrl = getOptimizedImage(undefined, { width: 20, height: 20 });

  const handleFavorite = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    void onFavorite(product.id, e);
  };

  const handleImageError = () => {
    setImageError(true);
  };

  return (
    <Link 
      href={product.slug || product.product_id ? `/products/${product.slug || product.product_id}` : `/products/${product.id}`}
      className="product-card group bg-white rounded-xl border border-gray-100 shadow-sm hover:shadow-lg hover:border-orange-200 overflow-hidden transition-all block"
    >
      {/* Image Container */}
      <div className="relative aspect-square bg-gray-50 overflow-hidden rounded-t-xl">
        {!imageError ? (
          <Image
            src={imageUrl}
            alt={product.name}
            fill
            className="object-cover group-hover:scale-105 transition-transform duration-300"
            onError={handleImageError}
            sizes="(max-width: 768px) 50vw, 25vw"
            priority={priority}
            placeholder="blur"
            blurDataURL={blurDataUrl}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gray-200">
            <span className="text-gray-400 text-xs">No Image</span>
          </div>
        )}

        {/* Favorite Button */}
        <button
          type="button"
          onClick={handleFavorite}
          className={`absolute top-1 right-1 min-w-[44px] min-h-[44px] w-11 h-11 -mt-1 -mr-1 rounded-full flex items-center justify-center text-xs transition-all ${
            isFavorited
              ? 'bg-red-500 text-white shadow'
              : 'bg-white bg-opacity-90 text-gray-600 hover:bg-red-500 hover:text-white'
          }`}
          aria-label={isFavorited ? 'Bỏ yêu thích' : 'Thêm yêu thích'}
        >
          {isFavorited ? '❤️' : '🤍'}
        </button>
      </div>

      {/* Product Info */}
      <div className="p-2">
        {/* Product Name */}
        <h3 className="font-medium text-gray-900 text-xs mb-1 line-clamp-2 leading-tight group-hover:text-orange-600 transition-colors min-h-[2rem]">
          {truncateText(product.name, 45)}
        </h3>

        {/* Price */}
        <div className="flex items-baseline space-x-1 mb-1">
          <span className="text-sm font-bold text-gray-900">
            {formatPrice(product.price)}
          </span>
        </div>

        {/* Stats */}
        <div className="flex justify-between items-center text-xs text-gray-500">
          <span>★ {product.rating_point?.toFixed(1) || '0.0'}</span>
          <span>Đã bán: {product.purchases || 0}</span>
        </div>
      </div>
    </Link>
  );
};