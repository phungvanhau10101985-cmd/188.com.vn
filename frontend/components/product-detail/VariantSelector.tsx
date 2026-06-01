// frontend/components/product-detail/VariantSelector.tsx - FILE FIX
'use client';

import { useState } from 'react';
import Image from 'next/image';
import ProductSizeGuideModal from '@/components/category-size-guide/ProductSizeGuideModal';
import { ProductColor } from '@/types/api';
import {
  colorLabelForCart,
  resolveColorSwatchImageUrl,
  type ColorSwatchProductRef,
} from '@/lib/product-color-variant';
import { getOptimizedImage } from '@/lib/image-utils';

interface VariantSelectorProps {
  sizes: string[];
  colors: ProductColor[];
  selectedSize: string;
  /** Chỉ số trong `colors`; -1 = chưa chọn. */
  selectedColorIndex: number;
  onSizeChange: (size: string) => void;
  onColorChange: (colorIndex: number, colorName: string, colorImage?: string) => void;
  /** Slug danh mục cấp 1 — mở popup hướng dẫn (API `category_level1_slug`). */
  categoryLevel1Slug?: string | null;
  /** Segment cấp 2 khi có whitelist override (API `category_level2_slug`). */
  categoryLevel2Slug?: string | null;
  /** Ngữ cảnh SP để lấy ảnh màu từ gallery / color_image_urls khi entry thiếu `img`. */
  colorImageContext?: ColorSwatchProductRef;
}

export default function VariantSelector({
  sizes,
  colors,
  selectedSize,
  selectedColorIndex,
  onSizeChange,
  onColorChange,
  categoryLevel1Slug,
  categoryLevel2Slug,
  colorImageContext,
}: VariantSelectorProps) {
  const [sizeGuideOpen, setSizeGuideOpen] = useState(false);

  const swatchProduct: ColorSwatchProductRef = {
    colors,
    color_image_urls: colorImageContext?.color_image_urls,
    color_variants: colorImageContext?.color_variants,
    images: colorImageContext?.images,
    gallery: colorImageContext?.gallery,
    main_image: colorImageContext?.main_image,
  };

  if (sizes.length === 0 && colors.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      {sizes.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-900">Kích thước:</span>
            <button
              type="button"
              className="text-xs text-[#ea580c] hover:text-[#c2410c]"
              onClick={() => setSizeGuideOpen(true)}
            >
              Hướng dẫn chọn size
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {sizes.map((size) => (
              <button
                key={size}
                onClick={() => onSizeChange(size)}
                className={`min-w-10 px-3 py-2 border-2 rounded-lg text-sm font-medium transition-all ${
                  selectedSize === size
                    ? 'border-orange-500 bg-orange-50 text-orange-700 shadow-sm'
                    : 'border-gray-300 text-gray-700 hover:border-gray-400 hover:shadow-sm'
                }`}
              >
                {size}
              </button>
            ))}
          </div>

          <ProductSizeGuideModal
            isOpen={sizeGuideOpen}
            onClose={() => setSizeGuideOpen(false)}
            categoryLevel1Slug={categoryLevel1Slug}
            categoryLevel2Slug={categoryLevel2Slug}
          />
        </div>
      )}

      {colors.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-900">Màu sắc và phân loại như ảnh:</span>
            <span className="text-xs text-gray-500">
              Đã chọn:{' '}
              <span className="font-medium text-gray-900">
                {selectedColorIndex >= 0 && colors[selectedColorIndex]
                  ? colorLabelForCart(colors, selectedColorIndex)
                  : '—'}
              </span>
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            {colors.map((color, index) => {
              const swatch = resolveColorSwatchImageUrl(swatchProduct, index);
              const label = colorLabelForCart(colors, index);
              return (
                <button
                  key={index}
                  type="button"
                  onClick={() => onColorChange(index, color.name, swatch || undefined)}
                  className={`flex items-center gap-2 px-2 py-1.5 border-2 rounded-lg text-sm font-medium transition-all ${
                    selectedColorIndex === index
                      ? 'border-orange-500 bg-orange-50 text-orange-700 shadow-sm'
                      : 'border-gray-300 text-gray-700 hover:border-gray-400 hover:shadow-sm'
                  }`}
                >
                  <div className="w-10 h-10 rounded-lg overflow-hidden flex-shrink-0 border border-gray-200 bg-gray-100 relative">
                    {swatch ? (
                      <Image
                        src={getOptimizedImage(swatch, { width: 80, height: 80, hideProductPng: true })}
                        alt={label}
                        width={40}
                        height={40}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full bg-gray-200" aria-hidden />
                    )}
                  </div>
                  <span className="text-left leading-snug">{label}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
