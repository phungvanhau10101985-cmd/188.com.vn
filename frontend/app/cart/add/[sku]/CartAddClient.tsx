'use client';

import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import type { Product } from '@/types/api';
import ProductVariantModal from '@/app/products/[slug]/components/ProductVariantModal/ProductVariantModal';
import { useCart } from '@/features/cart/hooks/useCart';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useToast } from '@/components/ToastProvider';
import { trackEvent } from '@/lib/analytics';
import {
  buildAddToCartRequestFromProduct,
  trackMarketingAddToCartIntent,
} from '@/lib/marketing-add-to-cart';
import { buildAuthLoginHrefFromFullPath, getBrowserReturnLocation } from '@/lib/auth-redirect';
import { isClientAuthLikelyLoggedIn, probeCookieAuthSession } from '@/lib/client-auth-session';
import { queuePendingCartAfterLogin } from '@/features/cart/pending-cart-session';
import { productPathSlugFromApi } from '@/lib/product-path-slug';
import {
  clearNanoAiOverlayPassThrough,
  markNanoAiCheckoutOnCart,
  releaseNanoAiClickBlockers,
} from '@/lib/nanoai-overlay-pass-through';
import { parseCartAddCloseMode, type CartAddCloseMode } from '@/lib/cart-add-return';
import {
  returnToNanoAiChatWidget,
  markCartAddFromNanoAiFlow,
  clearCartAddFromNanoAiFlow,
} from '@/lib/nanoai-hosted-chat';

interface CartAddClientProps {
  product: Product;
  sku: string;
  closeMode: CartAddCloseMode;
  closePath?: string;
}

function buildCartPayload(
  p: Product,
  quantity: number,
  selectedSize?: string,
  selectedColor?: string,
) {
  return buildAddToCartRequestFromProduct(p, quantity, selectedSize, selectedColor);
}

