'use client';

import Image from 'next/image';
import type { Product } from '@/types/api';

interface DebugProps {
  products: Product[];
}

export default function DebugProducts({ products }: DebugProps) {
  console.log('🔍 DebugProducts - Received products:', products);
  
  if (!products || products.length === 0) {
    return <div className="p-8 text-red-500">❌ Không có sản phẩm</div>;
  }

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-4">188-COM-VN - {products.length} SẢN PHẨM</h1>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {products.map((product, index) => (
          <div key={product.id || index} className="bg-white rounded-lg shadow-md border border-gray-200 overflow-hidden">
            {/* Product Image */}
            {product.main_image && (
              <div className="relative w-full h-48">
                <Image 
                  src={product.main_image.startsWith('//') ? `https:${product.main_image}` : product.main_image}
                  alt={product.name}
                  fill
                  sizes="(min-width: 1024px) 25vw, (min-width: 768px) 50vw, 100vw"
                  className="object-cover"
                  onError={(e) => {
                    (e.currentTarget as HTMLImageElement).src = 'https://via.placeholder.com/300x300?text=No+Image';
                  }}
                />
              </div>
            )}
            
            {/* Product Info */}
            <div className="p-4">
              <h2 className="font-semibold text-gray-800 line-clamp-2 mb-2 min-h-[3rem]">
                {product.name}
              </h2>
              
              {/* Price */}
              <p className="text-red-600 font-bold text-xl mb-2">
                {product.price?.toLocaleString('vi-VN')}₫
              </p>
              
              {/* Stock */}
              <p className={`text-sm font-medium mb-2 ${
                (product.available || 0) > 0 ? 'text-green-600' : 'text-red-600'
              }`}>
                {(product.available || 0) > 0 ? '✅ Còn hàng' : '❌ Hết hàng'}
              </p>
              
              {/* Brand */}
              {product.brand_name && (
                <p className="text-sm text-gray-600 mb-1">🏷️ {product.brand_name}</p>
              )}
              
              {/* Add to Cart Button */}
              <button className="w-full bg-orange-500 hover:bg-orange-600 text-white py-2 px-4 rounded-lg font-medium transition-colors">
                🛒 Thêm vào giỏ
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
