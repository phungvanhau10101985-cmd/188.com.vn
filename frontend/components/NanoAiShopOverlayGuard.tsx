'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { useCart } from '@/features/cart/hooks/useCart';
import {
  clearNanoAiCheckoutOnCart,
  clearNanoAiOverlayPassThrough,
  isNanoAiCheckoutOnCart,
  releaseNanoAiClickBlockers,
} from '@/lib/nanoai-overlay-pass-through';

/**
 * Giữ khung NanoAI không chặn click/cuộn khi popup shop hoặc trang giỏ (sau luồng chat) đang active.
 */
export default function NanoAiShopOverlayGuard() {
  const pathname = usePathname();
  const { showAddToCartPopup } = useCart();

  const isCartAddLandingPage = pathname?.startsWith('/cart/add/');
  const isCartPage = pathname === '/cart' || pathname === '/cart/';
  const shouldSuppress =
    showAddToCartPopup ||
    isCartAddLandingPage ||
    (isCartPage && isNanoAiCheckoutOnCart());

  useEffect(() => {
    if (typeof window === 'undefined' || !shouldSuppress) return;

    const run = () => releaseNanoAiClickBlockers({ mode: 'fullSuppress' });
    run();

    const mo = new MutationObserver(run);
    mo.observe(document.body, { childList: true, subtree: true });

    return () => {
      mo.disconnect();
    };
  }, [shouldSuppress]);

  useEffect(() => {
    if (shouldSuppress) return;
    clearNanoAiOverlayPassThrough();
  }, [shouldSuppress]);

  useEffect(() => {
    if (isCartPage) return;
    if (isNanoAiCheckoutOnCart()) {
      clearNanoAiCheckoutOnCart();
    }
  }, [isCartPage]);

  return null;
}
