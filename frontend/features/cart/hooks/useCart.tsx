// features/cart/hooks/useCart.tsx
'use client';

import { useState, useEffect, createContext, useContext, ReactNode, useRef } from 'react';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { cartAPI } from '../api/cart-api';
import { trackEvent } from '@/lib/analytics';
import { trackGoogleAdsAddToCart } from '@/lib/google-ads-gtag';
import { trackMetaAddToCart } from '@/lib/meta-pixel';
import { trackTikTokAddToCart } from '@/lib/tiktok-pixel';
import { CartRequiresLoginError } from '../cart-errors';
import { readPendingCartAfterLogin, clearPendingCartAfterLogin } from '../pending-cart-session';
import { hasClientAuthUser, hasClientBearerToken } from '@/lib/client-auth-session';
import type {
  AddToCartRequest,
  UpdateCartItemRequest,
  Cart,
  CartState,
  CartLineRef,
} from '../types/cart';

/** Tuỳ chọn khi thêm giỏ — ví dụ « Mua ngay » không hiện popup hỏi vào giỏ / mua tiếp. */
export type AddToCartOptions = {
  skipAddedPopup?: boolean;
};

interface CartContextType extends CartState {
  addToCart: (itemData: AddToCartRequest, options?: AddToCartOptions) => Promise<void>;
  updateCartItem: (lineRef: CartLineRef, updateData: UpdateCartItemRequest) => Promise<void>;
  removeFromCart: (lineRef: CartLineRef) => Promise<void>;
  clearCart: () => Promise<void>;
  refreshCart: () => Promise<void>;
  getCartItemCount: () => number;
  showAddToCartPopup: boolean;
  lastAddedItem: AddToCartRequest | null;
  hideAddToCartPopup: () => void;
}

const CartContext = createContext<CartContextType | undefined>(undefined);

const GUEST_CART_LEGACY_KEY = 'guest_cart';

function sortCartItemsNewestFirst<T extends { id?: number; updated_at?: string; created_at?: string; added_at?: string }>(
  items: T[],
): T[] {
  return [...items].sort((a, b) => {
    const ta = new Date(a.updated_at || a.created_at || a.added_at || 0).getTime();
    const tb = new Date(b.updated_at || b.created_at || b.added_at || 0).getTime();
    if (tb !== ta) return tb - ta;
    return Number(b.id ?? 0) - Number(a.id ?? 0);
  });
}

