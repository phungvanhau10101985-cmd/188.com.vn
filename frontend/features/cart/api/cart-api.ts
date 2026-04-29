// fix_frontend_cart_api.ts
/**
 * FIX: Sửa lỗi trùng prefix trong cart API
 * Copy nội dung này vào: frontend/features/cart/api/cart-api.ts
 */

import { 
  Cart, 
  AddToCartRequest, 
  UpdateCartItemRequest,
  GuestCartItem,
  CartMigrationResponse
} from '../types/cart';
import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';

class CartAPI {
  private async fetchWithAuth(path: string, options: RequestInit = {}) {
    const base = getApiBaseUrl();
    const url = path.startsWith('http') ? path : `${base}${path}`;
    const token = localStorage.getItem('access_token');
    
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...ngrokFetchHeaders(),
      ...(token && { 'Authorization': `Bearer ${token}` }),
      ...(options.headers as Record<string, string> | undefined),
    };

    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });

      if (!response.ok) {
        if (response.status === 401) {
          // Token expired or invalid — quay lại đúng trang sau đăng nhập lại
          localStorage.removeItem('access_token');
          localStorage.removeItem('user');
          const { buildAuthLoginHrefFromFullPath, getBrowserReturnLocation } = await import('@/lib/auth-redirect');
          window.location.href = buildAuthLoginHrefFromFullPath(getBrowserReturnLocation());
          throw new Error('Authentication required');
        }
        
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(errorData.detail || 'Request failed');
      }

      return response.json();
    } catch (error) {
      console.error('Cart API Error:', error);
      throw error;
    }
  }

  // Đường dẫn tương đối tới /api/v1 (getApiBaseUrl) — tương thích HTTPS/ngrok, không dùng localhost cố định
  async getCart(): Promise<Cart> {
    return this.fetchWithAuth(`/cart`);
  }

  async addToCart(itemData: AddToCartRequest): Promise<Cart> {
    return this.fetchWithAuth(`/cart/items`, {
      method: 'POST',
      body: JSON.stringify(itemData),
    });
  }

  async updateCartItem(itemId: number, updateData: UpdateCartItemRequest): Promise<Cart> {
    return this.fetchWithAuth(`/cart/items/${itemId}`, {
      method: 'PUT',
      body: JSON.stringify(updateData),
    });
  }

  async removeFromCart(itemId: number): Promise<Cart> {
    return this.fetchWithAuth(`/cart/items/${itemId}`, {
      method: 'DELETE',
    });
  }

  async clearCart(): Promise<{ message: string }> {
    return this.fetchWithAuth(`/cart`, {
      method: 'DELETE',
    });
  }

  async migrateGuestCart(guestItems: GuestCartItem[]): Promise<CartMigrationResponse> {
    return this.fetchWithAuth(`/cart/migrate-guest`, {
      method: 'POST',
      body: JSON.stringify({ guest_items: guestItems }),
    });
  }

  async getCartItemCount(): Promise<{ count: number }> {
    return this.fetchWithAuth(`/cart/count`);
  }
}

export const cartAPI = new CartAPI();