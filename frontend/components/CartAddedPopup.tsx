'use client';

import Link from 'next/link';
import Image from 'next/image';
import { useCart } from '@/features/cart/hooks/useCart';

export default function CartAddedPopup() {
  const { showAddToCartPopup, lastAddedItem, hideAddToCartPopup } = useCart();

  if (!showAddToCartPopup) return null;

  const name = lastAddedItem?.product_data?.name || 'Sản phẩm';
  const image = lastAddedItem?.product_data?.main_image || '';

  return (
    <div className="fixed inset-0 z-[60] flex items-end md:items-center justify-center p-3 md:p-4 bg-black/40" role="dialog" aria-modal="true" onClick={hideAddToCartPopup}>
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md md:max-w-lg" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 p-3 md:p-4 border-b border-gray-100">
          <div className="h-12 w-12 rounded bg-gray-100 overflow-hidden flex-shrink-0">
            {image ? (
              <Image src={image} alt={name} width={48} height={48} className="h-12 w-12 object-cover" />
            ) : (
              <div className="h-full w-full bg-gray-200" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm md:text-base font-semibold text-gray-900 truncate">Đã thêm vào giỏ hàng</p>
            <p className="text-xs md:text-sm text-gray-600 truncate">{name}</p>
          </div>
          <button
            type="button"
            onClick={hideAddToCartPopup}
            className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-700 transition"
            aria-label="Đóng"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 md:h-6 md:w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="p-3 md:p-4 flex flex-col sm:flex-row gap-2">
          <Link
            href="/cart"
            onClick={() => hideAddToCartPopup()}
            className="w-full sm:w-1/2 inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg font-semibold text-sm bg-[#ea580c] text-white hover:bg-[#c2410c] transition-colors"
          >
            <span>🛒</span>
            <span>Vào giỏ hàng</span>
          </Link>
          <button
            type="button"
            onClick={() => {
              hideAddToCartPopup();
            }}
            className="w-full sm:w-1/2 inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg font-semibold text-sm bg-gray-100 text-gray-800 hover:bg-gray-200 transition-colors"
          >
            <span>🛍️</span>
            <span>Mua sắm tiếp</span>
          </button>
        </div>
      </div>
    </div>
  );
}
