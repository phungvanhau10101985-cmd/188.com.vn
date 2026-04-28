// features/cart/hooks/useCart.tsx
'use client';

import { useState, useEffect, createContext, useContext, ReactNode } from 'react';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { cartAPI } from '../api/cart-api';
import { trackEvent } from '@/lib/analytics';
import { 
  Cart, 
  CartItem, 
  AddToCartRequest, 
  UpdateCartItemRequest,
  GuestCartItem,
  CartState 
} from '../types/cart';

interface CartContextType extends CartState {
  // Cart actions
  addToCart: (itemData: AddToCartRequest) => Promise<void>;
  updateCartItem: (productId: number, updateData: UpdateCartItemRequest) => Promise<void>;
  removeFromCart: (productId: number) => Promise<void>;
  clearCart: () => Promise<void>;
  
  // Guest cart management
  addToGuestCart: (itemData: AddToCartRequest) => void;
  getGuestCart: () => GuestCartItem[];
  clearGuestCart: () => void;
  
  // Migration
  migrateGuestCart: () => Promise<void>;
  
  // Utilities
  refreshCart: () => Promise<void>;
  getCartItemCount: () => number;
  showAddToCartPopup: boolean;
  lastAddedItem: AddToCartRequest | null;
  hideAddToCartPopup: () => void;
}

const CartContext = createContext<CartContextType | undefined>(undefined);

const GUEST_CART_KEY = 'guest_cart';

