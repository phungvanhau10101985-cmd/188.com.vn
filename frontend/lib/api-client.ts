// frontend/lib/api-client.ts - FIXED VERSION

import { 
  Product, 
  ProductListResponse, 
  ProductQuestionItem,
  ProductReviewItem,
  Category, 
  CategoryLevel1,
  CategoryLevel2,
  CategoryLevel3,
  CategoryByPath,
  Cart,
  ProductSearchParams,
  AuthResponse,
  UserAddress,
  AddressCreateInput,
  AddressUpdateInput,
  NanoaiSearchResponse,
  SameAgeGenderCohortMode,
} from '@/types/api';

import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';
import { getGuestSessionId } from '@/lib/guest-session';

const IS_PRODUCTION = process.env.NODE_ENV === 'production';

/** Node từ GET /categories/tree-v2 (taxonomy DB). */
interface TaxonomyTreeV2Node {
  name: string;
  slug?: string;
  children?: TaxonomyTreeV2Node[];
}

function taxonomyTreeV2ToCategoryLevel1(raw: unknown): CategoryLevel1[] {
  if (!Array.isArray(raw)) return [];
  const mapL3 = (n: TaxonomyTreeV2Node): CategoryLevel3 => ({
    name: String(n?.name ?? '').trim(),
    slug: n?.slug != null && String(n.slug).trim() ? String(n.slug).trim() : undefined,
  });
  const mapL2 = (n: TaxonomyTreeV2Node): CategoryLevel2 => ({
    name: String(n?.name ?? '').trim(),
    slug: n?.slug != null && String(n.slug).trim() ? String(n.slug).trim() : undefined,
    children: Array.isArray(n?.children)
      ? n.children
          .filter((c) => String(c?.name ?? '').trim().length > 0)
          .map(mapL3)
      : [],
  });
  return (raw as TaxonomyTreeV2Node[])
    .filter((c) => String(c?.name ?? '').trim().length > 0)
    .map((c1) => ({
      name: String(c1?.name ?? '').trim(),
      slug: c1?.slug != null && String(c1.slug).trim() ? String(c1.slug).trim() : undefined,
      children: Array.isArray(c1?.children)
        ? c1.children
            .filter((c) => String(c?.name ?? '').trim().length > 0)
            .map(mapL2)
        : [],
    }));
}

/** Giới hạn mỗi lần gọi text-search NanoAI (khớp backend `le=100`). */
export const NANOAI_TEXT_SEARCH_LIMIT = 100;

/** Giới hạn mỗi lần gọi image-search NanoAI (khớp backend). */
export const NANOAI_IMAGE_SEARCH_LIMIT = 100;

export interface CreateOrderRequest {
  shipping_address: string;
  payment_method: string;
  note?: string;
  shipping_phone?: string;
  shipping_name?: string;
}

/** Payload đúng schema backend OrderCreate */
export interface OrderCreateRequest {
  customer_name: string;
  customer_phone: string;
  customer_email: string;
  customer_address: string;
  customer_note?: string;
  payment_method: 'cod' | 'bank_transfer' | 'vnpay' | 'momo' | 'zalopay';
  shipping_method?: string;
  items: { product_id: number; quantity: number; selected_size?: string; selected_color?: string }[];
  deposit_type?: 'none' | 'percent_30' | 'percent_100';
}

export interface OrderResponse {
  id: number;
  order_code?: string;
  total_amount: number;
  status: string;
  customer_phone?: string;
  deposit_amount?: number;
  message?: string;
}

export interface BankAccountInfo {
  id: number;
  bank_name: string;
  account_number: string;
  account_holder: string;
  bank_code?: string | null;
  qr_template_url?: string | null;
  branch?: string | null;
  note?: string | null;
  /** Alias VietQR: dùng bank_code nếu có */
  bank_short_name?: string | null;
}

export interface AnalyticsEventCreate {
  event_name: string;
  session_id?: string | null;
  page_url?: string | null;
  referrer?: string | null;
  properties?: Record<string, any>;
}

class ApiClient {
  private async fetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = endpoint.startsWith('http') ? endpoint : `${getApiBaseUrl()}${endpoint}`;
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...ngrokFetchHeaders(),
      ...(options.headers as Record<string, string> || {}),
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const guestSid = typeof window !== 'undefined' ? getGuestSessionId() : null;
    if (guestSid) {
      headers['X-Guest-Session-Id'] = guestSid;
    }

