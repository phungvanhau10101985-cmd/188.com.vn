/**
 * Admin API client - dùng admin_token (Bearer) cho các endpoint /api/v1/orders/admin/*
 */
import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';

/** Grep trên trình duyệt (Console): IMPORT_EXCEL_CLIENT */
const IMPORT_EXCEL_CLIENT_TAG = '[IMPORT_EXCEL_CLIENT]';

function logImportExcelClient(stage: string, url: string, err: unknown) {
  console.warn(IMPORT_EXCEL_CLIENT_TAG, stage, url, err instanceof Error ? err.message : err);
}

/**
 * Khi `fetch` báo "Failed to fetch" — thường là lỗi mạng/CORS/mixed content, không phải lỗi JSON từ API.
 * Server: nếu không thấy `[IMPORT_EXCEL] queued` trong log backend thì request chưa tới API.
 */
export function formatImportFetchFailureMessage(
  stage: 'post_async' | 'poll_job' | 'post_sync',
  url: string,
  err: unknown,
): string {
  const msg = err instanceof Error ? err.message : String(err);
  const base = typeof window !== 'undefined' ? getApiBaseUrl() : '';
  if (!/failed to fetch|networkerror|load failed/i.test(msg)) {
    return msg;
  }
  const stepLabel =
    stage === 'post_async'
      ? 'POST …/import/excel/async (tải file)'
      : stage === 'poll_job'
        ? 'GET …/import/excel/job/{id} (poll tiến trình)'
        : 'POST …/import/excel (đồng bộ)';
  let corsHint = '';
  if (typeof window !== 'undefined' && base && url) {
    try {
      const pageHost = window.location.hostname;
      const apiHost = new URL(base).hostname;
      if (
        (pageHost === 'localhost' || pageHost === '127.0.0.1') &&
        apiHost !== pageHost &&
        apiHost !== ''
      ) {
        corsHint =
          'Rất hay gặp: admin chạy trên localhost nhưng API trỏ domain production → trình duyệt chặn CORS → Failed to fetch. Cách xử lý: (1) Trên VPS: thêm http://localhost:3001,http://127.0.0.1:3001 vào BACKEND_CORS_ORIGINS trong .env backend rồi restart pm2; hoặc (2) dev full local: NEXT_PUBLIC_API_BASE_URL=http://localhost:8001/api/v1 và chạy FastAPI cổng 8001.';
      }
    } catch {
      /* ignore URL parse */
    }
  }
  return [
    `Lỗi mạng tại: ${stepLabel}`,
    `(${msg})`,
    url ? `URL: ${url}` : '',
    base ? `API đang dùng: ${base}` : '',
    corsHint ||
      'Hay gặp: trang HTTPS gọi nhầm http://localhost — dùng cùng host /api/v1. Kiểm tra nginx, pm2.',
    'Trên server: pm2 logs … | findstr IMPORT_EXCEL — không có "queued" thì request chưa tới API (thường CORS/mạng).',
  ]
    .filter(Boolean)
    .join('\n');
}

function getAdminToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('admin_token');
}

/** Chuỗi thân thiện từ FastAPI detail (chuỗi | mảng validation) */
function formatFastApiDetail(detail: unknown): string {
  if (detail == null || detail === '') return '';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail))
    return detail
      .map((item) =>
        typeof item === 'object' && item !== null && 'msg' in item
          ? String((item as { msg?: unknown }).msg ?? '')
          : typeof item === 'string'
            ? item
            : JSON.stringify(item),
      )
      .filter(Boolean)
      .join('; ');
  return String(detail);
}

