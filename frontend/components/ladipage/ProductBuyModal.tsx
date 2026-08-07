'use client';

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import type { Product } from '@/types/api';
import ProductVariantModal from '@/app/products/[slug]/components/ProductVariantModal/ProductVariantModal';
import { useCart } from '@/features/cart/hooks/useCart';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useToast } from '@/components/ToastProvider';
import { trackEvent } from '@/lib/analytics';
import { buildAddToCartRequestFromProduct, trackMarketingAddToCartIntent } from '@/lib/marketing-add-to-cart';
import {
  getActiveGoogleAutomatedDiscountToken,
  markGoogleAutomatedDiscountCartLock,
} from '@/lib/google-automated-discount';
import { buildAuthLoginHrefFromFullPath, getBrowserReturnLocation } from '@/lib/auth-redirect';
import { isClientAuthLikelyLoggedIn, probeCookieAuthSession } from '@/lib/client-auth-session';
import { queuePendingCartAfterLogin } from '@/features/cart/pending-cart-session';

interface ProductBuyModalProps {
  product: Product;
  isOpen: boolean;
  onClose: () => void;
  /** Nhãn nguồn cho analytics — vd `ladipage:{slug}`. */
  source?: string;
}

/**
 * Modal mua hàng dùng lại `ProductVariantModal` (giống trang chi tiết sản phẩm) cho từng thẻ
 * sản phẩm trong ladipage — hoạt động như nhau cho cả trường hợp 1 sản phẩm hoặc nhiều sản phẩm,
 * mỗi thẻ mở modal đúng cho sản phẩm của nó.
 */
export default function ProductBuyModal({ product, isOpen, onClose, source = 'ladipage' }: ProductBuyModalProps) {
  const router = useRouter();
  const { addToCart, isLoading: cartLoading } = useCart();
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const { pushToast } = useToast();
  const [displayStockByVariant, setDisplayStockByVariant] = useState<Record<string, number>>({});

  const ensureAuthenticated = useCallback(
    async (
      payload: ReturnType<typeof buildAddToCartRequestFromProduct>,
      intent: 'add' | 'buy',
    ): Promise<boolean> => {
      if (isClientAuthLikelyLoggedIn(isAuthenticated, authLoading)) return false;
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
      router.push(buildAuthLoginHrefFromFullPath(getBrowserReturnLocation()));
      trackEvent(intent === 'buy' ? 'buy_now' : 'add_to_cart_click', {
        product_id: payload.product_id,
        quantity: payload.quantity,
        status: 'requires_login',
        source,
      });
      return true;
    },
    [authLoading, isAuthenticated, pushToast, router, source],
  );

  const handleAddToCart = async (
    p: Product,
    quantity: number,
    selectedSize?: string,
    selectedColor?: string,
  ) => {
    const googlePv2Token = getActiveGoogleAutomatedDiscountToken(p.product_id);
    const payload = buildAddToCartRequestFromProduct(p, quantity, selectedSize, selectedColor, {
      google_pv2_token: googlePv2Token ?? undefined,
    });
    trackMarketingAddToCartIntent(payload);
    if (await ensureAuthenticated(payload, 'add')) return;
    try {
      await addToCart(payload);
      if (googlePv2Token && p.product_id) {
        markGoogleAutomatedDiscountCartLock(p.product_id);
      }
      trackEvent('add_to_cart_click', { product_id: p.id, quantity, source });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      pushToast({ title: 'Không thể thêm vào giỏ hàng', description: message, variant: 'error', durationMs: 3000 });
    }
  };

  const handleBuyNow = async (
    p: Product,
    quantity: number,
    selectedSize?: string,
    selectedColor?: string,
  ) => {
    const googlePv2Token = getActiveGoogleAutomatedDiscountToken(p.product_id);
    const payload = buildAddToCartRequestFromProduct(p, quantity, selectedSize, selectedColor, {
      google_pv2_token: googlePv2Token ?? undefined,
    });
    trackMarketingAddToCartIntent(payload);
    if (await ensureAuthenticated(payload, 'buy')) return;
    try {
      await addToCart(payload, { skipAddedPopup: true });
      if (googlePv2Token && p.product_id) {
        markGoogleAutomatedDiscountCartLock(p.product_id);
      }
      trackEvent('buy_now', { product_id: p.id, quantity, source });
      onClose();
      router.push('/cart');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      pushToast({ title: 'Không thể mua hàng', description: message, variant: 'error', durationMs: 3000 });
    }
  };

  return (
    <ProductVariantModal
      product={product}
      isOpen={isOpen}
      onClose={onClose}
      onAddToCart={handleAddToCart}
      onBuyNow={handleBuyNow}
      isCartLoading={cartLoading}
      action="both"
      displayStockByVariant={displayStockByVariant}
      setDisplayStockByVariant={setDisplayStockByVariant}
      overlayZClassName="z-[130]"
      closeAfterConfirm="add-only"
    />
  );
}
