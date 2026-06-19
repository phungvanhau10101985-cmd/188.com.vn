// features/cart/types/cart.ts
import type { SiteSaleCalendarState, SiteSaleProductPricing } from '@/types/api';

export interface CartItem {
  id: number;
  product_id: number;
  product_code?: string;
  quantity: number;
  selected_size?: string;
  selected_color?: string;
  selected_color_name?: string;
  product_name?: string;
  product_price?: number;
  list_price?: number;
  original_price?: number;
  site_sale?: SiteSaleProductPricing;
  product_image?: string;
  product_data?: {
    id?: number;
    product_id?: string;
    name?: string;
    price?: number;
    list_price?: number;
    main_image?: string;
    brand_name?: string;
    available?: number;
    original_price?: number;
    is_warehouse_clearance?: boolean;
    warehouse_clearance_percent?: number;
    deposit_require?: boolean;
  };
  unit_price?: number;
  total_price: number;
  added_at?: string;
  created_at?: string;
  updated_at?: string;
  requires_deposit?: boolean;
}

export interface Cart {
  id: number;
  user_id: number;
  total_items: number;
  total_price: number;
  items: CartItem[];
  items_count?: number;
  requires_deposit?: boolean;
  created_at: string;
  updated_at?: string;
  loyalty_discount_percent?: number;
  loyalty_discount_amount?: number;
  final_price?: number;
  loyalty_tier_name?: string;
  birthday_discount_active?: boolean;
  birthday_discount_percent?: number;
  birthday_discount_amount?: number;
  birthday_next_date?: string | null;
  welcome_promo_eligible?: boolean;
  welcome_promo_applied?: boolean;
  welcome_discount_percent?: number;
  welcome_discount_amount?: number;
  welcome_promo_code?: string | null;
  site_sale?: SiteSaleCalendarState | null;
}

export interface CartState {
  cart: Cart | null;
  isLoading: boolean;
  error: string | null;
}

export interface AddToCartRequest {
  product_id: number;
  quantity: number;
  selected_size?: string;
  selected_color?: string;
  /** URL ảnh đúng biến thể — backend ưu tiên để không phụ thuộc khớp chuỗi màu. */
  line_image_url?: string;
  product_data?: any;
  /** JWT pv2 — chiết khấu tự động Google Shopping */
  google_pv2_token?: string;
}

export interface UpdateCartItemRequest {
  quantity: number;
  selected_size?: string;
  selected_color?: string;
}

export interface GuestCartItem {
  product_id: number;
  quantity: number;
  selected_size?: string;
  selected_color?: string;
  product_data: any;
  unit_price: number;
  added_at: string;
}

export interface CartMigrationResponse {
  message: string;
  migrated_items: number;
  total_items: number;
  cart: Cart;
}

/** Một dòng giỏ — API: `id` = cart_items.id; khách: `id` băm ổn định + product_id/size/color để tìm đúng dòng. */
export interface CartLineRef {
  id: number;
  product_id: number;
  selected_size?: string;
  selected_color?: string;
}