async function fetchAdmin<T>(
  endpoint: string,
  options: RequestInit & { timeoutMs?: number } = {},
): Promise<T> {
  const token = getAdminToken();
  if (!token) {
    throw new Error('Chưa đăng nhập admin');
  }
  const url = endpoint.startsWith('http') ? endpoint : `${getApiBaseUrl()}${endpoint}`;
  const { timeoutMs, signal: userSignal, ...fetchOpts } = options;
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    ...ngrokFetchHeaders(),
    ...(fetchOpts.headers as Record<string, string>),
  };
  if (!headers['Content-Type']) headers['Content-Type'] = 'application/json';

  const ctrl = new AbortController();
  const tid =
    typeof timeoutMs === 'number' && timeoutMs > 0
      ? setTimeout(() => ctrl.abort(), timeoutMs)
      : undefined;
  if (userSignal) {
    if (userSignal.aborted) ctrl.abort();
    else userSignal.addEventListener('abort', () => ctrl.abort(), { once: true });
  }

  try {
    const res = await fetch(url, { ...fetchOpts, headers, signal: ctrl.signal });
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
  } catch (e) {
    const aborted =
      (typeof DOMException !== 'undefined' && e instanceof DOMException && e.name === 'AbortError') ||
      (e instanceof Error && e.name === 'AbortError');
    if (aborted) {
      throw new Error(
        'Hết thời gian chờ server (timeout). API có thể quá tải hoặc pool PostgreSQL đầy — xem pm2 logs 188-api.',
      );
    }
    throw e;
  } finally {
    if (tid !== undefined) clearTimeout(tid);
  }
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

/** Trạng thái import Excel async (GET .../import/excel/job/{id}) */
export interface AdminImportExcelJob {
  job_id: string;
  status: 'queued' | 'running' | 'done' | 'error';
  phase: string;
  current: number;
  total: number | null;
  percent: number | null;
  message: string;
  created_at?: string;
  finished_at?: string | null;
  result?: {
    success?: boolean;
    message?: string;
    data?: {
      created: number;
      updated: number;
      total_processed: number;
      success_rate?: string;
      file_name?: string;
      import_time?: string;
    };
    warnings?: string[];
    errors?: string[];
  } | null;
  detail?: string | null;
  /** Kèm detail khi lỗi (dòng trong file / traceback rút gọn) */
  errors?: string[] | null;
  warnings?: string[] | null;
  total_rows?: number | null;
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

/** Upload multipart, chờ 202 + JSON — có xhr.upload progress (fetch không báo %). */
function postImportExcelAsyncMultipart(
  url: string,
  token: string,
  file: File,
  onUploadProgress?: (loaded: number, total: number) => void,
): Promise<{ job_id: string; message?: string; poll_url?: string }> {
  const form = new FormData();
  form.append('file', file);
  const ng = ngrokFetchHeaders();

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    xhr.timeout = 35 * 60 * 1000;
    xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    Object.entries(ng).forEach(([k, v]) => {
      if (v) xhr.setRequestHeader(k, v);
    });

    let lastLoaded = 0;
    let lastActivity = Date.now();
    /** Nếu không còn byte nào được gửi trong ~90s nhưng chưa xong → rất hay do nginx client_body_timeout (~60s). */
    const stallIv = window.setInterval(() => {
      if (xhr.readyState === XMLHttpRequest.DONE) {
        clearInterval(stallIv);
        return;
      }
      const idle = Date.now() - lastActivity;
      if (idle >= 90000 && lastLoaded > 0 && lastLoaded < file.size) {
        console.warn(
          IMPORT_EXCEL_CLIENT_TAG,
          'upload_idle — không có byte mới',
          Math.round(idle / 1000),
          's @',
          Math.round((lastLoaded / file.size) * 100),
          '% — kiểm tra nginx client_body_timeout / mạng',
        );
        lastActivity = Date.now();
      }
    }, 15000);

    const cleanup = () => clearInterval(stallIv);

    xhr.upload.onprogress = (ev) => {
      lastLoaded = ev.loaded;
      lastActivity = Date.now();
      if (ev.lengthComputable && onUploadProgress && ev.total > 0) {
        onUploadProgress(ev.loaded, ev.total);
      }
    };

    xhr.onload = () => {
      cleanup();
      try {
        const text = xhr.responseText || '';
        const data = text ? (JSON.parse(text) as { detail?: unknown; job_id?: string }) : {};
        if (xhr.status === 202 && data.job_id) {
          resolve(data as { job_id: string; message?: string; poll_url?: string });
          return;
        }
        const detail = formatFastApiDetail(data?.detail ?? data);
        reject(new Error(detail || `Import lỗi ${xhr.status}`));
      } catch {
        reject(new Error(`Phản hồi không hợp lệ (${xhr.status})`));
      }
    };

    xhr.onerror = () => {
      cleanup();
      logImportExcelClient('post_async', url, new Error('xhr network error'));
      reject(new Error(formatImportFetchFailureMessage('post_async', url, new Error('Failed to fetch'))));
    };

    xhr.ontimeout = () => {
      cleanup();
      reject(
        new Error(
          'Hết thời gian chờ upload (35 phút). Kiểm tra mạng và nginx (proxy_read_timeout, client_max_body_size, client_body_timeout).',
        ),
      );
    };

    xhr.send(form);
  });
}