export function CartProvider({ children }: { children: ReactNode }) {
  const [cartState, setCartState] = useState<CartState>({
    cart: null,
    isLoading: false,
    error: null,
  });

  const { isAuthenticated, user } = useAuth();
  const [showAddToCartPopup, setShowAddToCartPopup] = useState(false);
  const [lastAddedItem, setLastAddedItem] = useState<AddToCartRequest | null>(null);

  // Guest cart functions
  const getGuestCart = (): GuestCartItem[] => {
    if (typeof window === 'undefined') return [];
    
    try {
      const guestCart = localStorage.getItem(GUEST_CART_KEY);
      return guestCart ? JSON.parse(guestCart) : [];
    } catch {
      return [];
    }
  };

  const saveGuestCart = (items: GuestCartItem[]) => {
    if (typeof window === 'undefined') return;
    
    try {
      localStorage.setItem(GUEST_CART_KEY, JSON.stringify(items));
    } catch (error) {
      console.error('Failed to save guest cart:', error);
    }
  };

  const addToGuestCart = (itemData: AddToCartRequest) => {
    const guestItems = getGuestCart();
    
    // Check if item already exists
    const existingIndex = guestItems.findIndex(
      item => item.product_id === itemData.product_id && 
              item.selected_size === itemData.selected_size &&
              item.selected_color === itemData.selected_color
    );

    const newItem: GuestCartItem = {
      product_id: itemData.product_id,
      quantity: itemData.quantity,
      selected_size: itemData.selected_size,
      selected_color: itemData.selected_color,
      product_data: itemData.product_data || {},
      unit_price: itemData.product_data?.price || 0,
      added_at: new Date().toISOString(),
    };

    if (existingIndex >= 0) {
      // Update quantity if exists
      guestItems[existingIndex].quantity += itemData.quantity;
    } else {
      // Add new item
      guestItems.push(newItem);
    }

    saveGuestCart(guestItems);
    
    // Update local state for immediate UI update
    setCartState(prev => ({
      ...prev,
      cart: {
        id: 0,
        user_id: 0,
        total_items: guestItems.reduce((sum, item) => sum + item.quantity, 0),
        total_price: guestItems.reduce((sum, item) => sum + (item.unit_price * item.quantity), 0),
        items: guestItems.map(item => ({
          id: Math.random(), // Temporary ID for guest items
          product_id: item.product_id,
          quantity: item.quantity,
          selected_size: item.selected_size,
          selected_color: item.selected_color,
          product_data: item.product_data,
          unit_price: item.unit_price,
          total_price: item.unit_price * item.quantity,
          added_at: item.added_at,
        })),
        created_at: new Date().toISOString(),
      },
    }));
    setLastAddedItem(itemData);
    setShowAddToCartPopup(true);
    trackEvent('add_to_cart', {
      product_id: itemData.product_id,
      quantity: itemData.quantity,
      source: 'guest',
    });
  };

  const clearGuestCart = () => {
    if (typeof window === 'undefined') return;
    localStorage.removeItem(GUEST_CART_KEY);
    setCartState(prev => ({ ...prev, cart: null }));
  };

  // Server cart functions
  const refreshCart = async () => {
    if (!isAuthenticated) {
      // Load guest cart for unauthenticated users
      const guestItems = getGuestCart();
      setCartState(prev => ({
        ...prev,
        cart: guestItems.length > 0 ? {
          id: 0,
          user_id: 0,
          total_items: guestItems.reduce((sum, item) => sum + item.quantity, 0),
          total_price: guestItems.reduce((sum, item) => sum + (item.unit_price * item.quantity), 0),
          items: guestItems.map(item => ({
            id: Math.random(),
            product_id: item.product_id,
            quantity: item.quantity,
            selected_size: item.selected_size,
            selected_color: item.selected_color,
            product_data: item.product_data,
            unit_price: item.unit_price,
            total_price: item.unit_price * item.quantity,
            added_at: item.added_at,
          })),
          created_at: new Date().toISOString(),
        } : null,
        isLoading: false,
      }));
      return;
    }

    setCartState(prev => ({ ...prev, isLoading: true, error: null }));
    
    try {
      const cart = await cartAPI.getCart();
      // Đảm bảo cart.items luôn là mảng (API có thể trả items: undefined)
      const normalizedCart = cart ? { ...cart, items: Array.isArray(cart.items) ? cart.items : [] } : null;
      const enrichedCart = normalizedCart ? {
        ...normalizedCart,
        items: normalizedCart.items.map((item: any) => ({
          ...item,
          product_data: {
            id: item.product_id,
            product_id: item.product_data?.product_id ?? item.product_code,
            name: item.product_data?.name ?? item.product_name,
            price: item.product_data?.price ?? item.product_price,
            main_image: item.product_data?.main_image ?? item.product_image,
            deposit_require: item.product_data?.deposit_require ?? item.requires_deposit,
            ...item.product_data,
          },
        })),
      } : null;
      setCartState(prev => ({ ...prev, cart: enrichedCart, isLoading: false }));
    } catch (error: any) {
      console.error('Failed to fetch cart:', error);
      setCartState(prev => ({ 
        ...prev, 
        error: error.message || 'Failed to load cart',
        isLoading: false 
      }));
    }
  };

  const addToCart = async (itemData: AddToCartRequest) => {
    if (!isAuthenticated) {
      addToGuestCart(itemData);
      return;
    }

    setCartState(prev => ({ ...prev, isLoading: true, error: null }));
    
    try {
      await cartAPI.addToCart(itemData);
      // Backend trả về 1 item; luôn refresh full cart để cart.items là mảng
      await refreshCart();
      setLastAddedItem(itemData);
      setShowAddToCartPopup(true);
      trackEvent('add_to_cart', {
        product_id: itemData.product_id,
        quantity: itemData.quantity,
        source: 'user',
      });
    } catch (error: any) {
      setCartState(prev => ({ 
        ...prev, 
        error: error.message || 'Failed to add item to cart',
        isLoading: false 
      }));
      throw error;
    }
  };

  const updateCartItem = async (productId: number, updateData: UpdateCartItemRequest) => {
    if (!isAuthenticated) {
      // Update guest cart
      const guestItems = getGuestCart();
      const itemIndex = guestItems.findIndex(item => item.product_id === productId);
      
      if (itemIndex >= 0) {
        guestItems[itemIndex].quantity = updateData.quantity;
        guestItems[itemIndex].selected_size = updateData.selected_size;
        guestItems[itemIndex].selected_color = updateData.selected_color;
        saveGuestCart(guestItems);
        await refreshCart(); // Refresh local state
      }
      return;
    }

    setCartState(prev => ({ ...prev, isLoading: true, error: null }));
    
    try {
      await cartAPI.updateCartItem(productId, updateData);
      await refreshCart();
    } catch (error: any) {
      setCartState(prev => ({ 
        ...prev, 
        error: error.message || 'Failed to update cart item',
        isLoading: false 
      }));
      throw error;
    }
  };

  const removeFromCart = async (productId: number) => {
    if (!isAuthenticated) {
      // Remove from guest cart
      const guestItems = getGuestCart().filter(item => item.product_id !== productId);
      saveGuestCart(guestItems);
      await refreshCart(); // Refresh local state
      return;
    }

    setCartState(prev => ({ ...prev, isLoading: true, error: null }));
    
    try {
      await cartAPI.removeFromCart(productId);
      await refreshCart();
      trackEvent('remove_from_cart', { product_id: productId });
    } catch (error: any) {
      setCartState(prev => ({ 
        ...prev, 
        error: error.message || 'Failed to remove item from cart',
        isLoading: false 
      }));
      throw error;
    }
  };

  const clearCart = async () => {
    if (!isAuthenticated) {
      clearGuestCart();
      return;
    }

    setCartState(prev => ({ ...prev, isLoading: true, error: null }));
    
    try {
      await cartAPI.clearCart();
      setCartState(prev => ({ ...prev, cart: null, isLoading: false }));
      trackEvent('clear_cart', { item_count: cartState.cart?.total_items ?? 0 });
    } catch (error: any) {
      setCartState(prev => ({ 
        ...prev, 
        error: error.message || 'Failed to clear cart',
        isLoading: false 
      }));
      throw error;
    }
  };

  const migrateGuestCart = async () => {
    if (!isAuthenticated) return;

    const guestItems = getGuestCart();
    if (guestItems.length === 0) return;

    try {
      const result = await cartAPI.migrateGuestCart(guestItems);
      const c = result.cart;
      const normalizedCart = c ? { ...c, items: Array.isArray(c.items) ? c.items : [] } : null;
      setCartState(prev => ({ ...prev, cart: normalizedCart }));
      clearGuestCart();
    } catch (error) {
      console.error('Failed to migrate guest cart:', error);
    }
  };

  const getCartItemCount = (): number => {
    if (!cartState.cart) return 0;
    return cartState.cart.total_items;
  };

  // Effects
  useEffect(() => {
    refreshCart();
  }, [isAuthenticated]);

  // Auto-migrate guest cart when user logs in
  useEffect(() => {
    if (isAuthenticated && user) {
      const guestItems = getGuestCart();
      if (guestItems.length > 0) {
        migrateGuestCart();
      }
    }
  }, [isAuthenticated, user]);

  const value: CartContextType = {
    ...cartState,
    addToCart,
    updateCartItem,
    removeFromCart,
    clearCart,
    addToGuestCart,
    getGuestCart,
    clearGuestCart,
    migrateGuestCart,
    refreshCart,
    getCartItemCount,
    showAddToCartPopup,
    lastAddedItem,
    hideAddToCartPopup: () => setShowAddToCartPopup(false),
  };

  return (
    <CartContext.Provider value={value}>
      {children}
    </CartContext.Provider>
  );
}

export function useCart() {
  const context = useContext(CartContext);
  if (context === undefined) {
    throw new Error('useCart must be used within a CartProvider');
  }
  return context;
}
