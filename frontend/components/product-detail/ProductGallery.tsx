// frontend/components/product-detail/ProductGallery.tsx - FILE FIX
'use client';

import { useState } from 'react';
import { cdnUrl } from '@/lib/cdn-url';
import Image from 'next/image';
import { Product } from '@/types/api';
import { getProductMainImage } from '@/lib/utils';

interface ProductGalleryProps {
  product: Product;
}

export default function ProductGallery({ product }: ProductGalleryProps) {
  const [selectedImage, setSelectedImage] = useState(0);
  
  const mainImage = getProductMainImage(product);
  const galleryImages = product.gallery || product.images || [mainImage];

  return (
    <div className="space-y-4">
      {/* Main Image */}
      <div className="aspect-square bg-gray-100 rounded-2xl overflow-hidden border border-gray-200 relative">
        <Image
          src={galleryImages[selectedImage] || mainImage}
          alt={product.name}
          fill
          sizes="(min-width: 1024px) 40vw, 90vw"
          className="object-cover hover:scale-105 transition-transform duration-300"
          onError={(e) => {
            (e.currentTarget as HTMLImageElement).src = cdnUrl('/images/placeholder.jpg');
          }}
        />
      </div>

      {/* Thumbnail Gallery */}
      {galleryImages.length > 1 && (
        <div className="flex space-x-3 overflow-x-auto pb-2">
          {galleryImages.map((image, index) => (
            <button
              key={index}
              onClick={() => setSelectedImage(index)}
              className={`flex-shrink-0 w-20 h-20 rounded-lg border-2 overflow-hidden transition-all ${
                selectedImage === index
                  ? 'border-orange-500 ring-2 ring-orange-200'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <div className="relative w-full h-full">
                <Image
                  src={image}
                  alt={`${product.name} - ${index + 1}`}
                  fill
                  sizes="80px"
                  className="object-cover"
                  onError={(e) => {
                    (e.currentTarget as HTMLImageElement).src = cdnUrl('/images/placeholder.jpg');
                  }}
                />
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Product Badges */}
      <div className="flex flex-wrap gap-2">
        {product.original_price && product.original_price > product.price && (
          <span className="bg-red-500 text-white px-3 py-1 rounded-full text-sm font-medium">
            -{Math.round(((product.original_price - product.price) / product.original_price) * 100)}%
          </span>
        )}
        {product.rating_point && product.rating_point >= 4.5 && (
          <span className="bg-yellow-500 text-white px-3 py-1 rounded-full text-sm font-medium">
            ⭐ {product.rating_point}
          </span>
        )}
        {product.purchases && product.purchases > 1000 && (
          <span className="bg-green-500 text-white px-3 py-1 rounded-full text-sm font-medium">
            🔥 {product.purchases.toLocaleString()}+ đã bán
          </span>
        )}
      </div>
    </div>
  );
}
