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
import { clearNanoAiCartFlowState, isCartAddFromNanoAiFlow } from '@/lib/nanoai-hosted-chat';

/**
 * Giữ khung NanoAI không chặn click/cuộn khi popup shop hoặc trang giỏ (sau luồng chat) đang active.
 */
export default function NanoAiShopOverlayGuard() {
  const pathname = usePathname();
  const { showAddToCartPopup } = useCart();

  const isCartAddLandingPage = pathname?.startsWith('/cart/add/');
  const isCartPage = pathname === '/cart' || pathname === '/cart/';
  const isAuthPage = pathname?.startsWith('/auth/');
  const isProductDetailPage = Boolean(pathname?.match(/^\/products\/[^/]+$/));
  const shouldSuppress =
    showAddToCartPopup ||
    isCartAddLandingPage ||
    isAuthPage ||
    (isCartPage && (isNanoAiCheckoutOnCart() || isCartAddFromNanoAiFlow()));

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
    if (typeof document === 'undefined') return;
    if (isProductDetailPage && !shouldSuppress) {
      document.documentElement.setAttribute('data-nanoai188-pdp-pass', '1');
    } else {
      document.documentElement.removeAttribute('data-nanoai188-pdp-pass');
    }
    return () => {
      document.documentElement.removeAttribute('data-nanoai188-pdp-pass');
    };
  }, [isProductDetailPage, shouldSuppress]);

  useEffect(() => {
    if (typeof window === 'undefined' || !isProductDetailPage || shouldSuppress) return;

    const run = () => releaseNanoAiClickBlockers({ mode: 'passThrough' });
    run();

    const mo = new MutationObserver(run);
    mo.observe(document.body, { childList: true, subtree: true });

    return () => {
      mo.disconnect();
    };
  }, [isProductDetailPage, shouldSuppress]);

  useEffect(() => {
    if (shouldSuppress || isProductDetailPage) return;
    clearNanoAiOverlayPassThrough();
  }, [shouldSuppress, isProductDetailPage]);

  useEffect(() => {
    if (isCartPage) return;
    if (isNanoAiCheckoutOnCart()) {
      clearNanoAiCheckoutOnCart();
    }
  }, [isCartPage, pathname]);

  useEffect(() => {
    if (pathname !== '/cart' && pathname !== '/cart/') return;
    return () => {
      clearNanoAiCartFlowState();
    };
  }, [pathname]);

  return null;
}
