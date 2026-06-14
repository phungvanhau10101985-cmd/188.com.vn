'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import Link from 'next/link';
import Image from 'next/image';
import { usePathname, useRouter } from 'next/navigation';
import { useCart } from '@/features/cart/hooks/useCart';
import { getOptimizedImage } from '@/lib/image-utils';
import { resolveCartItemImageUrl } from '@/lib/product-color-variant';
import {
  markNanoAiCheckoutOnCart,
  releaseNanoAiClickBlockers,
} from '@/lib/nanoai-overlay-pass-through';
import {
  clearCartAddFromNanoAiFlow,
  getNanoAiShopReturnPath,
  isCartAddFromNanoAiFlow,
} from '@/lib/nanoai-hosted-chat';

const POPUP_Z = 'z-[2147483646]';

export default function CartAddedPopup() {
  const router = useRouter();
  const pathname = usePathname();
  const { showAddToCartPopup, lastAddedItem, hideAddToCartPopup } = useCart();
  const [portalReady, setPortalReady] = useState(false);

  useEffect(() => {
    setPortalReady(true);
  }, []);

  useEffect(() => {
    if (!showAddToCartPopup) return;
    releaseNanoAiClickBlockers({ mode: 'fullSuppress' });
    const mo = new MutationObserver(() => releaseNanoAiClickBlockers({ mode: 'fullSuppress' }));
    mo.observe(document.body, { childList: true, subtree: true });

    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      mo.disconnect();
      document.body.style.overflow = prev;
      releaseNanoAiClickBlockers({ mode: 'passThrough' });
    };
  }, [showAddToCartPopup]);

  if (!showAddToCartPopup) return null;

  const name = lastAddedItem?.product_data?.name || 'Sản phẩm';
  const image = lastAddedItem
    ? getOptimizedImage(resolveCartItemImageUrl(lastAddedItem) || undefined, {
        width: 96,
        height: 96,
        fallbackStrategy: 'local',
      })
    : getOptimizedImage(undefined, { width: 96, height: 96, fallbackStrategy: 'local' });

  const finishPopup = (opts?: { keepCartCheckoutGuard?: boolean }) => {
    hideAddToCartPopup();
    if (opts?.keepCartCheckoutGuard) {
      markNanoAiCheckoutOnCart();
    }
    if (isCartAddFromNanoAiFlow()) {
      clearCartAddFromNanoAiFlow();
    }
  };

  const handleClose = () => {
    finishPopup({ keepCartCheckoutGuard: pathname === '/cart' || pathname === '/cart/' });
  };

  const handleContinueShopping = () => {
    const fromNanoAi = isCartAddFromNanoAiFlow();
    const returnPath = getNanoAiShopReturnPath();
    finishPopup();

    if (fromNanoAi) {
      const dest =
        returnPath && returnPath !== '/cart' && !returnPath.startsWith('/cart/add/')
          ? returnPath
          : '/';
      router.push(dest);
      return;
    }

    if (typeof window !== 'undefined' && window.history.length > 1) {
      router.back();
      return;
    }
    router.push('/');
  };

  const handleViewCart = () => {
    markNanoAiCheckoutOnCart();
    clearCartAddFromNanoAiFlow();
    hideAddToCartPopup();
  };

  const modal = (
    <div
      data-188-cart-added-popup
      className={`fixed inset-0 ${POPUP_Z} isolate flex items-center justify-center p-4`}
      role="dialog"
      aria-modal="true"
      aria-labelledby="cart-added-popup-title"
    >
      <div
        className="absolute inset-0 z-0 bg-black/50"
        onClick={handleClose}
        aria-hidden
      />
      <div
        className="relative z-10 w-full max-w-md md:max-w-lg max-h-[calc(100dvh-2rem)] overflow-auto rounded-xl bg-white shadow-2xl touch-manipulation"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 p-3 md:p-4 border-b border-gray-100">
          <div className="h-12 w-12 rounded bg-gray-100 overflow-hidden flex-shrink-0">
            <Image src={image} alt={name} width={48} height={48} className="h-12 w-12 object-cover" draggable={false} />
          </div>
          <div className="flex-1 min-w-0">
            <p id="cart-added-popup-title" className="text-sm md:text-base font-semibold text-gray-900 truncate">
              Đã thêm vào giỏ hàng
            </p>
            <p className="text-xs md:text-sm text-gray-600 truncate">{name}</p>
          </div>
          <button
            type="button"
            onClick={handleClose}
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
            onClick={handleViewCart}
            className="w-full sm:w-1/2 inline-flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg font-semibold text-sm bg-[#ea580c] text-white hover:bg-[#c2410c] transition-colors"
          >
            <span aria-hidden>🛒</span>
            <span>Vào giỏ hàng</span>
          </Link>
          <button
            type="button"
            onClick={handleContinueShopping}
            className="w-full sm:w-1/2 inline-flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg font-semibold text-sm bg-gray-100 text-gray-800 hover:bg-gray-200 transition-colors"
          >
            <span aria-hidden>🛍️</span>
            <span>Mua sắm tiếp</span>
          </button>
        </div>
      </div>
    </div>
  );

  if (!portalReady || typeof document === 'undefined') return null;
  return createPortal(modal, document.body);
}