export default function CartAddClient({ product, sku, closeMode, closePath }: CartAddClientProps) {
  const router = useRouter();
  const { addToCart, isLoading: cartLoading } = useCart();
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const { pushToast } = useToast();
  const [displayStockByVariant, setDisplayStockByVariant] = useState<Record<string, number>>({});

  const productHref = useMemo(() => {
    const seg = productPathSlugFromApi(product.slug, product.product_id) || product.product_id;
    return seg ? `/products/${encodeURIComponent(seg)}` : '/';
  }, [product.slug, product.product_id]);

  const handleClose = useCallback(() => {
    if (typeof window === 'undefined') {
      router.replace(productHref || '/');
      return;
    }

    if (closeMode === 'back' || closeMode === 'nanoai') {
      if (closeMode === 'nanoai') {
        markCartAddFromNanoAiFlow();
      }
      returnToNanoAiChatWidget();
      return;
    }

    if (closeMode === 'path' && closePath) {
      window.location.assign(closePath);
      return;
    }

    window.location.assign(productHref || '/');
  }, [router, productHref, closeMode, closePath]);

  useLayoutEffect(() => {
    if (closeMode === 'nanoai') {
      markCartAddFromNanoAiFlow();
    }
  }, [closeMode]);

  useEffect(() => {
    releaseNanoAiClickBlockers({ mode: 'fullSuppress' });
    const mo = new MutationObserver(() => releaseNanoAiClickBlockers({ mode: 'fullSuppress' }));
    mo.observe(document.body, { childList: true, subtree: true });
    return () => {
      mo.disconnect();
      if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/auth/')) {
        clearNanoAiOverlayPassThrough();
      }
    };
  }, []);

  const ensureAuthenticatedForCartAction = useCallback(
    async (payload: ReturnType<typeof buildCartPayload>, intent: 'add' | 'buy') => {
      if (isClientAuthLikelyLoggedIn(isAuthenticated, authLoading)) {
        return false;
      }
      if (authLoading) {
        pushToast({
          title: 'Đang kiểm tra đăng nhập',
          description: 'Vui lòng thử lại sau vài giây.',
          variant: 'info',
          durationMs: 2200,
        });
        return true;
      }

      const probed = await probeCookieAuthSession();
      if (probed?.user) {
        window.dispatchEvent(new Event('188-auth-session-changed'));
        return false;
      }

      queuePendingCartAfterLogin(payload);
      pushToast({
        title: intent === 'buy' ? 'Đăng nhập để mua hàng' : 'Đăng nhập để thêm giỏ',
        description: 'Sau đăng nhập bạn sẽ được chuyển tới giỏ hàng với sản phẩm đã chọn.',
        variant: 'info',
        durationMs: 3200,
      });
      router.push(buildAuthLoginHrefFromFullPath('/cart'));
      trackEvent(intent === 'buy' ? 'buy_now' : 'add_to_cart_click', {
        product_id: payload.product_id,
        quantity: payload.quantity,
        status: 'requires_login',
        source: 'cart_add_sku',
      });
      return true;
    },
    [authLoading, isAuthenticated, pushToast, router],
  );

  const handleAddToCart = async (
    p: Product,
    quantity: number,
    selectedSize?: string,
    selectedColor?: string,
  ) => {
    const payload = buildCartPayload(p, quantity, selectedSize, selectedColor);
    trackMarketingAddToCartIntent(payload);
    if (await ensureAuthenticatedForCartAction(payload, 'add')) return;
    try {
      await addToCart(payload, { skipAddedPopup: true });
      trackEvent('add_to_cart_click', { product_id: p.id, quantity, source: 'cart_add_sku' });
      if (closeMode === 'nanoai') {
        markNanoAiCheckoutOnCart();
        clearCartAddFromNanoAiFlow();
      }
      router.push('/cart');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      if (message.includes('Authentication required') || message.includes('401')) {
        pushToast({
          title: 'Vui lòng đăng nhập lại',
          description: 'Phiên đăng nhập đã hết hạn.',
          variant: 'info',
          durationMs: 2500,
        });
        router.push(buildAuthLoginHrefFromFullPath(getBrowserReturnLocation()));
      } else {
        pushToast({
          title: 'Không thể thêm vào giỏ hàng',
          description: message,
          variant: 'error',
          durationMs: 3000,
        });
      }
    }
  };

  const handleBuyNow = async (
    p: Product,
    quantity: number,
    selectedSize?: string,
    selectedColor?: string,
  ) => {
    const payload = buildCartPayload(p, quantity, selectedSize, selectedColor);
    if (await ensureAuthenticatedForCartAction(payload, 'buy')) return;
    try {
      await addToCart(payload, { skipAddedPopup: true });
      trackEvent('buy_now', { product_id: p.id, quantity, source: 'cart_add_sku' });
      if (closeMode === 'nanoai') {
        markNanoAiCheckoutOnCart();
        clearCartAddFromNanoAiFlow();
      }
      router.push('/cart');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      if (message.includes('Authentication required') || message.includes('401')) {
        pushToast({
          title: 'Vui lòng đăng nhập lại',
          description: 'Phiên đăng nhập đã hết hạn.',
          variant: 'info',
          durationMs: 2500,
        });
        router.push(buildAuthLoginHrefFromFullPath(getBrowserReturnLocation()));
      } else {
        pushToast({
          title: 'Không thể mua hàng',
          description: message,
          variant: 'error',
          durationMs: 3000,
        });
      }
    }
  };

  return (
    <>
      <ProductVariantModal
        product={product}
        isOpen
        onClose={handleClose}
        onAddToCart={handleAddToCart}
        onBuyNow={handleBuyNow}
        isCartLoading={cartLoading}
        action="both"
        displayStockByVariant={displayStockByVariant}
        setDisplayStockByVariant={setDisplayStockByVariant}
        overlayZClassName="z-[2147483646]"
        closeAfterConfirm={false}
      />
      <div className="sr-only" aria-live="polite">
        Chọn size, màu và số lượng cho sản phẩm {product.name} (SKU {sku}).
        {' '}
        <Link href={productHref}>Xem chi tiết sản phẩm</Link>
      </div>
    </>
  );
}
