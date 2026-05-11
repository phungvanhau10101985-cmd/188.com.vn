// frontend/components/product-detail/VariantSelector.tsx - FILE FIX
'use client';

import { useState } from 'react';
import ProductSizeGuideModal from '@/components/category-size-guide/ProductSizeGuideModal';
import { ProductColor } from '@/types/api';
import { colorLabelForCart, colorEntryImageUrl } from '@/lib/product-color-variant';

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
}: VariantSelectorProps) {
  const [sizeGuideOpen, setSizeGuideOpen] = useState(false);

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
              const swatch = colorEntryImageUrl(color);
              return (
                <button
                  key={index}
                  type="button"
                  onClick={() => onColorChange(index, color.name, swatch || undefined)}
                  className={`flex items-center space-x-1.5 px-3 py-2 border-2 rounded-lg text-sm font-medium transition-all ${
                    selectedColorIndex === index
                      ? 'border-orange-500 bg-orange-50 text-orange-700 shadow-sm'
                      : 'border-gray-300 text-gray-700 hover:border-gray-400 hover:shadow-sm'
                  }`}
                >
                  {swatch ? (
                    <div
                      className="w-6 h-6 rounded-full border border-gray-300"
                      style={{
                        backgroundImage: `url(${swatch})`,
                        backgroundSize: 'cover',
                        backgroundPosition: 'center',
                      }}
                    />
                  ) : null}
                  <span>{colorLabelForCart(colors, index)}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
