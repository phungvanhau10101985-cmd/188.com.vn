// frontend/components/product-detail/ProductInfo.tsx - FILE FIX
'use client';

import { useState } from 'react';
import { Product } from '@/types/api';
import { formatPrice, getDiscountPercentage } from '@/lib/utils';
import VariantSelector from './VariantSelector';

interface ProductInfoProps {
  product: Product;
  onAddToCart: (product: Product, quantity: number, selectedSize?: string, selectedColor?: string) => void;
  onAddToFavorite: (product: Product) => void;
}

export default function ProductInfo({ product, onAddToCart, onAddToFavorite }: ProductInfoProps) {
  const [selectedSize, setSelectedSize] = useState<string>(product.sizes?.[0] || '');
  const [selectedColor, setSelectedColor] = useState<string>(product.colors?.[0]?.name || '');
  const [quantity, setQuantity] = useState(1);
  const [isFavorite, setIsFavorite] = useState(false);

  const available = (product.available || 0) > 0;
  const hasDiscount = product.original_price && product.original_price > product.price;

  const handleAddToCart = () => {
    onAddToCart(product, quantity, selectedSize, selectedColor);
  };

  const handleBuyNow = () => {
    onAddToCart(product, quantity, selectedSize, selectedColor);
    // Redirect to checkout page
    window.location.href = '/checkout';
  };

  const handleFavorite = () => {
    const newFavoriteState = !isFavorite;
    setIsFavorite(newFavoriteState);
    onAddToFavorite(product);
  };

  return (
    <div className="space-y-6">
      {/* Product Name */}
      <h1 className="text-2xl font-bold text-gray-900 leading-tight">
        {product.name}
      </h1>

      {/* Rating and Sales */}
      <div className="flex items-center space-x-6 text-sm text-gray-600">
        <div className="flex items-center space-x-2">
          <div className="flex items-center space-x-1">
            <span className="text-yellow-400 text-lg">★</span>
            <span className="font-semibold text-gray-900">{product.rating_point || 0}</span>
          </div>
          <span className="text-gray-500">({product.rating_total || 0} đánh giá)</span>
        </div>
        <div className="w-px h-4 bg-gray-300"></div>
        <span>{product.purchases || 0} đã bán</span>
        <div className="w-px h-4 bg-gray-300"></div>
        <span className={available ? 'text-green-600 font-medium' : 'text-red-600 font-medium'}>
          {available ? 'Còn hàng' : 'Hết hàng'}
        </span>
      </div>

      {/* Price Section */}
      <div className="bg-gradient-to-r from-blue-50 to-indigo-50 p-6 rounded-2xl border border-blue-100">
        <div className="flex items-baseline space-x-3 mb-2">
          <span className="text-3xl font-bold text-gray-900">
            {formatPrice(product.price)}
          </span>
          {hasDiscount && (
            <>
              <span className="text-lg text-gray-500 line-through">
                {formatPrice(product.original_price!)}
              </span>
              <span className="text-sm font-bold bg-red-500 text-white px-3 py-1 rounded-full">
                -{getDiscountPercentage(product.original_price!, product.price)}%
              </span>
            </>
          )}
        </div>
        
        {/* Benefits */}
        <div className="space-y-2 text-sm">
          <div className="flex items-center space-x-2 text-green-600 font-medium">
            <span>✓</span>
            <span>Miễn phí vận chuyển</span>
          </div>
          {product.price > 1000000 && (
            <div className="flex items-center space-x-2 text-blue-600 font-medium">
              <span>✓</span>
              <span>Trả góp 0% • {formatPrice(product.price / 6)}/tháng</span>
            </div>
          )}
        </div>
      </div>

      {/* Variant Selectors */}
      <VariantSelector
        sizes={product.sizes || []}
        colors={product.colors || []}
        selectedSize={selectedSize}
        selectedColor={selectedColor}
        onSizeChange={setSelectedSize}
        onColorChange={setSelectedColor}
      />

      {/* Quantity Selector */}
      <div className="border-t border-gray-200 pt-6">
        <div className="flex items-center justify-between mb-4">
          <span className="text-lg font-medium text-gray-900">Số lượng</span>
          <div className="flex items-center space-x-4">
            <button
              onClick={() => setQuantity(Math.max(1, quantity - 1))}
              disabled={quantity <= 1}
              className="w-10 h-10 border border-gray-300 rounded-xl flex items-center justify-center hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <span className="text-lg">-</span>
            </button>
            <span className="w-12 text-center text-lg font-bold">{quantity}</span>
            <button
              onClick={() => setQuantity(quantity + 1)}
              disabled={quantity >= (product.available || 0)}
              className="w-10 h-10 border border-gray-300 rounded-xl flex items-center justify-center hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <span className="text-lg">+</span>
            </button>
          </div>
        </div>
        <div className="text-sm text-gray-500">
          {product.available || 0} sản phẩm có sẵn
        </div>
      </div>

      {/* Action Buttons */}
      <div className="space-y-4 pt-6 border-t border-gray-200">
        <div className="flex space-x-4">
          <button
            onClick={handleAddToCart}
            disabled={!available}
            className={`flex-1 py-4 px-6 border-2 rounded-xl text-lg font-bold flex items-center justify-center space-x-3 transition-all ${
              available
                ? 'border-orange-500 text-orange-500 bg-white hover:bg-orange-50 hover:shadow-lg'
                : 'border-gray-300 text-gray-400 bg-gray-100 cursor-not-allowed'
            }`}
          >
            <span className="text-xl">🛒</span>
            <span>Thêm Vào Giỏ</span>
          </button>
          
          <button
            onClick={handleBuyNow}
            disabled={!available}
            className={`flex-1 py-4 px-6 rounded-xl text-lg font-bold text-white flex items-center justify-center space-x-3 transition-all ${
              available
                ? 'bg-gradient-to-r from-orange-500 to-red-500 hover:from-orange-600 hover:to-red-600 shadow-lg hover:shadow-xl'
                : 'bg-gray-400 cursor-not-allowed'
            }`}
          >
            <span>Mua Ngay</span>
          </button>
        </div>

        {/* Favorite Button */}
        <button
          onClick={handleFavorite}
          className={`w-full py-3 px-6 border rounded-xl font-medium flex items-center justify-center space-x-2 transition-all ${
            isFavorite
              ? 'border-red-300 bg-red-50 text-red-600 shadow-sm'
              : 'border-gray-300 text-gray-600 hover:border-red-300 hover:shadow-sm'
          }`}
        >
          <span className={`text-xl ${isFavorite ? 'text-red-500' : 'text-gray-500'}`}>
            {isFavorite ? '❤️' : '🤍'}
          </span>
          <span>{isFavorite ? 'Đã thích' : 'Thêm vào yêu thích'}</span>
          <span>({product.likes || 0})</span>
        </button>
      </div>

      {/* Quick Info */}
      <div className="grid grid-cols-2 gap-4 pt-6 border-t border-gray-200">
        <InfoItem icon="🚚" label="Giao hàng" value="Miễn phí" />
        <InfoItem icon="🔄" label="Đổi trả" value="7 ngày" />
        <InfoItem icon="🛡️" label="Bảo hành" value="Chính hãng" />
        <InfoItem icon="💳" label="Thanh toán" value="Đa dạng" />
      </div>
    </div>
  );
}

const InfoItem = ({ icon, label, value }: { icon: string; label: string; value: string }) => (
  <div className="flex items-center space-x-3 text-sm">
    <span className="text-2xl">{icon}</span>
    <div>
      <div className="text-gray-600">{label}</div>
      <div className="font-medium text-gray-900">{value}</div>
    </div>
  </div>
);