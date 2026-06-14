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

function isShopBrowsePath(pathname: string | null): boolean {
  if (!pathname) return false;
  const norm = pathname.replace(/\/$/, '') || '/';
  if (pathname.startsWith('/admin')) return false;
  if (pathname.startsWith('/auth')) return false;
  if (pathname.startsWith('/cart/add/')) return false;
  if (norm === '/luot-video-cung-shop') return false;
  return true;
}

/**
 * Giữ khung NanoAI không chặn click/cuộn shop (trang chủ, danh mục, PDP, giỏ…).
 * fullSuppress khi popup shop / auth / landing thêm giỏ từ chat.
 */
export default function NanoAiShopOverlayGuard() {
  const pathname = usePathname();
  const { showAddToCartPopup } = useCart();

  const isCartAddLandingPage = pathname?.startsWith('/cart/add/');
  const isCartPage = pathname === '/cart' || pathname === '/cart/';
  const isAuthPage = pathname?.startsWith('/auth/');
  const isShopBrowse = isShopBrowsePath(pathname);
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
    if (typeof window === 'undefined' || !isShopBrowse || shouldSuppress) return;

    const run = () => releaseNanoAiClickBlockers({ mode: 'passThrough' });
    run();

    const mo = new MutationObserver(run);
    mo.observe(document.body, { childList: true, subtree: true });
    window.addEventListener('188-site-embeds-ready', run);

    return () => {
      mo.disconnect();
      window.removeEventListener('188-site-embeds-ready', run);
    };
  }, [isShopBrowse, shouldSuppress]);

  useEffect(() => {
    if (isShopBrowse || shouldSuppress) return;
    clearNanoAiOverlayPassThrough();
  }, [isShopBrowse, shouldSuppress]);

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
