'use client';

import SizeGuideBody from './SizeGuideBody';

interface ProductSizeGuideModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Slug cat1 từ API `category_level1_slug`; cat2 chỉ khớp nếu nằm whitelist trong `category-size-guide-meta`. */
  categoryLevel1Slug?: string | null;
  categoryLevel2Slug?: string | null;
  /** Cao hơn overlay cha (ví dụ modal biến thể dùng z-50). */
  zClassName?: string;
}

export default function ProductSizeGuideModal({
  isOpen,
  onClose,
  categoryLevel1Slug,
  categoryLevel2Slug,
  zClassName = 'z-[200]',
}: ProductSizeGuideModalProps) {
  if (!isOpen) return null;

  return (
    <div
      className={`fixed inset-0 ${zClassName} flex items-center justify-center p-4 bg-black/50`}
      role="dialog"
      aria-modal="true"
      aria-labelledby="product-size-guide-heading"
      onClick={onClose}
    >
      <div
        className="relative bg-white rounded-lg max-w-[min(100vw-32px,540px)] max-h-[min(92vh,820px)] overflow-hidden shadow-xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between gap-2 px-4 py-2.5 border-b border-gray-100 bg-white flex-shrink-0">
          <span id="product-size-guide-heading" className="font-semibold text-sm text-gray-900">
            Hướng dẫn chọn size
          </span>
          <button
            type="button"
            aria-label="Đóng"
            className="p-1.5 rounded-lg text-gray-500 hover:bg-gray-100"
            onClick={onClose}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="overflow-y-auto flex-1 min-h-0 px-3 py-3">
          <SizeGuideBody
            categoryLevel1Slug={categoryLevel1Slug ?? ''}
            categoryLevel2Slug={categoryLevel2Slug}
          />
        </div>
      </div>
    </div>
  );
}
