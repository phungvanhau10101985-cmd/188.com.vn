/**
 * Admin API client - dùng admin_token (Bearer) cho các endpoint /api/v1/orders/admin/*
 */
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1';

function getAdminToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('admin_token');
}

async function fetchAdmin<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = getAdminToken();
  if (!token) {
    throw new Error('Chưa đăng nhập admin');
  }
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    ...(options.headers as Record<string, string>),
  };
  if (!headers['Content-Type']) headers['Content-Type'] = 'application/json';
  const res = await fetch(url, { ...options, headers });
  if (res.status === 401) {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('admin_token');
      window.location.href = '/admin/login';
    }
    throw new Error('Phiên đăng nhập hết hạn');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Lỗi ${res.status}`);
  }
  if (res.status === 204) return {} as T;
  return res.json();
}

export interface AdminOrderItem {
  id: number;
  product_name: string;
  quantity: number;
  unit_price: number;
  total_price: number;
}

export interface AdminOrder {
  id: number;
  order_code: string;
  customer_name: string;
  customer_phone: string;
  customer_address?: string;
  total_amount: number;
  status: string;
  payment_status: string;
  requires_deposit: boolean;
  deposit_amount: number;
  deposit_paid: number;
  created_at: string;
  items: AdminOrderItem[];
}

export interface AdminOrderStats {
  total_orders: number;
  total_revenue: number;
  pending_orders: number;
  waiting_deposit_orders: number;
  deposit_paid_orders: number;
  confirmed_orders: number;
  processing_orders: number;
  shipping_orders: number;
  delivered_orders: number;
  completed_orders: number;
  cancelled_orders: number;
}

export interface PaymentRecord {
  id: number;
  payment_code: string;
  order_id: number;
  amount: number;
  payment_status: string;
  created_at?: string;
}

export interface AdminProduct {
  id: number;
  product_id: string;
  code?: string;
  name: string;
  slug?: string;
  price: number;
  brand_name?: string;
  category?: string;
  subcategory?: string;
  main_image?: string;
  available?: number;
  is_active?: boolean;
  deposit_require?: boolean;
  description?: string;
  [key: string]: unknown;
}

export interface AdminProductsResponse {
  total: number;
  products: AdminProduct[];
  page: number;
  size: number;
  total_pages: number;
}

export interface AdminSearchMapping {
  id: number;
  keyword_input: string;
  keyword_target: string;
  type: 'product_search' | 'category_redirect';
  hit_count: number;
  created_at?: string;
  updated_at?: string;
}

export interface AdminSearchMappingsResponse {
  items: AdminSearchMapping[];
  total: number;
  page: number;
  size: number;
  total_pages: number;
}

export interface AdminSearchMappingCreateRequest {
  keyword_input: string;
  keyword_target: string;
  type: 'product_search' | 'category_redirect';
}

export const adminProductAPI = {
  getProducts: (params?: { skip?: number; limit?: number; q?: string; product_id?: string }) => {
    const sp = new URLSearchParams();
    sp.set('skip', String(params?.skip ?? 0));
    sp.set('limit', String(params?.limit ?? 100));
    if (params?.q) sp.set('q', params.q);
    if (params?.product_id) sp.set('product_id', params.product_id);
    return fetchAdmin<AdminProductsResponse>(`/products/?${sp.toString()}`);
  },

  updateProduct: (productId: string, data: Partial<AdminProduct>) =>
    fetchAdmin<AdminProduct>(`/products/${encodeURIComponent(productId)}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteProduct: (productId: string) =>
    fetchAdmin<AdminProduct>(`/products/${encodeURIComponent(productId)}`, { method: 'DELETE' }),

  importExcel: async (file: File, overwrite = false) => {
    const token = getAdminToken();
    if (!token) throw new Error('Chưa đăng nhập admin');
    const form = new FormData();
    form.append('file', file);
    const url = `${API_BASE}/import-export/import/excel?overwrite=${overwrite}`;
    const res = await fetch(url, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Import lỗi ${res.status}`);
    }
    return res.json();
  },

  exportExcel: async () => {
    const token = getAdminToken();
    if (!token) throw new Error('Chưa đăng nhập admin');
    const url = `${API_BASE}/import-export/export/excel?download=true`;
    const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) throw new Error('Export thất bại');
    const blob = await res.blob();
    const disposition = res.headers.get('Content-Disposition');
    const match = disposition?.match(/filename="?([^";]+)"?/);
    const filename = match ? match[1] : `export_products_${Date.now()}.xlsx`;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  },

  /** Tải file Excel mẫu để import sản phẩm (36 cột) */
  downloadSampleTemplate: async () => {
    const token = getAdminToken();
    if (!token) throw new Error('Chưa đăng nhập admin');
    const url = `${API_BASE}/import-export/download/sample`;
    const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Tải file mẫu thất bại');
    }
    const blob = await res.blob();
    const disposition = res.headers.get('Content-Disposition');
    const match = disposition?.match(/filename="?([^";]+)"?/);
    const filename = match ? match[1] : 'sample_import_template.xlsx';
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  },
};

export const adminSearchMappingAPI = {
  getMappings: (params?: { skip?: number; limit?: number; keyword?: string; mapping_type?: string }) => {
    const sp = new URLSearchParams();
    sp.set('skip', String(params?.skip ?? 0));
    sp.set('limit', String(params?.limit ?? 50));
    if (params?.keyword) sp.set('keyword', params.keyword);
    if (params?.mapping_type) sp.set('mapping_type', params.mapping_type);
    return fetchAdmin<AdminSearchMappingsResponse>(`/admin/search-mappings?${sp.toString()}`);
  },

  deleteMapping: (mappingId: number) =>
    fetchAdmin<void>(`/admin/search-mappings/${mappingId}`, { method: 'DELETE' }),

  createMapping: (payload: AdminSearchMappingCreateRequest) =>
    fetchAdmin<AdminSearchMapping>(`/admin/search-mappings`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

export const adminOrderAPI = {
  getAllOrders: (params?: { status?: string; limit?: number; skip?: number }) => {
    const sp = new URLSearchParams();
    if (params?.status) sp.set('status', params.status);
    if (params?.limit) sp.set('limit', String(params.limit));
    if (params?.skip) sp.set('skip', String(params.skip ?? 0));
    return fetchAdmin<AdminOrder[]>(`/orders/admin/all?${sp.toString()}`);
  },

  getStats: (period: 'today' | 'week' | 'month' | 'year' | 'all' = 'today') =>
    fetchAdmin<AdminOrderStats>(`/orders/admin/stats?period=${period}`),

  updateOrder: (orderId: number, data: { status?: string }) =>
    fetchAdmin<AdminOrder>(`/orders/admin/${orderId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  getOrderPayments: (orderId: number) =>
    fetchAdmin<PaymentRecord[]>(`/orders/admin/${orderId}/payments`),

  confirmDeposit: (orderId: number, data: { payment_id: number; is_confirmed: boolean; confirmation_note?: string }) =>
    fetchAdmin<AdminOrder>(`/orders/admin/${orderId}/confirm-deposit`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** Xác nhận cọc khi chưa có giao dịch trong hệ thống (khách đã chuyển khoản) */
  confirmDepositManual: (orderId: number, data?: { confirmation_note?: string }) =>
    fetchAdmin<AdminOrder>(`/orders/admin/${orderId}/confirm-deposit-manual`, {
      method: 'POST',
      body: JSON.stringify(data || {}),
    }),
};

export interface BankAccountAdmin {
  id: number;
  bank_name: string;
  account_number: string;
  account_holder: string;
  bank_code?: string | null;
  qr_template_url?: string | null;
  branch?: string | null;
  note?: string | null;
  is_active: boolean;
  sort_order: number;
}

export interface SiteEmbedCodeAdmin {
  id: number;
  platform: string;
  category: string;
  title: string;
  placement: string;
  content: string;
  hint?: string | null;
  is_active: boolean;
  sort_order: number;
  /** Conversion API: token đã lưu nhưng không trả về nội dung thật */
  secret_configured?: boolean;
}

export const adminSiteEmbedAPI = {
  getAll: () => fetchAdmin<SiteEmbedCodeAdmin[]>('/admin/site-embed-codes'),
  create: (data: {
    platform: string;
    category?: string;
    title: string;
    placement: string;
    content?: string;
    hint?: string | null;
    is_active?: boolean;
    sort_order?: number;
  }) =>
    fetchAdmin<SiteEmbedCodeAdmin>('/admin/site-embed-codes', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  update: (id: number, data: Partial<Omit<SiteEmbedCodeAdmin, 'id'>>) =>
    fetchAdmin<SiteEmbedCodeAdmin>(`/admin/site-embed-codes/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  delete: (id: number) => fetchAdmin<void>(`/admin/site-embed-codes/${id}`, { method: 'DELETE' }),
};

export const adminBankAPI = {
  getAll: () => fetchAdmin<BankAccountAdmin[]>('/admin/bank-accounts/all'),
  create: (data: {
    bank_name: string;
    account_number: string;
    account_holder: string;
    bank_code?: string | null;
    qr_template_url?: string | null;
    branch?: string;
    note?: string;
    is_active?: boolean;
    sort_order?: number;
  }) => fetchAdmin<BankAccountAdmin>('/admin/bank-accounts/', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: number, data: Partial<BankAccountAdmin>) =>
    fetchAdmin<BankAccountAdmin>(`/admin/bank-accounts/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id: number) => fetchAdmin<void>(`/admin/bank-accounts/${id}`, { method: 'DELETE' }),
};

export interface AdminMember {
  id: number;
  phone: string;
  email?: string | null;
  full_name?: string | null;
  date_of_birth: string;
  gender?: string | null;
  address?: string | null;
  avatar?: string | null;
  is_active: boolean;
  is_verified: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  last_login?: string | null;
}

export interface AdminMembersResponse {
  items: AdminMember[];
  total: number;
}

export const adminMemberAPI = {
  getMembers: (params?: { skip?: number; limit?: number; keyword?: string }) => {
    const sp = new URLSearchParams();
    sp.set('skip', String(params?.skip ?? 0));
    sp.set('limit', String(params?.limit ?? 50));
    if (params?.keyword?.trim()) sp.set('keyword', params.keyword.trim());
    return fetchAdmin<AdminMembersResponse>(`/admin/users?${sp.toString()}`);
  },
  getMember: (id: number) => fetchAdmin<AdminMember>(`/admin/users/${id}`),
  updateMember: (id: number, data: { is_active?: boolean; full_name?: string; email?: string; address?: string }) =>
    fetchAdmin<AdminMember>(`/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
};

export interface ProductQuestionAdmin {
  id: number;
  user_name: string;
  content: string;
  group: number;
  product_id: number | null;
  product_slug?: string | null;
  useful: number;
  reply_admin_name?: string;
  reply_admin_content?: string;
  reply_admin_at?: string | null;
  reply_user_one_id?: number | null;
  reply_user_one_name?: string;
  reply_user_one_content?: string;
  reply_user_one_at?: string | null;
  reply_user_two_id?: number | null;
  reply_user_two_name?: string;
  reply_user_two_content?: string;
  reply_user_two_at?: string | null;
  reply_count: number;
  is_active: boolean;
  is_imported?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProductQuestionsListResponse {
  items: ProductQuestionAdmin[];
  total: number;
  skip: number;
  limit: number;
}

export const adminProductQuestionsAPI = {
  getList: (params?: {
    skip?: number;
    limit?: number;
    group?: number;
    product_id?: number;
    search_group?: string;
    sort_by?: string;
    sort_desc?: boolean;
  }) => {
    const sp = new URLSearchParams();
    sp.set('skip', String(params?.skip ?? 0));
    sp.set('limit', String(params?.limit ?? 10));
    if (params?.group != null) sp.set('group', String(params.group));
    if (params?.product_id != null) sp.set('product_id', String(params.product_id));
    if (params?.search_group) sp.set('search_group', params.search_group);
    if (params?.sort_by) sp.set('sort_by', params.sort_by);
    if (params?.sort_desc !== undefined) sp.set('sort_desc', String(params.sort_desc));
    return fetchAdmin<ProductQuestionsListResponse>(`/product-questions/admin/list?${sp.toString()}`);
  },

  getOne: (id: number) => fetchAdmin<ProductQuestionAdmin>(`/product-questions/admin/${id}`),

  create: (data: Partial<ProductQuestionAdmin>) =>
    fetchAdmin<ProductQuestionAdmin>('/product-questions/admin/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: number, data: Partial<ProductQuestionAdmin>) =>
    fetchAdmin<ProductQuestionAdmin>(`/product-questions/admin/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (id: number) =>
    fetchAdmin<{ message: string }>(`/product-questions/admin/${id}`, { method: 'DELETE' }),

  importExcel: async (file: File) => {
    const token = getAdminToken();
    if (!token) throw new Error('Chưa đăng nhập admin');
    const form = new FormData();
    form.append('file', file);
    const url = `${API_BASE}/product-questions/admin/import/excel`;
    const res = await fetch(url, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Import thất bại');
    }
    return res.json();
  },

  /** Tải file Excel mẫu (cần gọi với token, trigger download ở client). */
  downloadSampleExcel: async () => {
    const token = getAdminToken();
    if (!token) throw new Error('Chưa đăng nhập admin');
    const url = `${API_BASE}/product-questions/admin/export/sample`;
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Không tải được file mẫu');
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'cau_hoi_san_pham_mau.xlsx';
    a.click();
    URL.revokeObjectURL(a.href);
  },
};

export interface ProductReviewAdmin {
  id: number;
  user_name: string;
  star: number;
  title: string;
  content: string;
  group: number;
  product_id: number | null;
  product_slug?: string | null;
  useful: number;
  reply_name?: string;
  reply_content?: string;
  reply_at?: string | null;
  images?: string[];
  is_active: boolean;
  is_imported?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProductReviewsListResponse {
  items: ProductReviewAdmin[];
  total: number;
  skip: number;
  limit: number;
}

export const adminProductReviewsAPI = {
  getList: (params?: { skip?: number; limit?: number }) => {
    const sp = new URLSearchParams();
    sp.set('skip', String(params?.skip ?? 0));
    sp.set('limit', String(params?.limit ?? 10));
    return fetchAdmin<ProductReviewsListResponse>(`/product-reviews/admin/list?${sp.toString()}`);
  },

  update: (id: number, data: Partial<ProductReviewAdmin>) =>
    fetchAdmin<ProductReviewAdmin>(`/product-reviews/admin/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (id: number) =>
    fetchAdmin<{ message: string }>(`/product-reviews/admin/${id}`, { method: 'DELETE' }),

  importExcel: async (file: File) => {
    const token = getAdminToken();
    if (!token) throw new Error('Chưa đăng nhập admin');
    const form = new FormData();
    form.append('file', file);
    const url = `${API_BASE}/product-reviews/admin/import/excel`;
    const res = await fetch(url, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Import thất bại');
    }
    return res.json();
  },

  downloadSampleExcel: async () => {
    const token = getAdminToken();
    if (!token) throw new Error('Chưa đăng nhập admin');
    const url = `${API_BASE}/product-reviews/admin/export/sample`;
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Không tải được file mẫu');
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'danh_gia_san_pham_mau.xlsx';
    a.click();
    URL.revokeObjectURL(a.href);
  },
};

export interface AdminLoyaltyTier {
  id: number;
  name: string;
  min_spend: number;
  discount_percent: number;
  description: string;
}

export const adminLoyaltyAPI = {
  getTiers: () => fetchAdmin<AdminLoyaltyTier[]>('/loyalty/tiers'),
  createTier: (data: Omit<AdminLoyaltyTier, 'id'>) =>
    fetchAdmin<AdminLoyaltyTier>('/loyalty/tiers', { method: 'POST', body: JSON.stringify(data) }),
  updateTier: (id: number, data: Partial<AdminLoyaltyTier>) =>
    fetchAdmin<AdminLoyaltyTier>(`/loyalty/tiers/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteTier: (id: number) =>
    fetchAdmin<void>(`/loyalty/tiers/${id}`, { method: 'DELETE' }),
};

export async function adminLogin(username: string, password: string) {
  const res = await fetch(`${API_BASE}/admin/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Đăng nhập thất bại' }));
    throw new Error(err.detail || 'Đăng nhập thất bại');
  }
  return res.json();
}