/** Timeout danh sách SP admin — tránh treo "Đang tải..." khi API/pool DB chờ quá lâu */
const ADMIN_PRODUCTS_LIST_TIMEOUT_MS = 120_000;

export const adminProductAPI = {
  getProducts: (params?: { skip?: number; limit?: number; q?: string; product_id?: string }) => {
    const sp = new URLSearchParams();
    sp.set('skip', String(params?.skip ?? 0));
    sp.set('limit', String(params?.limit ?? 100));
    if (params?.q) sp.set('q', params.q);
    if (params?.product_id) sp.set('product_id', params.product_id);
    return fetchAdmin<AdminProductsResponse>(`/products/?${sp.toString()}`, {
      timeoutMs: ADMIN_PRODUCTS_LIST_TIMEOUT_MS,
    });
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
    const url = `${getApiBaseUrl()}/import-export/import/excel?overwrite=${overwrite}`;
    let res: Response;
    try {
      res = await fetch(url, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, ...ngrokFetchHeaders() },
        body: form,
      });
    } catch (err) {
      logImportExcelClient('post_sync', url, err);
      throw new Error(formatImportFetchFailureMessage('post_sync', url, err));
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(formatFastApiDetail(err?.detail ?? err) || `Import lỗi ${res.status}`);
    }
    return res.json();
  },

  /**
   * Import lớn: server trả 202 + job_id; dùng getImportExcelJob để poll tiến trình.
   * Dùng XMLHttpRequest để có tiến trình upload (loaded/total); fetch không có %.
   */
  startImportExcelAsync: async (
    file: File,
    overwrite = false,
    onUploadProgress?: (loaded: number, total: number) => void,
  ) => {
    const token = getAdminToken();
    if (!token) throw new Error('Chưa đăng nhập admin');
    const url = `${getApiBaseUrl()}/import-export/import/excel/async?overwrite=${overwrite}`;
    console.info('[IMPORT_EXCEL_CLIENT]', 'post_async_start', {
      url,
      file: file.name,
      bytes: file.size,
    });
    return postImportExcelAsyncMultipart(url, token, file, onUploadProgress);
  },

  getImportExcelJob: async (jobId: string) => {
    const ep = `/import-export/import/excel/job/${encodeURIComponent(jobId)}`;
    const url = `${getApiBaseUrl()}${ep}`;
    try {
      return await fetchAdmin<AdminImportExcelJob>(ep);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (/failed to fetch|networkerror|load failed/i.test(msg)) {
        logImportExcelClient('poll_job', url, err);
        throw new Error(formatImportFetchFailureMessage('poll_job', url, err));
      }
      throw err;
    }
  },

  exportExcel: async () => {
    const token = getAdminToken();
    if (!token) throw new Error('Chưa đăng nhập admin');
    const url = `${getApiBaseUrl()}/import-export/export/excel?download=true`;
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}`, ...ngrokFetchHeaders() },
    });
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
    const url = `${getApiBaseUrl()}/import-export/download/sample`;
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}`, ...ngrokFetchHeaders() },
    });
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

export interface SearchKeywordStatItem {
  keyword: string;
  search_count: number;
  avg_result_count: number;
  ai_processed_count: number;
}

export interface SearchKeywordStatsResponse {
  days: number;
  total_distinct_keywords: number;
  items: SearchKeywordStatItem[];
}

export interface ProductSearchCacheRowItem {
  cache_key: string;
  expires_at: string;
  created_at: string | null;
  response_size_bytes: number;
  hint_query: string | null;
}

