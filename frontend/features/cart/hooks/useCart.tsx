// features/cart/hooks/useCart.tsx
'use client';

import { useState, useEffect, createContext, useContext, ReactNode } from 'react';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { cartAPI } from '../api/cart-api';
import { trackEvent } from '@/lib/analytics';
import { CartRequiresLoginError } from '../cart-errors';
import type {
  Cart,
  AddToCartRequest,
  UpdateCartItemRequest,
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

export function CartProvider({ children }: { children: ReactNode }) {
  const [cartState, setCartState] = useState<CartState>({
    cart: null,
    isLoading: false,
    error: null,
  });

  const { isAuthenticated } = useAuth();
  const [showAddToCartPopup, setShowAddToCartPopup] = useState(false);
  const [lastAddedItem, setLastAddedItem] = useState<AddToCartRequest | null>(null);

  const discardLegacyGuestCart = () => {
    if (typeof window === 'undefined') return;
    try {
      localStorage.removeItem(GUEST_CART_LEGACY_KEY);
    } catch {
      /* ignore */
    }
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

    setCartState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      const cart = await cartAPI.getCart();
      const normalizedCart = cart ? { ...cart, items: Array.isArray(cart.items) ? cart.items : [] } : null;
      const sortedItems = normalizedCart
        ? [...normalizedCart.items].sort((a: any, b: any) => Number(a?.id ?? 0) - Number(b?.id ?? 0))
        : [];
      const enrichedCart = normalizedCart
        ? {
            ...normalizedCart,
            items: sortedItems.map((item: any) => {
              const fromApi =
                item.product_data && typeof item.product_data === 'object' ? { ...item.product_data } : {};
              return {
                ...item,
                product_data: {
                  ...fromApi,
                  id: item.product_id,
                  product_id: fromApi.product_id ?? item.product_code,
                  name: fromApi.name ?? item.product_name,
                  price: fromApi.price ?? item.product_price,
                  main_image: fromApi.main_image || item.product_image,
                  deposit_require: fromApi.deposit_require ?? item.requires_deposit,
                },
              };
            }),
          }
        : null;
      setCartState((prev) => ({ ...prev, cart: enrichedCart, isLoading: false }));
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
    if (!isAuthenticated) {
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

    setCartState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      await cartAPI.updateCartItem(lineRef.id, updateData);
      await refreshCart();
    } catch (error: any) {
      setCartState((prev) => ({
        ...prev,
        error: error.message || 'Failed to update cart item',
        isLoading: false,
      }));
      throw error;
    }
  };

  const removeFromCart = async (lineRef: CartLineRef) => {
    if (!isAuthenticated) return;

    setCartState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      await cartAPI.removeFromCart(lineRef.id);
      await refreshCart();
      trackEvent('remove_from_cart', { product_id: lineRef.product_id });
    } catch (error: any) {
      setCartState((prev) => ({
        ...prev,
        error: error.message || 'Failed to remove item from cart',
        isLoading: false,
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
    refreshCart();
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