    if (!IS_PRODUCTION) {
      console.log(`🔍 API Call: ${url}`, { headers: { ...headers, Authorization: 'Bearer ***' } });
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers,
        credentials: 'include',
      });

      if (!IS_PRODUCTION) {
        console.log(`📡 Response: ${response.status} ${response.statusText}`);
      }

      if (response.status === 401) {
        console.error('❌ 401 Unauthorized - Token invalid or missing');
        if (typeof window !== 'undefined') {
          localStorage.removeItem('access_token');
          // Chỉ xoá user khi request từng gửi Bearer — tránh mất phiên chỉ-cookie / race sau đăng nhập
          if (token) {
            localStorage.removeItem('user');
          }
        }
        throw new Error('Authentication required');
      }

      if (!response.ok) {
        const errorText = await response.text();
        console.error(`❌ API Error ${response.status}:`, errorText);
        let errorData;
        try {
          errorData = JSON.parse(errorText);
        } catch {
          errorData = { detail: errorText || `API Error: ${response.status}` };
        }
        throw new Error(errorData.detail || `API Error: ${response.status}`);
      }

      const data = await response.json();
      if (!IS_PRODUCTION) {
        console.log('✅ API Success:', data);
      }
      return data;
    } catch (error) {
      console.error(`🔥 Fetch error at ${url}:`, error);
      throw error;
    }
  }

  // PRODUCT
  async getProducts(params?: ProductSearchParams): Promise<ProductListResponse> {
    const query = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') query.append(key, String(value));
      });
    }
    return this.fetch<ProductListResponse>(`/products/?${query.toString()}`);
  }

  async getProductBySlug(slug: string): Promise<Product> {
    return this.fetch<Product>(`/products/by-slug/?slug=${encodeURIComponent(slug)}`);
  }
  
  async searchProducts(keyword: string): Promise<ProductListResponse> {
    return this.fetch<ProductListResponse>(`/products/search/?q=${encodeURIComponent(keyword)}`);
  }

  async getProductById(id: number): Promise<Product> {
    return this.fetch<Product>(`/products/by-id/${id}`);
  }
  
  async getProductByProductId(productId: string): Promise<Product> {
    return this.fetch<Product>(`/products/${encodeURIComponent(productId)}`);
  }

  // CATEGORY
  async getCategories(): Promise<Category[]> {
    return this.fetch<Category[]>('/categories/');
  }

  async getCategoryBySlug(slug: string): Promise<Category> {
    return this.fetch<Category>(`/categories/slug/${slug}`);
  }

  /** Cây danh mục 3 cấp từ sản phẩm (AB, AC, AD) */
  async getCategoryTreeFromProducts(): Promise<CategoryLevel1[]> {
    const data = await this.fetch<CategoryLevel1[] | { data?: CategoryLevel1[] }>('/categories/from-products');
    if (Array.isArray(data)) return data;
    if (data && Array.isArray((data as { data?: CategoryLevel1[] }).data)) return (data as { data: CategoryLevel1[] }).data;
    return [];
  }

  /**
   * Cây 3 cấp từ bảng `categories` (sau import taxonomy tại /admin/taxonomy).
   * Dùng cho admin mapping / menu chuẩn; slug khớp URL taxonomy.
   */
  async getCategoryTreeV2(options?: { isActiveOnly?: boolean }): Promise<CategoryLevel1[]> {
    const sp = new URLSearchParams();
    sp.set('is_active_only', options?.isActiveOnly === false ? 'false' : 'true');
    const raw = await this.fetch<unknown>(`/categories/tree-v2?${sp.toString()}`);
    return taxonomyTreeV2ToCategoryLevel1(raw);
  }

  /** Nhánh c1/c2/c3 có ≥1 SP (khóa \\x1f). Dùng lọc cột Nguồn khi tạo mapping. */
  async getProductCategoryBranchKeys(options?: { isActiveOnly?: boolean }): Promise<{
    level2_keys: string[];
    level3_keys: string[];
  }> {
    const sp = new URLSearchParams();
    if (options?.isActiveOnly === false) sp.set('is_active', 'false');
    return this.fetch<{ level2_keys: string[]; level3_keys: string[] }>(
      `/categories/product-branch-keys?${sp.toString()}`
    );
  }

  /** Resolve path slugs → thông tin danh mục (SEO). level2, level3 optional. */
  async getCategoryByPath(
    level1: string,
    level2?: string | null,
    level3?: string | null
  ): Promise<CategoryByPath> {
    const params = new URLSearchParams({ level1: level1 });
    if (level2) params.set('level2', level2);
    if (level3) params.set('level3', level3);
    return this.fetch<CategoryByPath>(`/categories/from-products/by-path?${params.toString()}`);
  }

  // ========== CART - FIXED ENDPOINTS ==========
  async getCart(): Promise<Cart> {
    return this.fetch<Cart>('/cart/');  // FIXED: '/cart/' not '/cart/cart'
  }

  async addToCart(productId: number, quantity: number = 1, size?: string, color?: string): Promise<Cart> {
    return this.fetch<Cart>('/cart/items', {  // FIXED: '/cart/items' not '/cart/cart/items'
      method: 'POST',
      body: JSON.stringify({ 
        product_id: productId, 
        quantity, 
        selected_size: size, 
        selected_color: color 
      })
    });
  }

  async updateCartItem(itemId: number, quantity: number): Promise<Cart> {
    return this.fetch<Cart>(`/cart/items/${itemId}`, {  // FIXED
      method: 'PUT',
      body: JSON.stringify({ quantity })
    });
  }

  async removeFromCart(itemId: number): Promise<Cart> {
    return this.fetch<Cart>(`/cart/items/${itemId}`, {  // FIXED
      method: 'DELETE' 
    });
  }

  async clearCart(): Promise<any> {
    return this.fetch('/cart/', { method: 'DELETE' });  // FIXED
  }
  
  async migrateGuestCart(guestItems: any[]): Promise<any> {
    return this.fetch('/cart/migrate-guest', {  // FIXED
      method: 'POST',
      body: JSON.stringify({ guest_items: guestItems })
    });
  }

  // ORDER
  async createOrder(orderData: CreateOrderRequest): Promise<OrderResponse> {
    return this.fetch<OrderResponse>('/orders/', {
      method: 'POST',
      body: JSON.stringify(orderData)
    });
  }

  /** Tạo đơn với payload đầy đủ (customer_*, items) - dùng từ giỏ hàng/checkout */
  async createOrderFull(orderData: OrderCreateRequest): Promise<OrderResponse> {
    return this.fetch<OrderResponse>('/orders/', {
      method: 'POST',
      body: JSON.stringify(orderData)
    });
  }

  /** Sau đăng nhập: gộp xem / yêu thích / lịch sử tìm kiếm từ phiên khách vào tài khoản. */
  async mergeGuestBehaviorSession(): Promise<void> {
    await this.fetch('/user-behavior/session/merge', { method: 'POST' }).catch(() => {});
  }

  async getOrders(params?: { status?: string; skip?: number; limit?: number }): Promise<any[]> {
    const sp = new URLSearchParams();
    if (params?.status) sp.set('status', params.status);
    if (params?.skip != null) sp.set('skip', String(params.skip));
    if (params?.limit != null) sp.set('limit', String(params.limit));
    const q = sp.toString();
    return this.fetch<any[]>(q ? `/orders/?${q}` : '/orders/');
  }

  async getOrder(orderId: number): Promise<any> {
    return this.fetch<any>(`/orders/${orderId}`);
  }

  async cancelOrder(orderId: number, reason: string): Promise<any> {
    return this.fetch<any>(`/orders/${orderId}/cancel?reason=${encodeURIComponent(reason)}`, { method: 'POST' });
  }

  async confirmReceived(orderId: number): Promise<any> {
    return this.fetch<any>(`/orders/${orderId}/confirm-received`, { method: 'POST' });
  }

  async updateOrderDepositType(orderId: number, depositType: 'percent_30' | 'percent_100'): Promise<any> {
    return this.fetch<any>(`/orders/${orderId}/deposit-type`, {
      method: 'PATCH',
      body: JSON.stringify({ deposit_type: depositType }),
    });
  }

  /** QR SePay (qr.sepay.vn) + nội dung CK — backend đọc SEPAY_QR_* */
  async getOrderSepayDepositInfo(orderId: number): Promise<{
    enabled: boolean;
    transfer_content: string;
    amount: string | number;
    qr_image_url?: string | null;
    bank_code?: string | null;
    account_number?: string | null;
    register_webhook_url?: string | null;
  }> {
    return this.fetch(`/orders/${orderId}/sepay-deposit-info`);
  }

  // USER BEHAVIOR
  async trackProductView(productId: number, productData?: any): Promise<void> {
    this.fetch('/user-behavior/products/view', {
      method: 'POST',
      body: JSON.stringify({ 
        product_id: productId,
        product_data: productData 
      })
    }).catch(() => {});
  }

  /** Danh sách sản phẩm đã xem (tài khoản hoặc phiên khách qua X-Guest-Session-Id). */
  async getViewedProducts(limit = 24): Promise<any[]> {
    return this.fetch<any[]>(`/user-behavior/products/viewed?limit=${limit}`);
  }

  /** Đề xuất theo nhóm tuổi/giới (cần đăng nhập + ngày sinh & giới tính trong hồ sơ). */
  async getProductsViewedBySameAgeGender(limit = 24): Promise<{
    products: Product[];
    cohort_mode: SameAgeGenderCohortMode;
  }> {
    const res = await this.fetch<{ products?: Product[]; cohort_mode?: SameAgeGenderCohortMode }>(
      `/user-behavior/products/viewed-by-same-age-gender?limit=${limit}`
    ).catch(() => ({ products: [], cohort_mode: 'requires_login' as SameAgeGenderCohortMode }));
    return {
      products: res?.products ?? [],
      cohort_mode: res?.cohort_mode ?? 'exact_cohort',
    };
  }

  /**
   * Lưới «Tất cả sản phẩm» trang chủ (không lọc): ưu tiên theo danh mục/shop từ lượt xem + thích.
   * Khách và đăng nhập đều dùng header Bearer / X-Guest-Session-Id như mọi request.
   */
  async getPersonalizedHomeFeed(skip = 0, limit = 48): Promise<ProductListResponse> {
    const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    return this.fetch<ProductListResponse>(`/user-behavior/products/home-feed?${params}`);
  }

  /** Sản phẩm cùng shop với 8 sản phẩm xem gần nhất; phân trang: limit, offset, seed. */
  async getProductsSameShopAsRecentViews(
    limit = 60,
    offset = 0,
    seed?: number | null
  ): Promise<{ products: Product[]; total: number; seed: number | null }> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (seed != null) params.set('seed', String(seed));
    const res = await this.fetch<{ products?: Product[]; total?: number; seed?: number | null }>(
      `/user-behavior/products/same-shop-as-recent-views?${params}`
    ).catch(() => ({ products: [], total: 0, seed: null }));
    return {
      products: res?.products ?? [],
      total: res?.total ?? 0,
      seed: res?.seed ?? null,
    };
  }

  async addToFavorites(productId: number, productData?: any): Promise<any> {
    return this.fetch('/user-behavior/products/favorite', {
      method: 'POST',
      body: JSON.stringify({ 
        product_id: productId,
        product_data: productData 
      })
    });
  }

  async removeFromFavorites(productId: number): Promise<any> {
    return this.fetch(`/user-behavior/products/favorite/${productId}`, {
      method: 'DELETE'
    });
  }

  async getFavorites(): Promise<any[]> {
    return this.fetch<any[]>('/user-behavior/products/favorites');
  }

  async isProductFavorited(productId: number): Promise<{ is_favorited: boolean }> {
    return this.fetch<{ is_favorited: boolean }>(`/user-behavior/products/${productId}/is-favorited`);
  }

  /** Gợi ý từ khóa tìm kiếm (3 đầu = gần đây, còn lại = cùng giới tính + năm sinh). */
  async getSearchSuggestions(limit = 12): Promise<{ suggestions: string[] }> {
    return this.fetch<{ suggestions: string[] }>(`/user-behavior/search/suggestions?limit=${limit}`);
  }

  /** Lưu lịch sử tìm kiếm (cần đăng nhập). */
  async addSearchHistory(searchQuery: string): Promise<void> {
    return this.fetch('/user-behavior/search/history', {
      method: 'POST',
      body: JSON.stringify({ search_query: searchQuery.trim() }),
    });
  }

  // ANALYTICS EVENTS (conversion funnel)
  async trackEvent(eventData: AnalyticsEventCreate): Promise<void> {
    await this.fetch('/analytics/events', {
      method: 'POST',
      body: JSON.stringify(eventData),
    });
  }

  // PRODUCT QUESTIONS (câu hỏi câu trả lời sản phẩm)
  async getProductQuestions(productId: number): Promise<ProductQuestionItem[]> {
    return this.fetch<ProductQuestionItem[]>(
      `/product-questions/for-product?product_id=${productId}&limit=100`
    );
  }

  async askProductQuestion(productId: number, content: string): Promise<ProductQuestionItem> {
    return this.fetch<ProductQuestionItem>('/product-questions/ask', {
      method: 'POST',
      body: JSON.stringify({ product_id: productId, content: content.trim() }),
    });
  }

  /** Người đã mua hàng trả lời câu hỏi (cần đăng nhập và đã mua sản phẩm). */
  async replyToQuestion(questionId: number, content: string): Promise<ProductQuestionItem> {
    return this.fetch<ProductQuestionItem>(`/product-questions/reply/${questionId}`, {
      method: 'POST',
      body: JSON.stringify({ content: content.trim() }),
    });
  }

  /** Bấm/bỏ bấm nút Hữu ích (cần đăng nhập). Trả về { useful, user_has_voted }. */
  async toggleQuestionUseful(questionId: number): Promise<{ useful: number; user_has_voted: boolean }> {
    return this.fetch<{ useful: number; user_has_voted: boolean }>(
      `/product-questions/useful/${questionId}/toggle`,
      { method: 'POST' }
    );
  }

  // PRODUCT REVIEWS (đánh giá - chỉ admin trả lời)
  async getProductReviews(productId: number): Promise<ProductReviewItem[]> {
    return this.fetch<ProductReviewItem[]>(
      `/product-reviews/for-product?product_id=${productId}&limit=100`
    );
  }

  async toggleReviewUseful(reviewId: number): Promise<{ useful: number; user_has_voted: boolean }> {
    return this.fetch<{ useful: number; user_has_voted: boolean }>(
      `/product-reviews/useful/${reviewId}/toggle`,
      { method: 'POST' }
    );
  }

  /** Lấy danh sách product_id mà user đã đánh giá. */
  async getUserReviewedProductIds(productIds: number[]): Promise<{ product_ids: number[] }> {
    if (productIds.length === 0) return { product_ids: [] };
    return this.fetch<{ product_ids: number[] }>(
      `/product-reviews/user-reviewed-ids?product_ids=${productIds.join(',')}`
    );
  }

  /** Kiểm tra user có được phép đánh giá sản phẩm (đã mua và nhận hàng). */
  async canReviewProduct(productId: number): Promise<{ can_review: boolean; reason?: string }> {
    return this.fetch<{ can_review: boolean; reason?: string }>(
      `/product-reviews/can-review?product_id=${productId}`
    );
  }

  async submitProductReview(data: { product_id: number; star: number; title?: string; content: string; images?: string[] }): Promise<ProductReviewItem> {
    return this.fetch<ProductReviewItem>('/product-reviews/submit', {
      method: 'POST',
      body: JSON.stringify({
        product_id: data.product_id,
        star: data.star,
        title: data.title || '',
        content: data.content.trim(),
        images: data.images || [],
      }),
    });
  }

  // AUTH
  async login(credentials: any): Promise<AuthResponse> {
    // Format đúng cho backend
    const payload = {
      phone: credentials.phone,
      date_of_birth: credentials.date_of_birth || credentials.password
    };
    
    console.log('🔐 Login payload:', payload);
    
    const result = await this.fetch<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    
    // Lưu token
    if (result.access_token && typeof window !== 'undefined') {
      localStorage.setItem('access_token', result.access_token);
      console.log('💾 Token saved to localStorage');
    }
    
    return result;
  }

  async register(userData: any): Promise<any> {
    return this.fetch('/auth/register', {
      method: 'POST',
      body: JSON.stringify(userData)
    });
  }

  async getProfile(): Promise<any> {
    return this.fetch('/auth/me');
  }

  // ADDRESSES (Sổ địa chỉ)
  async getAddresses(): Promise<UserAddress[]> {
    return this.fetch<UserAddress[]>('/addresses/');
  }

  async getDefaultAddress(): Promise<UserAddress | null> {
    return this.fetch<UserAddress | null>('/addresses/default');
  }

  async getAddress(id: number): Promise<UserAddress> {
    return this.fetch<UserAddress>(`/addresses/${id}`);
  }

  async createAddress(data: AddressCreateInput): Promise<UserAddress> {
    return this.fetch<UserAddress>('/addresses/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateAddress(id: number, data: AddressUpdateInput): Promise<UserAddress> {
    return this.fetch<UserAddress>(`/addresses/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async setDefaultAddress(id: number): Promise<UserAddress> {
    return this.fetch<UserAddress>(`/addresses/${id}/set-default`, {
      method: 'POST',
    });
  }

  async deleteAddress(id: number): Promise<void> {
    return this.fetch(`/addresses/${id}`, { method: 'DELETE' });
  }

  // BANK ACCOUNTS (public - cho trang đặt cọc)
  async getBankAccounts(): Promise<BankAccountInfo[]> {
    const rows = await this.fetch<BankAccountInfo[]>('/bank-accounts/');
    return rows.map((r) => ({
      ...r,
      bank_short_name: r.bank_short_name ?? r.bank_code ?? null,
    }));
  }

  // LOYALTY
  async getMyLoyaltyStatus(): Promise<any> {
    return this.fetch('/loyalty/my-status');
  }

  async getLoyaltyTiers(): Promise<any[]> {
    return this.fetch<any[]>('/loyalty/tiers');
  }

  async updateProfile(userData: any): Promise<any> {
    return this.fetch('/auth/me', {
      method: 'PUT',
      body: JSON.stringify(userData)
    });
  }

  async sendForgotDobOtp(phone: string): Promise<{ message: string; phone: string; provider: string }> {
    return this.fetch('/auth/send-forgot-dob-otp', {
      method: 'POST',
      body: JSON.stringify({ phone: phone.trim() })
    });
  }

  async forgotDateOfBirth(phone: string, otpCode: string): Promise<any> {
    return this.fetch('/auth/forgot-date-of-birth', {
      method: 'POST',
      body: JSON.stringify({ phone: phone.trim(), otp_code: otpCode.trim() })
    });
  }

  // DEBUG: Kiểm tra token
  async debugCheckToken(): Promise<any> {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    console.log('🔍 Debug token:', token);
    
    if (!token) {
      return { error: 'No token' };
    }
    
    try {
      // Test token bằng cách gọi profile
      const profile = await this.getProfile();
      return { token: token.substring(0, 50) + '...', valid: true, profile };
    } catch (error) {
      return { token: token.substring(0, 50) + '...', valid: false, error };
    }
  }

  // COMPATIBILITY
  simple = {
    getProductBySlug: async (slug: string) => {
        try {
            const product = await this.getProductBySlug(slug);
            return { found: true, product };
        } catch {
            return { found: false };
        }
    }
  };

  // ========== CATEGORY SEO ==========
  
  /** Kiểm tra danh mục: redirect hay noindex. Mỗi ý định chỉ SEO một trang. */
  async checkCategoryRedirect(path: string): Promise<{
    should_redirect: boolean;
    redirect_to: string | null;
    seo_indexable?: boolean;
    canonical_url?: string | null;
  }> {
    try {
      const url = `${getApiBaseUrl()}/category-seo/check-redirect?path=${encodeURIComponent(path)}`;
      const res = await fetch(url);
      if (!res.ok) return { should_redirect: false, redirect_to: null };
      return await res.json();
    } catch {
      return { should_redirect: false, redirect_to: null };
    }
  }

  /** Lấy tất cả redirects đã approved */
  async getCategorySeoRedirects(): Promise<{ total: number; redirects: Array<{ from: string; to: string; source_name: string; canonical_name: string }> }> {
    try {
      const url = `${getApiBaseUrl()}/category-seo/redirects`;
      const res = await fetch(url);
      if (!res.ok) return { total: 0, redirects: [] };
      return await res.json();
    } catch {
      return { total: 0, redirects: [] };
    }
  }

  /** Chạy scan SEO danh mục (phát hiện trùng, tạo mapping, tự duyệt nếu confidence cao) */
  async runCategorySeoScan(forceRescan = false): Promise<{
    status: string;
    message: string;
    total_categories?: number;
    duplicates_found?: number;
    auto_approved?: number;
    details?: Array<{ category: string; path: string; is_duplicate: boolean; canonical?: string; status: string }>;
  }> {
    try {
      const url = `${getApiBaseUrl()}/category-seo/scan${forceRescan ? '?force_rescan=true' : ''}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(await res.text());
      return await res.json();
    } catch (e) {
      throw e;
    }
  }

  /** Gộp sản phẩm từ danh mục không SEO (redirect/noindex) vào danh mục canonical. Cần gọi sau khi đã approve mappings. */
  async runCategorySeoMerge(): Promise<{
    status: string;
    message: string;
    merged_mappings: number;
    products_updated: number;
    details?: Array<{ source_path: string; canonical_path: string; products_updated: number }>;
  }> {
      const url = `${getApiBaseUrl()}/category-seo/merge-non-seo`;
    const res = await fetch(url, { method: 'POST' });
    if (!res.ok) throw new Error(await res.text());
    return await res.json();
  }

  /** Lấy tổng quan SEO danh mục */
  async getCategorySeoSummary(): Promise<{
    total_categories: number;
    total_mappings: number;
    pending_review: number;
    approved: number;
    rejected: number;
    active_redirects: number;
    coverage: string;
  }> {
    try {
      const url = `${getApiBaseUrl()}/category-seo/summary`;
      const res = await fetch(url);
      if (!res.ok) throw new Error('Failed to get SEO summary');
      return await res.json();
    } catch {
      return {
        total_categories: 0,
        total_mappings: 0,
        pending_review: 0,
        approved: 0,
        rejected: 0,
        active_redirects: 0,
        coverage: '0%'
      };
    }
  }

  // ========== CATEGORY MANAGEMENT ==========

  /** Chuyển danh mục cấp 2 xuống cấp 3 */
  async moveLevel2ToLevel3(params: {
    category: string;
    subcategory: string;
    target_subcategory: string;
    new_sub_subcategory_name?: string;
  }): Promise<{
    status: string;
    message: string;
    products_updated: number;
    from: string;
    to: string;
  }> {
    const query = new URLSearchParams();
    query.append('category', params.category);
    query.append('subcategory', params.subcategory);
    query.append('target_subcategory', params.target_subcategory);
    if (params.new_sub_subcategory_name) {
      query.append('new_sub_subcategory_name', params.new_sub_subcategory_name);
    }
    
    return this.fetch(`/category-seo/move-level2-to-level3?${query.toString()}`, {
      method: 'POST'
    });
  }

  /** Chuyển danh mục cấp 3 lên cấp 2 */
  async moveLevel3ToLevel2(params: {
    category: string;
    subcategory: string;
    sub_subcategory: string;
    new_subcategory_name?: string;
  }): Promise<{
    status: string;
    message: string;
    products_updated: number;
    from: string;
    to: string;
  }> {
    const query = new URLSearchParams();
    query.append('category', params.category);
    query.append('subcategory', params.subcategory);
    query.append('sub_subcategory', params.sub_subcategory);
    if (params.new_subcategory_name) {
      query.append('new_subcategory_name', params.new_subcategory_name);
    }
    
    return this.fetch(`/category-seo/move-level3-to-level2?${query.toString()}`, {
      method: 'POST'
    });
  }

  /** Đổi cấp danh mục giữa cấp 2 và cấp 3 */
  async swapLevel2Level3(params: {
    category: string;
    subcategory: string;
    sub_subcategory: string;
  }): Promise<{
    status: string;
    message: string;
    products_updated: number;
    from: string;
    to: string;
  }> {
    const query = new URLSearchParams();
    query.append('category', params.category);
    query.append('subcategory', params.subcategory);
    query.append('sub_subcategory', params.sub_subcategory);

    return this.fetch(`/category-seo/swap-level2-level3?${query.toString()}`, {
      method: 'POST'
    });
  }

  /** Đổi tên danh mục cấp 2 hoặc cấp 3 */
  async renameCategory(params: {
    level: 2 | 3;
    category: string;
    subcategory?: string;
    sub_subcategory?: string;
    new_name: string;
  }): Promise<{
    status: string;
    message: string;
    products_updated: number;
  }> {
    const query = new URLSearchParams();
    query.append('level', String(params.level));
    query.append('category', params.category);
    if (params.subcategory) query.append('subcategory', params.subcategory);
    if (params.sub_subcategory) query.append('sub_subcategory', params.sub_subcategory);
    query.append('new_name', params.new_name);

    return this.fetch(`/category-seo/rename-category?${query.toString()}`, {
      method: 'POST'
    });
  }

  /** Tạo lại SEO body cho danh mục */
  async generateSeoBodies(params?: {
    force?: boolean;
    dry_run?: boolean;
    path?: string;
    delay?: number;
  }): Promise<any> {
    const query = new URLSearchParams();
    if (params?.force) query.append('force', 'true');
    if (params?.dry_run) query.append('dry_run', 'true');
    if (params?.path) query.append('path', params.path);
    if (params?.delay !== undefined) query.append('delay', String(params.delay));

    return this.fetch(`/category-seo/seo-bodies/generate?${query.toString()}`, {
      method: 'POST'
    });
  }

  /** Lấy trạng thái chạy SEO body */
  async getSeoBodiesStatus(): Promise<any> {
    return this.fetch(`/category-seo/seo-bodies/status`);
  }

  /** Cài đặt chế độ tự động / tay (Gemini danh mục sau import API) — lưu DB */
  async getCategorySeoAppSettings(): Promise<{
    gemini_auto_enabled_admin: boolean;
    env_allows_gemini_auto: boolean;
    gemini_auto_effective: boolean;
    gemini_whitelist_only_env: boolean;
  }> {
    return this.fetch(`/category-seo/app-settings`);
  }

  async putCategorySeoAppSettings(payload: { gemini_auto_enabled: boolean }): Promise<any> {
    return this.fetch(`/category-seo/app-settings`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  }

  /** Catalog danh mục + thống kê Gemini đích */
  async getGeminiTargetsCatalog(): Promise<any> {
    return this.fetch(`/category-seo/gemini-targets/catalog`);
  }

  /** Bật/tắt danh mục trong whitelist Gemini SEO */
  async setGeminiTargets(payload: { paths: string[]; enabled: boolean }): Promise<{ status: string; affected: number }> {
    return this.fetch(`/category-seo/gemini-targets`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  }

  /** Chạy Gemini meta description + seo_body cho paths (hoặc toàn bộ whitelist nếu paths rỗng) */
  async runGeminiTargets(payload?: {
    paths?: string[];
    force_description?: boolean;
    force_body?: boolean;
    delay?: number;
  }): Promise<any> {
    return this.fetch(`/category-seo/gemini-targets/run`, {
      method: 'POST',
      body: JSON.stringify(payload || {}),
    });
  }

  async getGeminiTargetsJobStatus(): Promise<any> {
    return this.fetch(`/category-seo/gemini-targets/status`);
  }

  /** Lấy danh sách rules */
  async getCategoryRules(): Promise<{ total: number; rules: any[] }> {
    return this.fetch(`/category-seo/rules`);
  }

  /** Tạo rule mới */
  async createCategoryRule(params: {
    rule_type: string;
    level?: number;
    category: string;
    subcategory?: string;
    sub_subcategory?: string;
    source_subcategories?: string[];
    target_name?: string;
  }): Promise<{ status: string; rule_id: number }> {
    const query = new URLSearchParams();
    query.append('rule_type', params.rule_type);
    if (params.level !== undefined) query.append('level', String(params.level));
    query.append('category', params.category);
    if (params.subcategory) query.append('subcategory', params.subcategory);
    if (params.sub_subcategory) query.append('sub_subcategory', params.sub_subcategory);
    if (params.source_subcategories && params.source_subcategories.length > 0) {
      query.append('source_subcategories', params.source_subcategories.join(','));
    }
    if (params.target_name) query.append('target_name', params.target_name);
    return this.fetch(`/category-seo/rules?${query.toString()}`, { method: 'POST' });
  }

  /** Cập nhật rule */
  async updateCategoryRule(ruleId: number, payload: any): Promise<{ status: string; rule_id: number }> {
    return this.fetch(`/category-seo/rules/${ruleId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  }

  /** Xóa rule */
  async deleteCategoryRule(ruleId: number): Promise<{ status: string }> {
    return this.fetch(`/category-seo/rules/${ruleId}`, { method: 'DELETE' });
  }

  /** Áp dụng rule cho sản phẩm cũ */
  async applyCategoryRules(): Promise<{ status: string; updated: number }> {
    return this.fetch(`/category-seo/rules/apply`, { method: 'POST' });
  }

  /** Export rules */
  async exportCategoryRules(): Promise<{ rules: any[] }> {
    return this.fetch(`/category-seo/rules/export`);
  }

  /** Import rules */
  async importCategoryRules(payload: { rules: any[]; replace?: boolean }): Promise<{ status: string; created: number; replaced: boolean }> {
    const query = new URLSearchParams();
    if (payload.replace) query.append('replace', 'true');
    return this.fetch(`/category-seo/rules/import?${query.toString()}`, {
      method: 'POST',
      body: JSON.stringify({ rules: payload.rules }),
    });
  }

  /** Lấy mapping đầu→cuối */
  async getFinalMappings(): Promise<{ total: number; mappings: any[] }> {
    return this.fetch(`/category-seo/mappings-final`);
  }

  /** Tạo mapping */
  async createFinalMapping(payload: any): Promise<{ status: string; mapping_id: number; products_updated?: number }> {
    return this.fetch(`/category-seo/mappings-final`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  /** Cập nhật mapping */
  async updateFinalMapping(id: number, payload: any): Promise<{ status: string; mapping_id: number; products_updated?: number }> {
    return this.fetch(`/category-seo/mappings-final/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  }

  /** Xóa mapping */
  async deleteFinalMapping(id: number): Promise<{ status: string }> {
    return this.fetch(`/category-seo/mappings-final/${id}`, { method: 'DELETE' });
  }

  /** Áp dụng mapping cho sản phẩm cũ */
  async applyFinalMappings(): Promise<{
    status: string;
    updated: number;
    category_ids_resynced?: number;
  }> {
    return this.fetch(`/category-seo/mappings-final/apply`, { method: 'POST' });
  }

  /** Gán lại category_id (FK cat3) từ 3 cột tên — cluster `/c/<slug>` đếm SP theo FK */
  async resyncFinalMappingProductCategoryIds(isActiveOnly = true): Promise<{
    status: string;
    products_updated: number;
  }> {
    const sp = new URLSearchParams();
    if (!isActiveOnly) sp.set('is_active_only', 'false');
    const q = sp.toString();
    return this.fetch(`/category-seo/mappings-final/resync-product-category-ids${q ? `?${q}` : ''}`, {
      method: 'POST',
    });
  }

  /** Export mapping */
  async exportFinalMappings(): Promise<{ mappings: any[] }> {
    return this.fetch(`/category-seo/mappings-final/export`);
  }

  /** Import mapping */
  async importFinalMappings(payload: { mappings: any[]; replace?: boolean }): Promise<{
    status: string;
    created: number;
    replaced: boolean;
    products_updated?: number;
    category_ids_resynced?: number;
  }> {
    const query = new URLSearchParams();
    if (payload.replace) query.append('replace', 'true');
    return this.fetch(`/category-seo/mappings-final/import?${query.toString()}`, {
      method: 'POST',
      body: JSON.stringify({ mappings: payload.mappings }),
    });
  }

  /** Gộp các danh mục cấp 2 */
  async mergeLevel2Categories(params: {
    category: string;
    source_subcategories: string[];
    target_subcategory?: string;
    new_target_name?: string;
  }): Promise<{
    status: string;
    message: string;
    products_updated: number;
    merged_categories: string[];
    target_category: string;
  }> {
    const query = new URLSearchParams();
    query.append('category', params.category);
    params.source_subcategories.forEach(sub => {
      query.append('source_subcategories', sub);
    });
    if (params.target_subcategory) {
      query.append('target_subcategory', params.target_subcategory);
    }
    if (params.new_target_name) {
      query.append('new_target_name', params.new_target_name);
    }
    
    return this.fetch(`/category-seo/merge-level2?${query.toString()}`, {
      method: 'POST'
    });
  }

  /** Gộp các danh mục cấp 3 */
  async mergeLevel3Categories(params: {
    category: string;
    subcategory: string;
    source_sub_subcategories: string[];
    target_sub_subcategory?: string;
    new_target_name?: string;
  }): Promise<{
    status: string;
    message: string;
    products_updated: number;
    merged_categories: string[];
    target_category: string;
  }> {
    const query = new URLSearchParams();
    query.append('category', params.category);
    query.append('subcategory', params.subcategory);
    params.source_sub_subcategories.forEach(sub => {
      query.append('source_sub_subcategories', sub);
    });
    if (params.target_sub_subcategory) {
      query.append('target_sub_subcategory', params.target_sub_subcategory);
    }
    if (params.new_target_name) {
      query.append('new_target_name', params.new_target_name);
    }
    
    return this.fetch(`/category-seo/merge-level3?${query.toString()}`, {
      method: 'POST'
    });
  }

  // NOTIFICATIONS
  async getMyNotifications(skip = 0, limit = 100): Promise<any[]> {
    return this.fetch<any[]>(`/notifications/?skip=${skip}&limit=${limit}`);
  }

  async getUnreadNotificationCount(): Promise<number> {
    return this.fetch<number>('/notifications/unread-count');
  }

  async markNotificationAsRead(id: number): Promise<any> {
    return this.fetch(`/notifications/${id}/read`, { method: 'PUT' });
  }

  async markAllNotificationsAsRead(): Promise<any> {
    return this.fetch('/notifications/read-all', { method: 'PUT' });
  }

  async getPushVapidKey(): Promise<{ public_key: string }> {
    return this.fetch<{ public_key: string }>('/push/vapid-public-key', { method: 'GET' });
  }

  async registerPushSubscription(body: {
    endpoint: string;
    keys: { p256dh: string; auth: string };
    user_agent?: string;
  }): Promise<{ ok: boolean; message?: string }> {
    return this.fetch('/push/subscribe', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async unregisterPushSubscription(endpoint: string): Promise<{ ok: boolean }> {
    return this.fetch('/push/unsubscribe', {
      method: 'POST',
      body: JSON.stringify({ endpoint }),
    });
  }

  async importNotifications(file: File): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const response = await fetch(`${getApiBaseUrl()}/notifications/import`, {
      method: 'POST',
      headers,
      body: formData
    });

    if (!response.ok) {
      const errorText = await response.text();
      let errorData;
      try {
        errorData = JSON.parse(errorText);
      } catch {
        errorData = { detail: errorText };
      }
      throw new Error(errorData.detail || errorText);
    }
    return await response.json();
  }

  /** Tìm sản phẩm theo ảnh (proxy backend → NanoAI; không gửi khóa NanoAI từ trình duyệt). */
  async nanoaiImageSearch(file: File, limit = NANOAI_IMAGE_SEARCH_LIMIT): Promise<NanoaiSearchResponse> {
    const url = `${getApiBaseUrl()}/nanoai/image-search`;
    const headers: Record<string, string> = { ...ngrokFetchHeaders() };
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const guestSid = typeof window !== 'undefined' ? getGuestSessionId() : null;
    if (guestSid) headers['X-Guest-Session-Id'] = guestSid;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('limit', String(limit));

    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: formData,
      credentials: 'include',
    });
    const raw = await response.text();
    let data: unknown;
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch {
      data = { detail: raw || `HTTP ${response.status}` };
    }
    if (!response.ok) {
      const d = data as { detail?: string | string[]; error?: string };
      const detail = d.detail;
      const msg =
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
            ? detail.join(', ')
            : d.error || `Lỗi ${response.status}`;
      throw new Error(msg);
    }
    const out = data as NanoaiSearchResponse;
    if (!Array.isArray(out.products)) {
      out.products = [];
    }
    return out;
  }

  /**
   * Tìm sản phẩm theo chữ (vector NanoAI) — proxy backend; `q` tối thiểu 2 ký tự trên server.
   * `limit` tối đa 100 (khớp backend); số thẻ hiển thị = độ dài `products` trả về; lazy load chỉ bóc dần danh sách đã tải.
   */
  async nanoaiTextSearch(q: string, limit = NANOAI_TEXT_SEARCH_LIMIT): Promise<NanoaiSearchResponse> {
    const trimmed = (q || '').trim();
    if (trimmed.length < 2) {
      return { ok: true, products: [], error: null };
    }
    return this.fetch<NanoaiSearchResponse>('/nanoai/text-search', {
      method: 'POST',
      body: JSON.stringify({ q: trimmed, limit }),
    });
  }
}

export const apiClient = new ApiClient();