export interface ProductSearchCacheListResponse {
  total_rows: number;
  active_rows: number;
  expired_rows: number;
  items: ProductSearchCacheRowItem[];
}

export const adminSearchCacheAPI = {
  getKeywordStats: (params?: { days?: number; skip?: number; limit?: number }) => {
    const sp = new URLSearchParams();
    if (params?.days != null) sp.set('days', String(params.days));
    sp.set('skip', String(params?.skip ?? 0));
    sp.set('limit', String(params?.limit ?? 100));
    return fetchAdmin<SearchKeywordStatsResponse>(`/admin/search-analytics/keywords?${sp.toString()}`);
  },

  getProductCache: (params?: { skip?: number; limit?: number }) => {
    const sp = new URLSearchParams();
    sp.set('skip', String(params?.skip ?? 0));
    sp.set('limit', String(params?.limit ?? 50));
    return fetchAdmin<ProductSearchCacheListResponse>(`/admin/product-search-cache?${sp.toString()}`);
  },

  clearProductCache: (scope: 'expired' | 'all') =>
    fetchAdmin<{ deleted: number; scope: string }>(`/admin/product-search-cache?scope=${scope}`, {
      method: 'DELETE',
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

/** Vị trí FAB «lướt video» (đồng bộ với GET public `/shop-video-fab/public`). */
export interface ShopVideoFabSettings {
  right_mobile_px: number;
  bottom_mobile_px_no_nav: number;
  bottom_mobile_px_with_nav: number;
  right_desktop_px: number;
  bottom_desktop_px: number;
}

export const adminShopVideoFabAPI = {
  get: () => fetchAdmin<ShopVideoFabSettings>('/admin/shop-video-fab-settings'),
  update: (data: ShopVideoFabSettings) =>
    fetchAdmin<ShopVideoFabSettings>('/admin/shop-video-fab-settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
};

export interface BunnyCdnStatus {
  configured: boolean;
  cdn_public_base: string;
  upload_path_prefix: string;
}

export interface BunnyCdnUploadResult {
  public_url: string;
  remote_path: string;
  bytes: number;
}

export const adminBunnyCdnAPI = {
  getStatus: () => fetchAdmin<BunnyCdnStatus>('/admin/bunny-cdn/status'),

  upload: async (file: File, subfolder?: string): Promise<BunnyCdnUploadResult> => {
    const token =
      typeof window !== 'undefined' ? localStorage.getItem('admin_token') : null;
    if (!token) throw new Error('Chưa đăng nhập admin');
    const url = `${getApiBaseUrl()}/admin/bunny-cdn/upload`;
    const form = new FormData();
    form.append('file', file);
    const sf = (subfolder ?? '').trim();
    if (sf) form.append('subfolder', sf);
    const res = await fetch(url, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, ...ngrokFetchHeaders() },
      body: form,
    });
    if (res.status === 401) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('admin_token');
        window.location.href = '/admin/login';
      }
      throw new Error('Phiên đăng nhập hết hạn');
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(formatFastApiDetail(err?.detail ?? err) || `Lỗi ${res.status}`);
    }
    return res.json();
  },
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
  phone?: string | null;
  email?: string | null;
  full_name?: string | null;
  date_of_birth?: string | null;
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
    const url = `${getApiBaseUrl()}/product-questions/admin/import/excel`;
    const res = await fetch(url, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, ...ngrokFetchHeaders() },
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
    const url = `${getApiBaseUrl()}/product-questions/admin/export/sample`;
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}`, ...ngrokFetchHeaders() },
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
    const url = `${getApiBaseUrl()}/product-reviews/admin/import/excel`;
    const res = await fetch(url, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, ...ngrokFetchHeaders() },
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
    const url = `${getApiBaseUrl()}/product-reviews/admin/export/sample`;
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}`, ...ngrokFetchHeaders() },
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
  const res = await fetch(`${getApiBaseUrl()}/admin/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...ngrokFetchHeaders() },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const msg = formatFastApiDetail((err as { detail?: unknown }).detail) || 'Đăng nhập thất bại';
    throw new Error(msg);
  }
  return res.json();
}
