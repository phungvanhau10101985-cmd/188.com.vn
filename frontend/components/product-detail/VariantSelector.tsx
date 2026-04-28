// frontend/components/product-detail/VariantSelector.tsx - FILE FIX
'use client';

import { ProductColor } from '@/types/api';

interface VariantSelectorProps {
  sizes: string[];
  colors: ProductColor[];
  selectedSize: string;
  selectedColor: string;
  onSizeChange: (size: string) => void;
  onColorChange: (color: string, colorImage?: string) => void;
}

export default function VariantSelector({
  sizes,
  colors,
  selectedSize,
  selectedColor,
  onSizeChange,
  onColorChange,
}: VariantSelectorProps) {
  if (sizes.length === 0 && colors.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      {/* Size Selector */}
      {sizes.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-900">Kích thước:</span>
            <button className="text-xs text-[#ea580c] hover:text-[#c2410c]">
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
        </div>
      )}

      {/* Color Selector */}
      {colors.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-900">Màu sắc và phân loại như ảnh:</span>
            <span className="text-xs text-gray-500">
              Đã chọn: <span className="font-medium text-gray-900">{selectedColor}</span>
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            {colors.map((color, index) => (
              <button
                key={index}
                onClick={() => onColorChange(color.name, color.img)}
                className={`flex items-center space-x-1.5 px-3 py-2 border-2 rounded-lg text-sm font-medium transition-all ${
                  selectedColor === color.name
                    ? 'border-orange-500 bg-orange-50 text-orange-700 shadow-sm'
                    : 'border-gray-300 text-gray-700 hover:border-gray-400 hover:shadow-sm'
                }`}
              >
                {color.img && (
                  <div 
                    className="w-6 h-6 rounded-full border border-gray-300"
                    style={{ 
                      backgroundImage: `url(${color.img})`,
                      backgroundSize: 'cover',
                      backgroundPosition: 'center'
                    }}
                  />
                )}
                <span>{color.name}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}