export function CartProvider({ children }: { children: ReactNode }) {
  const [cartState, setCartState] = useState<CartState>({
    cart: null,
    isLoading: true,
    error: null,
  });

  const { isAuthenticated } = useAuth();
  const [showAddToCartPopup, setShowAddToCartPopup] = useState(false);
  const [lastAddedItem, setLastAddedItem] = useState<AddToCartRequest | null>(null);
  const cartRef = useRef(cartState.cart);
  cartRef.current = cartState.cart;
  const cartMutationSeqRef = useRef(0);

  const discardLegacyGuestCart = () => {
    if (typeof window === 'undefined') return;
    try {
      localStorage.removeItem(GUEST_CART_LEGACY_KEY);
    } catch {
      /* ignore */
    }
  };

  const enrichCart = (cart: Awaited<ReturnType<typeof cartAPI.getCart>>) => {
    const normalizedCart = cart ? { ...cart, items: Array.isArray(cart.items) ? cart.items : [] } : null;
    const sortedItems = normalizedCart ? sortCartItemsNewestFirst(normalizedCart.items) : [];
    return normalizedCart
      ? {
          ...normalizedCart,
          items: sortedItems.map((item: any) => {
            let fromApi: Record<string, unknown> = {};
            const rawPd = item.product_data;
            if (rawPd && typeof rawPd === 'object') {
              fromApi = { ...rawPd };
            } else if (typeof rawPd === 'string' && rawPd.trim()) {
              try {
                const parsed = JSON.parse(rawPd);
                if (parsed && typeof parsed === 'object') fromApi = { ...parsed };
              } catch {
                /* ignore */
              }
            }
            const lineImage = String(
              item.line_image_url || fromApi.main_image || item.product_image || '',
            ).trim();
            return {
              ...item,
              product_image: lineImage || item.product_image,
              list_price: item.list_price ?? fromApi.list_price ?? fromApi.original_price,
              original_price: item.original_price ?? fromApi.original_price,
              product_data: {
                ...fromApi,
                id: item.product_id,
                product_id: fromApi.product_id ?? item.product_code,
                name: fromApi.name ?? item.product_name,
                list_price: item.list_price ?? fromApi.list_price ?? fromApi.original_price,
                original_price: item.original_price ?? fromApi.original_price,
                price: item.product_price ?? fromApi.price,
                main_image: lineImage,
                deposit_require: fromApi.deposit_require ?? item.requires_deposit,
              },
            };
          }),
        }
      : null;
  };

  const applyCartKeepingLineOrder = (nextCart: Cart | null, prevCart: Cart | null) => {
    if (!nextCart) return null;
    const enriched = enrichCart(nextCart);
    if (!enriched || !prevCart?.items?.length) return enriched;
    const incomingById = new Map(enriched.items.map((item) => [item.id, item]));
    const ordered: Cart['items'] = [];
    for (const old of prevCart.items) {
      const next = incomingById.get(old.id);
      if (next) {
        ordered.push(next);
        incomingById.delete(old.id);
      }
    }
    for (const rest of incomingById.values()) ordered.push(rest);
    return { ...enriched, items: ordered };
  };

  const refreshCart = async () => {
    if (!isAuthenticated) {
      discardLegacyGuestCart();
      setCartState((prev) => ({
        ...prev,
        cart: null,
        isLoading: false,
        error: null,
      }));
      return;
    }

    setCartState((prev) => ({
      ...prev,
      // Giữ giỏ đang hiện — không skeleton trắng khi đã có dữ liệu
      isLoading: prev.cart == null ? true : prev.isLoading,
      error: null,
    }));

    try {
      const cart = await cartAPI.getCart();
      setCartState((prev) => ({ ...prev, cart: enrichCart(cart), isLoading: false }));
    } catch (error: any) {
      console.error('Failed to fetch cart:', error);
      setCartState((prev) => ({
        ...prev,
        error: error.message || 'Failed to load cart',
        isLoading: false,
      }));
    }
  };

  const addToCart = async (itemData: AddToCartRequest, options?: AddToCartOptions) => {
    if (!isAuthenticated && !hasClientAuthUser() && !hasClientBearerToken()) {
      throw new CartRequiresLoginError();
    }

    setCartState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      await cartAPI.addToCart(itemData);
      await refreshCart();
      if (!options?.skipAddedPopup) {
        setLastAddedItem(itemData);
        setShowAddToCartPopup(true);
      }
      trackEvent('add_to_cart', {
        product_id: itemData.product_id,
        quantity: itemData.quantity,
        source: 'user',
      });
      /** Dự phòng nếu handler trang chưa gọi (dedupe 2s tránh double). */
      trackMetaAddToCart(itemData);
      trackTikTokAddToCart(itemData);
      trackGoogleAdsAddToCart(itemData);
    } catch (error: any) {
      setCartState((prev) => ({
        ...prev,
        error: error.message || 'Failed to add item to cart',
        isLoading: false,
      }));
      throw error;
    }
  };

  const updateCartItem = async (lineRef: CartLineRef, updateData: UpdateCartItemRequest) => {
    if (!isAuthenticated) return;

    const seq = ++cartMutationSeqRef.current;
    const snapshot = cartRef.current;

    if (typeof updateData.quantity === 'number') {
      setCartState((prev) => {
        if (!prev.cart) return { ...prev, error: null };
        const items = prev.cart.items.map((item) => {
          if (item.id !== lineRef.id) return item;
          const quantity = updateData.quantity;
          const unit = item.unit_price ?? item.product_price ?? 0;
          return { ...item, quantity, total_price: unit * quantity };
        });
        const total_items = items.reduce((sum, item) => sum + item.quantity, 0);
        return {
          ...prev,
          error: null,
          cart: { ...prev.cart, items, total_items },
        };
      });
    }

    try {
      await cartAPI.updateCartItem(lineRef.id, updateData);
      if (seq !== cartMutationSeqRef.current) return;
      const cart = await cartAPI.getCart();
      if (seq !== cartMutationSeqRef.current) return;
      setCartState((prev) => ({
        ...prev,
        cart: applyCartKeepingLineOrder(cart, prev.cart),
        isLoading: false,
        error: null,
      }));
    } catch (error: any) {
      if (seq !== cartMutationSeqRef.current) throw error;
      setCartState((prev) => ({
        ...prev,
        cart: snapshot ?? prev.cart,
        isLoading: false,
        error: error.message || 'Failed to update cart item',
      }));
      throw error;
    }
  };

  const removeFromCart = async (lineRef: CartLineRef) => {
    if (!isAuthenticated) return;

    const seq = ++cartMutationSeqRef.current;
    const snapshot = cartRef.current;

    setCartState((prev) => {
      if (!prev.cart) return { ...prev, error: null };
      const items = prev.cart.items.filter((item) => item.id !== lineRef.id);
      const total_items = items.reduce((sum, item) => sum + item.quantity, 0);
      return {
        ...prev,
        error: null,
        cart: { ...prev.cart, items, total_items },
      };
    });

    try {
      await cartAPI.removeFromCart(lineRef.id);
      if (seq !== cartMutationSeqRef.current) return;
      const cart = await cartAPI.getCart();
      if (seq !== cartMutationSeqRef.current) return;
      setCartState((prev) => ({
        ...prev,
        cart: applyCartKeepingLineOrder(cart, prev.cart),
        isLoading: false,
        error: null,
      }));
      trackEvent('remove_from_cart', { product_id: lineRef.product_id });
    } catch (error: any) {
      if (seq !== cartMutationSeqRef.current) throw error;
      setCartState((prev) => ({
        ...prev,
        cart: snapshot ?? prev.cart,
        isLoading: false,
        error: error.message || 'Failed to remove item from cart',
      }));
      throw error;
    }
  };

  const clearCart = async () => {
    if (!isAuthenticated) {
      discardLegacyGuestCart();
      setCartState((prev) => ({ ...prev, cart: null }));
      return;
    }

    setCartState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      await cartAPI.clearCart();
      setCartState((prev) => ({ ...prev, cart: null, isLoading: false }));
      trackEvent('clear_cart', { item_count: cartState.cart?.total_items ?? 0 });
    } catch (error: any) {
      setCartState((prev) => ({
        ...prev,
        error: error.message || 'Failed to clear cart',
        isLoading: false,
      }));
      throw error;
    }
  };

  const getCartItemCount = (): number => {
    if (!cartState.cart) return 0;
    return cartState.cart.total_items;
  };

  useEffect(() => {
    if (!isAuthenticated) {
      discardLegacyGuestCart();
      setCartState((prev) => ({
        ...prev,
        cart: null,
        isLoading: false,
        error: null,
      }));
      return;
    }

    let cancelled = false;

    const load = async () => {
      setCartState((prev) => ({ ...prev, isLoading: true, error: null }));
      try {
        const pending = readPendingCartAfterLogin();
        if (pending.length > 0) {
          for (const item of pending) {
            if (cancelled) return;
            await cartAPI.addToCart(item);
          }
          if (!cancelled) clearPendingCartAfterLogin();
        }
        if (cancelled) return;
        const cart = await cartAPI.getCart();
        if (cancelled) return;
        setCartState((prev) => ({
          ...prev,
          cart: enrichCart(cart),
          isLoading: false,
          error: null,
        }));
      } catch (error: any) {
        console.error('Failed to load cart:', error);
        if (!cancelled) {
          setCartState((prev) => ({
            ...prev,
            error: error.message || 'Failed to load cart',
            isLoading: false,
          }));
        }
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  const value: CartContextType = {
    ...cartState,
    addToCart,
    updateCartItem,
    removeFromCart,
    clearCart,
    refreshCart,
    getCartItemCount,
    showAddToCartPopup,
    lastAddedItem,
    hideAddToCartPopup: () => setShowAddToCartPopup(false),
  };

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart() {
  const context = useContext(CartContext);
  if (context === undefined) {
    throw new Error('useCart must be used within a CartProvider');
  }
  return context;
}
