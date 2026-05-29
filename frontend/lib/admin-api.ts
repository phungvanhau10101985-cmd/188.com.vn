/**
 * Admin API client - dùng admin_token (Bearer) cho các endpoint /api/v1/orders/admin/*
 */
import { getApiBaseUrl, getBackendOriginUrl, ngrokFetchHeaders } from '@/lib/api-base';

/** Grep trên trình duyệt (Console): IMPORT_EXCEL_CLIENT */
const IMPORT_EXCEL_CLIENT_TAG = '[IMPORT_EXCEL_CLIENT]';

function logImportExcelClient(stage: string, url: string, err: unknown) {
  console.warn(IMPORT_EXCEL_CLIENT_TAG, stage, url, err instanceof Error ? err.message : err);
}

function getImportExcelUploadApiBaseUrl(): string {
  if (typeof window === 'undefined') return getApiBaseUrl();
  if (window.location.protocol === 'http:' && process.env.NODE_ENV === 'development') {
    return `${getBackendOriginUrl().replace(/\/$/, '')}/api/v1`;
  }
  return getApiBaseUrl();
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
          'Rất hay gặp: admin localhost nhưng API trỏ domain production → CORS → Failed to fetch; hoặc dev gọi thẳng :8001 mà backend chưa chạy. Cách xử lý: (1) VPS: thêm http://localhost:3001 vào BACKEND_CORS_ORIGINS và restart backend; (2) dev local: để Next proxy (getApiBaseUrl() mặc định là cùng host /api/v1) và chạy FastAPI cổng 8001 để rewrite hoạt động; (3) nếu cần gọi trực tiếp :8001: NEXT_PUBLIC_API_NEXT_PROXY=0 và NEXT_PUBLIC_API_BASE_URL=http://localhost:8001/api/v1.';
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

function sanitizeDownloadFilename(name: string): string {
  const n = (name || '').trim() || 'download.bin';
  return n.replace(/[/\\?%*:|"<>]/g, '_');
}

/** Tải thẳng về thư mục Downloads mặc định của trình duyệt, không mở hộp thoại chọn nơi lưu. */
async function triggerBlobDownloadPreferred(blob: Blob, filename: string): Promise<void> {
  const safeName = sanitizeDownloadFilename(filename);
  const w = typeof window !== 'undefined' ? window : undefined;
  if (!w) return;

  const objectUrl = URL.createObjectURL(blob);
  const revokeLater = () => {
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  };

  try {
    const a = document.createElement('a');
    a.href = objectUrl;
    a.download = safeName;
    a.rel = 'noopener noreferrer';
    a.style.display = 'none';
    document.body.appendChild(a);
    a.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: w }));
    document.body.removeChild(a);
  } catch (e) {
    console.warn('[admin-api] anchor download failed, trying window.open(blob)', e);
    try {
      const opened = w.open(objectUrl, '_blank', 'noopener,noreferrer');
      if (!opened) {
        throw new Error('popup blocked');
      }
    } catch {
      URL.revokeObjectURL(objectUrl);
      throw new Error(
        'Trình duyệt chặn tải file sau khi nhận dữ liệu. Thử Chrome/Edge (có hộp thoại Lưu), tắt chặn popup, hoặc kiểm tra HTTPS.',
      );
    }
  }
  revokeLater();
}

async function assertBlobLooksLikeXlsx(blob: Blob): Promise<void> {
  if (blob.size < 64) {
    throw new Error(
      `Phản hồi quá nhỏ (${blob.size} byte). Thường do proxy/nginx trả HTML thay vì Excel — kiểm tra tab Network.`,
    );
  }
  const head = new Uint8Array(await blob.slice(0, 4).arrayBuffer());
  const pk =
    head[0] === 0x50 &&
    head[1] === 0x4b &&
    (head[2] === 0x03 || head[2] === 0x05 || head[2] === 0x07) &&
    (head[3] === 0x04 || head[3] === 0x06 || head[3] === 0x08);
  if (pk) return;
  const snippet = (await blob.slice(0, 500).text()).replace(/\s+/g, ' ').trim().slice(0, 240);
  throw new Error(
    snippet.startsWith('<') || snippet.startsWith('{')
      ? `Không nhận được Excel — có vẻ là HTML/JSON (${snippet.slice(0, 120)}…). Kiểm tra URL API, nginx và phiên đăng nhập admin.`
      : 'Không nhận được file Excel (.xlsx là ZIP). Kiểm tra phản hồi server.',
  );
}

/** Chuỗi thân thiện từ FastAPI detail (chuỗi | mảng validation | object { message }) */
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
  if (typeof detail === 'object' && detail !== null) {
    const o = detail as Record<string, unknown>;
    if (typeof o.message === 'string') return o.message;
    try {
      return JSON.stringify(o, null, 2);
    } catch {
      return String(detail);
    }
  }
  return String(detail);
}

/** Scrape nguồn có thể chạy lâu — phải ≥ timeout proxy/nginx (khuyến nghị 600s+ cho location API). */
export const ADMIN_SOURCE_STOCK_SCAN_TIMEOUT_MS = 660_000;

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
        localStorage.removeItem('admin_role');
        localStorage.removeItem('admin_modules');
        window.location.href = '/admin/login';
      }
      throw new Error('Phiên đăng nhập hết hạn');
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      const msg = formatFastApiDetail((err as { detail?: unknown }).detail) || `Lỗi ${res.status}`;
      const statusHint =
        res.status === 422
          ? '[422] Body JSON cần dạng: {"url":"https://..." , "download_images":true}. '
          : res.status === 504 || res.status === 502
            ? `[${res.status}] Hết giờ chờ proxy (gateway timeout) — request lâu hơn giới hạn nginx/Cloudflare. Cấu hình proxy_read_timeout / timeout ít nhất ${Math.round(
                ADMIN_SOURCE_STOCK_SCAN_TIMEOUT_MS / 60000,
              )} phút cho route API /products/ hoặc thử lại. `
          : res.status === 404
            ? `[404 ${url}] `
            : '';
      throw new Error(statusHint + msg);
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
  product_id?: number;
  product_slug?: string | null;
  product_name: string;
  product_image?: string | null;
  quantity: number;
  unit_price: number;
  total_price: number;
  requires_deposit?: boolean;
  selected_size?: string | null;
  selected_color?: string | null;
  selected_color_name?: string | null;
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
  /** Nhân viên đã liên hệ tư vấn */
  staff_consultation_contacted?: boolean;
  requires_deposit: boolean;
  deposit_amount: number;
  deposit_paid: number;
  deposit_percentage?: number;
  deposit_type?: string | null;
  remaining_amount?: number;
  tracking_number?: string | null;
  shipping_provider?: string | null;
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
  returned_orders: number;
  cancelled_orders: number;
  period_label?: string | null;
  date_from?: string | null;
  date_to?: string | null;
}

export type AdminOrderStatsPreset =
  | 'today'
  | 'this_week'
  | 'last_week'
  | 'this_month'
  | 'last_month';

export type AdminOrderStatsQuery = {
  period?: 'today' | 'week' | 'month' | 'year' | 'all';
  preset?: AdminOrderStatsPreset;
  date?: string;
  year?: number;
  date_from?: string;
  date_to?: string;
};

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
  sub_subcategory?: string;
  main_image?: string;
  /** gallery_images — ảnh thư viện / carousel */
  images?: string[];
  /** detail_images — ảnh mô tả chi tiết SP */
  gallery?: string[];
  available?: number;
  is_active?: boolean;
  deposit_require?: boolean;
  description?: string;
  /** Link nguồn Excel `product_url` — dùng cho kiểm tra tồn 1688. */
  link_default?: string | null;
  /** Cache worker kiểm tra trang chi tiết 1688 (`unknown`, `queued`, …). */
  source_stock_status?: string | null;
  source_stock_checked_at?: string | null;
  source_stock_next_check_at?: string | null;
  source_stock_error?: string | null;
  /** Admin Kiểm tra nguồn (DB): không xếp hàng lại cho đến khi đủ số ngày cooldown */
  admin_source_batch_scanned_at?: string | null;
  image_localization_status?: string | null;
  image_localization_language?: string | null;
  image_localized_at?: string | null;
  image_localization_error?: string | null;
  [key: string]: unknown;
}

export interface AdminProductsResponse {
  total: number;
  products: AdminProduct[];
  page: number;
  size: number;
  total_pages: number;
}

export interface AdminSourceStockBatchOneMatched {
  id: number;
  name: string;
  slug: string;
  product_id: string | null;
}

export interface AdminSourceStockBatchOneResult {
  ok: boolean;
  canonical_url: string;
  domain: string;
  raw_status?: string | null;
  classified_out_of_stock: boolean;
  detail?: string | null;
  warnings?: string[];
  matched_products: AdminSourceStockBatchOneMatched[];
  updated_product_ids: number[];
  matched_count: number;
  updates_committed?: boolean;
  /** Hai nền đều lỗi; backend vẫn ghi mốc lỗi lên SP hàng chờ rồi client dừng lặp. */
  dual_platform_both_failed?: boolean;
  dual_attempts?: Array<{ domain: string; raw_status?: string | null; detail?: string | null }>;
  skipped_after_retry?: boolean;
  alternate_fallback_used?: boolean;
  alternate_failed_domain?: string;
  alternate_sequence_index?: number;
  alternate_primary_domain?: string;
  /** Theo DB: SP hàng chờ được gắn thêm vào nhóm kết quả khi cần neo đúng `products.id`. */
  anchor_included_db_id?: number;
  /** Khi OOS và slug không map nhưng vẫn commit, SP hàng chờ được gắn thêm vào nhóm khớp. */
  oos_commit_included_anchor_db_id?: number;
}

/** Kiểm tra tuần tự từ DB (thêm các trường done / seed). */
export type AdminSourceStockBatchDbNextResult = AdminSourceStockBatchOneResult & {
  done?: boolean;
  cursor_after_product_id: number;
  seed_product_db_id?: number | null;
  seed_product_name?: string | null;
  seed_link_default?: string | null;
  admin_batch_scan_cooldown_days?: number;
  seed_admin_batch_scanned_at?: string | null;
};

export interface AdminSourceStockProductUrlsResponse {
  urls: string[];
  count: number;
  domain_filter: string;
  active_only?: boolean;
}

export interface AdminSourceStockBatchDeleteByDbIdsResult {
  ok: boolean;
  deleted_count: number;
  deleted_db_ids: number[];
  not_found_db_ids: number[];
}

export interface AdminSourceStockQueueStats {
  ok: boolean;
  domain: string;
  active_only: boolean;
  admin_batch_scan_cooldown_days: number;
  admin_batch_traffic_view_window_days?: number;
  admin_batch_traffic_check_gap_days?: number;
  cooldown_cutoff_utc_iso: string;
  traffic_recent_check_cutoff_utc_iso?: string;
  traffic_view_since_utc_iso?: string;
  total_in_scope: number;
  eligible_now: number;
  /** Trong nhóm được xếp hàng ngay — chưa từng đánh batch (scanned_at null) */
  eligible_never_scanned?: number;
  /** Trong nhóm được xếp hàng ngay — đã đánh batch trước đây và đã hết chờ TTL */
  eligible_rescan_after_ttl?: number;
  /** Trong nhóm đến lượt có lượt xem PDP trong cửa sổ traffic */
  eligible_with_recent_customer_view?: number;
  /** Đến lượt, không có lượt xem PDP trong cửa sổ — xử lý theo TTL «thường» */
  eligible_without_recent_customer_view?: number;
  in_cooldown: number;
}

/** Một dòng trong các bảng mẫu báo cáo kiểm tra nguồn (30 ngày). */
export interface AdminSourceStockActivityReportSampleRow {
  id: number;
  product_id: string;
  name: string;
  slug: string;
  link_default: string;
  /** URL trang item CSSBuy sau quy đổi (như batch Excel / worker). */
  link_convert_cssbuy?: string;
  link_convert_cssbuy_err?: string;
  /** URL Hibox scrape sau quy đổi. */
  link_convert_hibox?: string;
  link_convert_hibox_err?: string;
  /** URL Vipomall (gương 1688) sau quy đổi. */
  link_convert_vipomall?: string;
  link_convert_vipomall_err?: string;
  source_stock_status: string | null;
  source_stock_checked_at: string | null;
  /** Nền đã đọc PDP cho kết quả kiểm tra (worker: cssbuy / hibox; batch: cssbuy, hibox, cssbuy+hibox…) */
  source_stock_check_platform?: string | null;
  admin_source_batch_scanned_at: string | null;
  available: number;
}

export interface AdminSourceStockActivityReportCounts {
  batch_ttl_stamped_in_window: number;
  source_stock_checked_any_in_window: number;
  source_stock_oos_signal_in_window: number;
  source_stock_in_stock_signal_in_window: number;
  checked_available_positive_in_window: number;
  checked_available_zero_or_negative_in_window: number;
}

/** Phân trang một nhóm mẫu (API có thể clamp `page` xuống `total_pages`). */
export interface AdminSourceStockReportSamplePaginationSlice {
  page: number;
  total: number;
  total_pages: number;
}

/** Phân trang danh sách mẫu — mỗi nhóm có `page` riêng, `page_size` chung. */
export interface AdminSourceStockSamplesPagination {
  page_size: number;
  oos: AdminSourceStockReportSamplePaginationSlice;
  in_stock: AdminSourceStockReportSamplePaginationSlice;
  batch_ttl_recent: AdminSourceStockReportSamplePaginationSlice;
}

/** Báo cáo rolling N ngày + lặp lại `queue` để đối chiếu hàng chờ. */
export interface AdminSourceStockActivityReport {
  ok: boolean;
  domain: string;
  active_only: boolean;
  window_days: number;
  window_since_utc_iso: string;
  samples_pagination: AdminSourceStockSamplesPagination;
  queue: AdminSourceStockQueueStats;
  counts: AdminSourceStockActivityReportCounts;
  checked_in_window_by_source_stock_status: Record<string, number>;
  samples: {
    oos: AdminSourceStockActivityReportSampleRow[];
    in_stock: AdminSourceStockActivityReportSampleRow[];
    batch_ttl_recent: AdminSourceStockActivityReportSampleRow[];
  };
}

/** Gỡ cờ «hết hàng nguồn» sai từ báo cáo — không xóa sản. */
export interface AdminSourceStockClearOosFlagResult {
  ok: boolean;
  product_db_id: number;
  source_stock_status?: string | null;
  available?: number;
  source_stock_checked_at?: string | null;
  detail?: string;
}

/** Xếp worker PDP kiểm tra lại (force). */
export interface AdminSourceStockForceWorkerRecheckResult {
  ok: boolean;
  product_db_id: number;
  enqueued_now: boolean;
  skip_reason?: string | null;
  source_stock_status?: string | null;
  source_stock_next_check_at?: string | null;
}

/** Thử PDP theo một link — không ghi DB (CSSBuy→Hibox như worker). */
export interface AdminSourceStockPreviewUrlBranch {
  status: string;
  error?: string | null;
  checked_via?: string | null;
}

export interface AdminSourceStockPreviewUrlCoercion {
  cssbuy_url: string;
  cssbuy_coercion_error: string;
  hibox_url: string;
  hibox_coercion_error: string;
  vipomall_url?: string;
  vipomall_coercion_error?: string;
}

export interface AdminSourceStockPreviewUrlResult {
  ok: boolean;
  canonical_input: string;
  link_eligible: boolean;
  coercion: AdminSourceStockPreviewUrlCoercion;
  cssbuy: AdminSourceStockPreviewUrlBranch;
  hibox: AdminSourceStockPreviewUrlBranch;
  vipomall?: AdminSourceStockPreviewUrlBranch;
  merged: AdminSourceStockPreviewUrlBranch;
}

/** Reset PDP source_stock_* trong phạm vi link + domain (bulk). */
export interface AdminSourceStockResetPdpResult {
  ok: boolean;
  domain: string;
  active_only: boolean;
  products_updated: number;
  memory_queue_cleared: number;
  detail?: string;
}

/** Dòng PDP trong snapshot worker (đang làm / vừa xong / sắp tới). */
export interface AdminSourceStockWorkerProgressRow {
  product_db_id: number;
  product_code?: string | null;
  name?: string | null;
  link_default?: string | null;
  checking_started_at_utc_iso?: string | null;
  finished_at_utc_iso?: string | null;
  source_stock_status?: string | null;
  /** Nền đã đọc PDP trong lần kiểm tra gần nhất (snapshot merge từ products). */
  source_stock_check_platform?: string | null;
  queue_hint?: string | null;
  queue_hint_vi?: string | null;
}

export interface AdminSourceStockProductsCommitAudit {
  ok?: boolean | null;
  at_utc_iso?: string | null;
  detail?: string | null;
  product_db_id?: number | null;
  consistency_hint_vi?: string | null;
}

/** Trạng thái worker kiểm tra nguồn (daemon + cờ pause DB). */
export interface AdminSourceStockWorkerState {
  ok: boolean;
  env_source_stock_check_enabled: boolean;
  db_paused: boolean;
  db_pause_updated_at_utc_iso?: string | null;
  daemon_thread_started_flag: boolean;
  daemon_thread_alive: boolean;
  process_in_memory_queue_depth: number;
  check_interval_seconds: number;
  effective_idle_reason: string | null;
  effective_idle_hint_vi?: string | null;
  deployment_notes_vi?: string | null;
  checking?: AdminSourceStockWorkerProgressRow | null;
  last_completed?: AdminSourceStockWorkerProgressRow | null;
  next_upcoming_primary?: AdminSourceStockWorkerProgressRow | null;
  upcoming_candidates?: AdminSourceStockWorkerProgressRow[];
  products_commit_audit?: AdminSourceStockProductsCommitAudit | null;
  progress_notes_vi?: string | null;
}

export interface AdminImageLocalizationJob {
  job_id: string;
  status: 'queued' | 'running' | 'done' | 'error' | 'cancelled';
  phase?: string;
  message?: string;
  current?: number;
  total?: number | null;
  done?: number;
  failed?: number;
  skipped?: number;
  percent?: number | null;
  language?: string;
  gemini_mode?: 'web' | 'api' | 'openai';
  gemini_image_model?: string;
  gemini_image_size?: string;
  openai_image_model?: string;
  openai_image_quality?: string;
  openai_image_size?: string;
  inference_tier?: 'standard' | 'flex';
  allow_ai_image_models?: boolean | null;
  local_image_only?: boolean;
  playwright_headless_requested?: boolean | null;
  playwright_headless_effective?: boolean;
  current_product_id?: string | null;
  /** Snapshot id trong lượt chạy (backend có thể cắt nếu batch rất lớn — xem job_queue_truncated). */
  job_queue_product_ids?: string[];
  job_queue_truncated?: boolean;
  skipped_product_reports?: Array<{
    product_id: string;
    message?: string | null;
  }>;
  recent_results?: Array<{
    product_id: string;
    status: string;
    message?: string;
    processed_images?: number;
  }>;
}

export interface AdminImageLocalizationSummary {
  pending: number;
  localized: number;
  failed: number;
  processing: number;
}

export interface AdminImageLocalizationJobList {
  items: AdminImageLocalizationJob[];
  active_count: number;
}

export interface AdminImageLocalizationReportItem {
  original_url: string;
  final_url?: string | null;
  status: string;
  category: string;
  label_vi: string;
  message: string;
  /** Phần có cấu trúc từ DB (vd. split_parts sau ảnh dài). */
  detail?: Record<string, unknown> | null;
  bucket?: string | null;
  index?: number | null;
}

export interface AdminImageLocalizationReportSummary {
  total: number;
  deleted: number;
  error: number;
  ai_image: number;
  local_draw: number;
  local_pipeline: number;
  processed_other: number;
  kept_cdn: number;
  kept_other: number;
  unknown: number;
}

export interface AdminImageLocalizationProductReport {
  product_id: string;
  db_status?: string | null;
  db_language?: string | null;
  db_error?: string | null;
  report_language?: string | null;
  report_processed_at?: string | null;
  has_report: boolean;
  summary: AdminImageLocalizationReportSummary;
  items: AdminImageLocalizationReportItem[];
}

export interface AdminGeminiAuthBranch {
  ready: boolean;
  cookie_configured?: boolean;
  cookie_count?: number;
  cookies_all_expired?: boolean;
  cookie_expiry_known_for_all?: boolean;
  cookie_deploy_block_reason?: string | null;
  requires_cookie_or_login_marker_for_headless?: boolean;
  profile_marker?: boolean;
  profile_logged_in_marker?: boolean;
  profile_path?: string;
  key_configured?: boolean;
  model?: string;
  inference_tier?: string;
  openai_flex_is_economy_preset?: boolean;
  /** Backend đã bỏ preset Flex/OpenAI tiết kiệm */
  openai_flex_removed?: boolean;
}

export interface AdminGeminiAuthStatus {
  /** false = admin chỉ được pipeline OCR + DeepSeek + vẽ local (Gemini/GPT ảnh tắt trên server). */
  ai_image_jobs_allowed?: boolean;
  default_gemini_mode: 'web' | 'api' | 'openai';
  image_model: string;
  openai_image_model: string;
  gemini_api_image_sizes?: string[];
  openai_image_qualities?: string[];
  openai_image_sizes?: string[];
  inference_tier_options?: string[];
  inference_tier_notes?: Record<string, string>;
  playwright_headless?: boolean;
  playwright_browser_visible?: boolean;
  deploy_browser_help?: string;
  web: AdminGeminiAuthBranch;
  api: AdminGeminiAuthBranch;
  openai: AdminGeminiAuthBranch;
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
      /** Import Excel: số dòng có listed=0 và đã xóa khỏi DB */
      deleted?: number;
      skipped_count?: number;
      total_processed: number;
      success_rate?: string;
      file_name?: string;
      import_time?: string;
    };
    warnings?: string[];
    errors?: string[];
    /** Dòng bỏ qua (trùng id nguồn / SKU kiểu «…a188…») */
    skipped?: string[] | null;
  } | null;
  detail?: string | null;
  /** Kèm detail khi lỗi (dòng trong file / traceback rút gọn) */
  errors?: string[] | null;
  warnings?: string[] | null;
  total_rows?: number | null;
}

export interface AdminImport1688Draft {
  id: number;
  job_id: string;
  source: string;
  source_url: string;
  source_offer_id?: string | null;
  status: string;
  phase?: string | null;
  message?: string | null;
  percent?: number | null;
  raw_payload?: Record<string, unknown> | null;
  product_data?: Partial<AdminProduct> & Record<string, unknown>;
  errors?: string[];
  warnings?: string[];
  published_product_id?: string | null;
  created_at?: string;
  updated_at?: string | null;
  finished_at?: string | null;
}

export interface AdminImport1688Job {
  job_id: string;
  status: 'queued' | 'running' | 'done' | 'error' | 'published' | string;
  phase?: string | null;
  message?: string | null;
  percent?: number | null;
  draft_id?: number | null;
  product_data?: Partial<AdminProduct> & Record<string, unknown>;
  errors?: string[];
  warnings?: string[];
  published_product_id?: string | null;
  created_at?: string;
  finished_at?: string | null;
}

export interface AdminImport1688ExcelBatchStart {
  batch_token: string;
  total: number;
  draft_ids: number[];
  job_ids: string[];
  skipped: string[];
}

export interface AdminImport1688BatchStatusItem {
  draft_id: number;
  job_id: string;
  excel_row?: number | null;
  status: string;
  phase?: string | null;
  message?: string | null;
}

export interface AdminImport1688BatchStatus {
  batch_token: string;
  total: number;
  completed: number;
  failed: number;
  pending: number;
  items: AdminImport1688BatchStatusItem[];
}

/** Một đợt Excel (aggregate), không chứa từng dòng chi tiết. */
export interface AdminImport1688ExcelBatchSummary {
  batch_token: string;
  created_at?: string | null;
  total_links: number;
  completed: number;
  failed: number;
  pending: number;
  skipped_lines: number;
}

export interface AdminImport1688ExcelBatchListResponse {
  items: AdminImport1688ExcelBatchSummary[];
  limit: number;
}

export interface AdminImport1688ExcelBatchDeleteResponse {
  success: boolean;
  batch_token: string;
  draft_ids_deleted: number[];
  meta_removed: boolean;
}

export interface AdminImport1688BatchResumeResponse {
  success: boolean;
  message: string;
  pending: number;
}

export interface AdminListingImportQueueCounts {
  total: number;
  done: number;
  error: number;
  pending: number;
  running: number;
}

export interface AdminListingImportQueueItem {
  id: string;
  url: string;
  source: string;
  label?: string | null;
  chinese_name?: string | null;
  shop_name_chinese?: string | null;
  state: string;
  job_id?: string | null;
  draft_id?: number | null;
  message?: string | null;
  finished_at?: string | null;
}

export interface AdminListingImportQueueStatus {
  queue_token: string;
  created_at?: string | null;
  updated_at?: string | null;
  run_status: string;
  pause_requested: boolean;
  stop_requested: boolean;
  worker_alive: boolean;
  current_item_id?: string | null;
  counts: AdminListingImportQueueCounts;
  items: AdminListingImportQueueItem[];
  can_resume: boolean;
  can_pause: boolean;
  can_stop: boolean;
}

export interface AdminListingImportQueueEnqueueResponse {
  queue_token: string;
  added: number;
  message: string;
}

export interface AdminListingImportQueueRunCounts {
  total: number;
  done: number;
  error: number;
  pending: number;
  running: number;
}

export interface AdminListingImportQueueRunSummary {
  queue_token: string;
  created_at?: string | null;
  updated_at?: string | null;
  run_status?: string;
  pause_requested?: boolean;
  stop_requested?: boolean;
  worker_alive?: boolean;
  counts: AdminListingImportQueueRunCounts;
}

export interface AdminListingImportQueueRunsResponse {
  items: AdminListingImportQueueRunSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdminImport1688DraftListResponse {
  items: AdminImport1688Draft[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdminImport1688CookieSettings {
  enabled: boolean;
  cookie_file?: string | null;
  has_cookie: boolean;
  cookie_count: number;
  cookie_names: string[];
  message?: string | null;
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
      const text = xhr.responseText || '';
      try {
        const data = text ? (JSON.parse(text) as { detail?: unknown; job_id?: string }) : {};
        if (xhr.status === 202 && data.job_id) {
          resolve(data as { job_id: string; message?: string; poll_url?: string });
          return;
        }
        const detail = formatFastApiDetail(data?.detail ?? data);
        reject(new Error(detail || `Import lỗi ${xhr.status}`));
      } catch {
        const snippet = text.replace(/\s+/g, ' ').trim().slice(0, 280);
        reject(
          new Error(
            snippet
              ? `Phản hồi không phải JSON (${xhr.status}): ${snippet}`
              : `Phản hồi không hợp lệ (${xhr.status})`,
          ),
        );
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

export type AdminProductListSort = 'default' | 'views_desc' | 'newest' | 'oldest';

/** Một mục tiêu trong POST /import-export/sync/google-sheet-skus */
export type AdminGoogleSheetSkuSyncTargetResult = {
  ok: boolean;
  field?: string;
  /** full | key_time — backend */
  row_mode?: string;
  sheet_title?: string;
  spreadsheet_id?: string;
  sheet_gid?: number;
  error?: string;
  column_count?: number;
  updated_rows?: number;
  unchanged_rows?: number;
  added_rows?: number;
  removed_orphan_rows?: number;
  removed_duplicate_rows?: number;
  db_key_count?: number;
};

/** Kết quả POST /import-export/sync/google-sheet-skus */
export type AdminGoogleSheetSkuSyncResult = {
  ok: boolean;
  skipped?: boolean;
  /** Một bảng thành công, một bảng lỗi */
  partial?: boolean;
  reason?: string;
  error?: string;
  targets?: AdminGoogleSheetSkuSyncTargetResult[];
  field?: string;
  sheet_title?: string;
  column_count?: number;
  updated_rows?: number;
  unchanged_rows?: number;
  added_rows?: number;
  removed_orphan_rows?: number;
  removed_duplicate_rows?: number;
  db_key_count?: number;
};

export const adminProductAPI = {
  getProducts: (
    params?: {
      skip?: number;
      limit?: number;
      q?: string;
      product_id?: string;
      sort?: AdminProductListSort;
    },
  ) => {
    const sp = new URLSearchParams();
    sp.set('skip', String(params?.skip ?? 0));
    sp.set('limit', String(params?.limit ?? 100));
    if (params?.q) sp.set('q', params.q);
    if (params?.product_id) sp.set('product_id', params.product_id);
    if (params?.sort && params.sort !== 'default') sp.set('sort', params.sort);
    return fetchAdmin<AdminProductsResponse>(`/products/?${sp.toString()}`, {
      timeoutMs: ADMIN_PRODUCTS_LIST_TIMEOUT_MS,
      cache: 'no-store',
    });
  },

  /**
   * Đối chiếu ID parse HTML listing với DB.
   * - Mặc định (như trước): ``products`` + nháp import ``done`` có ``product_data`` — dùng cho lưới «chưa có trên shop».
   * - Modal đăng sau crawl: ``{ includeDoneDrafts: false, productsActiveOnly: true }`` — chỉ SP đang ``is_active`` trên shop.
   */
  listingParserDbPresence: (
    ids: string[],
    opts?: { includeDoneDrafts?: boolean; productsActiveOnly?: boolean },
  ) =>
    fetchAdmin<{ existing_normalized: string[] }>('/products/listing-parser-db-presence', {
      method: 'POST',
      body: JSON.stringify({
        ids,
        include_done_drafts: opts?.includeDoneDrafts ?? true,
        products_active_only: opts?.productsActiveOnly ?? false,
      }),
    }),

  updateProduct: (productId: string, data: Partial<AdminProduct>) =>
    fetchAdmin<AdminProduct>(`/products/${encodeURIComponent(productId)}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteProduct: (productId: string) =>
    fetchAdmin<AdminProduct>(`/products/${encodeURIComponent(productId)}`, { method: 'DELETE' }),

  /** Xếp hàng kiểm tra tình trạng nguồn qua worker scrape Hibox (`SOURCE_STOCK_CHECK_*`). Không chờ worker xong. */
  enqueueSourceStockCheckByDbId: (dbPkId: number) =>
    fetchAdmin<{
      queued: boolean;
      source_stock_status?: string | null;
      source_stock_checked_at?: string | null;
      source_stock_next_check_at?: string | null;
    }>(`/products/by-id/${dbPkId}/source-stock-check/enqueue`, { method: 'POST' }),

  /** Một SP kế trong DB — kiểm tra qua Hibox hoặc CSSBuy. */
  runSourceStockBatchNextFromDb: (params: {
    domain: 'hibox' | 'cssbuy' | 'vipomall';
    activeOnly?: boolean;
    cursorAfterProductId?: number;
    /** products.id — giữ kiểm tra lại đúng SP sau lỗi tạm (captcha/chặn…). */
    stickySeedProductId?: number;
    /** Retry sticky vẫn lỗi thì backend đóng TTL để bỏ qua vòng này. */
    skipStickyAfterFailure?: boolean;
    dualAlternateFallback?: boolean;
    alternateSequenceIndex?: number;
  }) =>
    fetchAdmin<AdminSourceStockBatchDbNextResult>('/products/admin/source-stock-batch/run-next-from-db', {
      method: 'POST',
      body: JSON.stringify({
        domain: params.domain,
        active_only: params.activeOnly ?? true,
        cursor_after_product_id: params.cursorAfterProductId ?? 0,
        sticky_seed_product_id: params.stickySeedProductId ?? 0,
        skip_sticky_after_failure: params.skipStickyAfterFailure ?? false,
        dual_alternate_fallback: params.dualAlternateFallback ?? false,
        alternate_sequence_index: params.alternateSequenceIndex ?? 0,
      }),
      timeoutMs: ADMIN_SOURCE_STOCK_SCAN_TIMEOUT_MS,
    }),

  /** Nạp `link_default` trong DB — lọc theo miền kiểm tra (hibox vs cssbuy). */
  fetchSourceStockProductUrls: (params: {
    domain: 'hibox' | 'cssbuy' | 'vipomall';
    limit?: number;
    activeOnly?: boolean;
  }) =>
    fetchAdmin<AdminSourceStockProductUrlsResponse>(
      `/products/admin/source-stock-batch/product-urls?domain=${encodeURIComponent(params.domain)}&limit=${params.limit ?? 8000}&active_only=${params.activeOnly ?? true}`,
      { timeoutMs: 120_000 },
    ),

  fetchSourceStockQueueStats: (params: { domain: 'hibox' | 'cssbuy' | 'vipomall'; activeOnly?: boolean }) =>
    fetchAdmin<AdminSourceStockQueueStats>(
      `/products/admin/source-stock-batch/queue-stats?domain=${encodeURIComponent(params.domain)}&active_only=${params.activeOnly ?? true}`,
      { timeoutMs: 60_000 },
    ),

  fetchSourceStockWorkerState: () =>
    fetchAdmin<AdminSourceStockWorkerState>('/products/admin/source-stock-batch/worker-state', {
      timeoutMs: 45_000,
    }),

  setSourceStockWorkerPaused: (paused: boolean) =>
    fetchAdmin<AdminSourceStockWorkerState>('/products/admin/source-stock-batch/worker-pause', {
      method: 'POST',
      body: JSON.stringify({ paused }),
      timeoutMs: 45_000,
    }),

  /** Đếm đã kiểm tra / OOS / còn hàng trong cửa sổ + mẫu chi tiết (phân trang, mới nhất trước). */
  fetchSourceStockActivityReport: (params: {
    domain: 'hibox' | 'cssbuy' | 'vipomall';
    activeOnly?: boolean;
    windowDays?: number;
    samplesOosPage?: number;
    samplesInStockPage?: number;
    samplesBatchTtlPage?: number;
    samplePageSize?: number;
  }) => {
    const sp = new URLSearchParams();
    sp.set('domain', params.domain);
    sp.set('active_only', String(params.activeOnly ?? true));
    sp.set('window_days', String(params.windowDays ?? 30));
    sp.set('samples_oos_page', String(params.samplesOosPage ?? 1));
    sp.set('samples_in_stock_page', String(params.samplesInStockPage ?? 1));
    sp.set('samples_batch_ttl_page', String(params.samplesBatchTtlPage ?? 1));
    sp.set('sample_page_size', String(params.samplePageSize ?? 200));
    return fetchAdmin<AdminSourceStockActivityReport>(
      `/products/admin/source-stock-batch/report?${sp.toString()}`,
      { timeoutMs: 120_000 },
    );
  },

  getProductByDatabaseId: (dbId: number) =>
    fetchAdmin<AdminProduct>(`/products/by-id/${dbId}`, { timeoutMs: 60_000 }),

  clearSourceStockOosFlagByDbId: (dbId: number) =>
    fetchAdmin<AdminSourceStockClearOosFlagResult>('/products/admin/source-stock-batch/clear-oos-flag', {
      method: 'POST',
      body: JSON.stringify({ db_id: dbId }),
      timeoutMs: 60_000,
    }),

  forceWorkerSourceStockRecheckByDbId: (dbId: number) =>
    fetchAdmin<AdminSourceStockForceWorkerRecheckResult>(
      '/products/admin/source-stock-batch/force-worker-recheck',
      {
        method: 'POST',
        body: JSON.stringify({ db_id: dbId }),
        timeoutMs: 60_000,
      },
    ),

  /** Một request thử PDP (CSSBuy→Hibox→Vipomall) theo URL — không cập nhật products. */
  previewSourceStockByUrl: (url: string) =>
    fetchAdmin<AdminSourceStockPreviewUrlResult>('/products/admin/source-stock-batch/preview-url', {
      method: 'POST',
      body: JSON.stringify({ url }),
      timeoutMs: 240_000,
    }),

  /**
   * Xóa lịch/ghi PDP (source_stock_*) và reset trạng thái kiểm tra trong phạm vi link giống queue-stats.
   * Xóa hàng chờ RAM chỉ trên một process backend.
   */
  resetSourceStockPdpCycle: (params: {
    domain: 'hibox' | 'cssbuy' | 'vipomall';
    activeOnly?: boolean;
    confirm: boolean;
  }) =>
    fetchAdmin<AdminSourceStockResetPdpResult>('/products/admin/source-stock-batch/reset-pdp-cycle', {
      method: 'POST',
      body: JSON.stringify({
        domain: params.domain,
        active_only: params.activeOnly ?? true,
        confirm: params.confirm,
      }),
      timeoutMs: 120_000,
    }),

  /** Xóa vĩnh viễn các sản theo khóa chính `products.id` (sau phiên kiểm tra nguồn). */
  deleteSourceStockBatchProductsByDbIds: async (dbIds: number[]) => {
    const unique = [...new Set(dbIds.filter((id) => Number.isFinite(id) && id > 0))];
    if (!unique.length) {
      return { ok: true, deleted_count: 0, deleted_db_ids: [], not_found_db_ids: [] };
    }
    const chunkSize = 20;
    const deleted_db_ids: number[] = [];
    const not_found_db_ids: number[] = [];
    for (let i = 0; i < unique.length; i += chunkSize) {
      const chunk = unique.slice(i, i + chunkSize);
      const res = await fetchAdmin<AdminSourceStockBatchDeleteByDbIdsResult>(
        '/products/admin/source-stock-batch/delete-by-db-ids',
        {
          method: 'POST',
          body: JSON.stringify({ db_ids: chunk }),
          timeoutMs: 120_000,
        },
      );
      deleted_db_ids.push(...(res.deleted_db_ids ?? []));
      not_found_db_ids.push(...(res.not_found_db_ids ?? []));
    }
    return {
      ok: true,
      deleted_count: deleted_db_ids.length,
      deleted_db_ids,
      not_found_db_ids,
    };
  },

  saveGeminiImageLocalizationCookie: (cookie: string) =>
    fetchAdmin<{ success: boolean; cookie_count: number }>('/image-localization/settings/gemini-cookie', {
      method: 'POST',
      body: JSON.stringify({ cookie }),
      timeoutMs: 60_000,
    }),

  getGeminiImageLocalizationAuth: (language = 'vi') =>
    fetchAdmin<AdminGeminiAuthStatus>(
      `/image-localization/settings/gemini-auth?language=${encodeURIComponent(language)}`,
      { timeoutMs: 60_000 },
    ),

  getImageLocalizationSummary: () =>
    fetchAdmin<AdminImageLocalizationSummary>('/image-localization/summary', { timeoutMs: 60_000 }),

  listImageLocalizationJobs: (params?: { limit?: number; active_only?: boolean }) => {
    const qs = new URLSearchParams();
    if (params?.limit != null) qs.set('limit', String(params.limit));
    if (params?.active_only) qs.set('active_only', 'true');
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return fetchAdmin<AdminImageLocalizationJobList>(`/image-localization/jobs${suffix}`, {
      timeoutMs: 60_000,
    });
  },

  getImageLocalizationProductReport: (productId: string) =>
    fetchAdmin<AdminImageLocalizationProductReport>(
      `/image-localization/products/${encodeURIComponent(productId)}/report`,
      { timeoutMs: 60_000 },
    ),

  startImageLocalization: (payload: {
    language: string;
    force?: boolean;
    dry_run?: boolean;
    product_ids?: string[];
    limit?: number;
    gemini_mode?: 'web' | 'api' | 'openai';
    /** false = chỉ DeepSeek + vẽ, không Gemini/GPT ảnh cho cả batch */
    allow_ai_image_models?: boolean | null;
    playwright_headless?: boolean | null;
    gemini_image_model?: string;
    gemini_image_size?: string;
    openai_image_model?: string;
    openai_image_quality?: string;
    openai_image_size?: string;
    inference_tier?: 'standard';
  }) =>
    fetchAdmin<{ job_id: string; status: string }>('/image-localization/jobs', {
      method: 'POST',
      body: JSON.stringify(payload),
      timeoutMs: 60_000,
    }),

  getImageLocalizationJob: (jobId: string) =>
    fetchAdmin<AdminImageLocalizationJob>(`/image-localization/jobs/${encodeURIComponent(jobId)}`, {
      timeoutMs: 60_000,
    }),

  cancelImageLocalizationJob: (jobId: string) =>
    fetchAdmin<AdminImageLocalizationJob>(`/image-localization/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: 'POST',
      timeoutMs: 60_000,
    }),

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
    const url = `${getImportExcelUploadApiBaseUrl()}/import-export/import/excel/async?overwrite=${overwrite}`;
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

  startImport1688: (url: string, downloadImages = true, source?: '1688' | 'hibox' | 'vipomall') =>
    fetchAdmin<{ job_id: string; draft_id: number; message?: string; poll_url?: string }>(
      '/import-1688/jobs',
      {
        method: 'POST',
        body: JSON.stringify({ url, download_images: downloadImages, source }),
        timeoutMs: 60_000,
      },
    ),

  enqueueListingImportQueue: (params: {
    queue_token?: string | null;
    items: {
      url: string;
      source?: string;
      label?: string | null;
      chinese_name?: string | null;
      shop_name_chinese?: string | null;
    }[];
  }) =>
    fetchAdmin<AdminListingImportQueueEnqueueResponse>('/import-1688/listing-queue/enqueue', {
      method: 'POST',
      body: JSON.stringify({
        queue_token: params.queue_token ?? undefined,
        items: params.items,
      }),
      timeoutMs: 120_000,
    }),

  getListingImportQueueStatus: (queueToken: string) =>
    fetchAdmin<AdminListingImportQueueStatus>(
      `/import-1688/listing-queue/${encodeURIComponent(queueToken)}`,
      { timeoutMs: 120_000 },
    ),

  pauseListingImportQueue: (queueToken: string) =>
    fetchAdmin<{ queue_token: string; message: string }>(
      `/import-1688/listing-queue/${encodeURIComponent(queueToken)}/pause`,
      { method: 'POST', timeoutMs: 30_000 },
    ),

  resumeListingImportQueue: (queueToken: string) =>
    fetchAdmin<{ queue_token: string; message: string }>(
      `/import-1688/listing-queue/${encodeURIComponent(queueToken)}/resume`,
      { method: 'POST', timeoutMs: 60_000 },
    ),

  stopListingImportQueue: (queueToken: string) =>
    fetchAdmin<{ queue_token: string; message: string }>(
      `/import-1688/listing-queue/${encodeURIComponent(queueToken)}/stop`,
      { method: 'POST', timeoutMs: 60_000 },
    ),

  listListingImportQueueRuns: (params?: { limit?: number; offset?: number }) => {
    const limit = params?.limit ?? 50;
    const offset = params?.offset ?? 0;
    const qs = `?limit=${encodeURIComponent(String(limit))}&offset=${encodeURIComponent(String(offset))}`;
    return fetchAdmin<AdminListingImportQueueRunsResponse>(`/import-1688/listing-queue/runs${qs}`, {
      timeoutMs: 60_000,
    });
  },

  deleteListingImportQueueSaved: (queueToken: string) =>
    fetchAdmin<{ queue_token: string; deleted: boolean }>(
      `/import-1688/listing-queue/${encodeURIComponent(queueToken)}`,
      { method: 'DELETE', timeoutMs: 30_000 },
    ),

  downloadListingImportQueueCsv: async (
    queueToken: string,
    options?: { finishedOnly?: boolean },
  ) => {
    const token = getAdminToken();
    if (!token) throw new Error('Chưa đăng nhập admin');
    const finishedOnly = options?.finishedOnly === true;
    const qs = finishedOnly ? '?finished_only=true' : '';
    const url = `${getApiBaseUrl()}/import-1688/listing-queue/${encodeURIComponent(queueToken)}/export.csv${qs}`;
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}`, ...ngrokFetchHeaders() },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(formatFastApiDetail(err?.detail ?? err) || 'Tải CSV hàng đợi thất bại');
    }
    const blob = await res.blob();
    const suffix = finishedOnly ? '_ket_qua' : '_snapshot';
    await triggerBlobDownloadPreferred(blob, `listing_import_queue_${queueToken.slice(0, 12)}${suffix}.csv`);
  },

  /** Excel mẫu nhập web — dữ liệu sản phẩm từ draft các dòng đã xong trong đợt (giống export bulk draft). */
  downloadListingImportQueueProductsExcel: async (queueToken: string) => {
    const token = getAdminToken();
    if (!token) throw new Error('Chưa đăng nhập admin');
    const url = `${getApiBaseUrl()}/import-1688/listing-queue/${encodeURIComponent(queueToken)}/export-products.xlsx`;
    const ctrl = new AbortController();
    const tid =
      typeof window !== 'undefined'
        ? window.setTimeout(() => ctrl.abort(), 600_000)
        : undefined;
    try {
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}`, ...ngrokFetchHeaders() },
        signal: ctrl.signal,
      });
      if (!res.ok) {
        const text = await res.text().catch(() => '');
        let detail = '';
        if (text) {
          try {
            const err = JSON.parse(text) as { detail?: unknown };
            detail = formatFastApiDetail(err?.detail);
          } catch {
            /* body không phải JSON */
          }
        }
        if (!detail) {
          const clip = text.replace(/\s+/g, ' ').trim().slice(0, 280);
          detail = clip || res.statusText || `HTTP ${res.status}`;
        }
        throw new Error(
          `${detail} (HTTP ${res.status}${res.statusText ? ` ${res.statusText}` : ''})`,
        );
      }
      const blob = await res.blob();
      await assertBlobLooksLikeXlsx(blob);
      const cd = res.headers.get('Content-Disposition');
      let filename = `listing_queue_products_${queueToken.slice(0, 12)}.xlsx`;
      const m = cd && /filename="?([^";]+)"?/i.exec(cd);
      if (m?.[1]) filename = m[1].trim();
      await triggerBlobDownloadPreferred(blob, filename);
    } finally {
      if (tid != null) window.clearTimeout(tid);
    }
  },

  getImport1688Job: (jobId: string) =>
    fetchAdmin<AdminImport1688Job>(`/import-1688/jobs/${encodeURIComponent(jobId)}`, {
      timeoutMs: 60_000,
    }),

  getImport1688Draft: (draftId: number) =>
    fetchAdmin<AdminImport1688Draft>(`/import-1688/drafts/${draftId}`, {
      timeoutMs: 60_000,
    }),

  deleteImport1688Draft: (draftId: number) =>
    fetchAdmin<{ success: boolean; draft_id: number }>(`/import-1688/drafts/${draftId}`, {
      method: 'DELETE',
      timeoutMs: 60_000,
    }),

  updateImport1688Draft: (draftId: number, productData: Partial<AdminProduct> & Record<string, unknown>) =>
    fetchAdmin<AdminImport1688Draft>(`/import-1688/drafts/${draftId}`, {
      method: 'PUT',
      body: JSON.stringify({ product_data: productData }),
      timeoutMs: 60_000,
    }),

  publishImport1688Draft: (draftId: number) =>
    fetchAdmin<{ success: boolean; action: 'created' | 'updated'; product_id: string; slug?: string }>(
      `/import-1688/drafts/${draftId}/publish`,
      { method: 'POST', timeoutMs: 120_000 },
    ),

  exportImport1688DraftExcel: async (draftId: number) => {
    const token = getAdminToken();
    if (!token) throw new Error('Chưa đăng nhập admin');
    const url = `${getApiBaseUrl()}/import-1688/drafts/${draftId}/export-excel`;
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}`, ...ngrokFetchHeaders() },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(formatFastApiDetail(err?.detail ?? err) || 'Export draft 1688 thất bại');
    }
    const blob = await res.blob();
    await assertBlobLooksLikeXlsx(blob);
    const disposition = res.headers.get('Content-Disposition');
    const match = disposition?.match(/filename="?([^";]+)"?/);
    const filename = match ? match[1] : `import_1688_draft_${draftId}.xlsx`;
    await triggerBlobDownloadPreferred(blob, filename);
  },

  uploadImport1688ExcelBatch: async (
    file: File,
    fetchTarget: 'auto' | 'hibox' | 'vipomall' = 'auto',
  ): Promise<AdminImport1688ExcelBatchStart> => {
    const token = getAdminToken();
    if (!token) throw new Error('Chưa đăng nhập admin');
    const form = new FormData();
    form.append('file', file);
    form.append('fetch_target', fetchTarget);
    const url = `${getApiBaseUrl()}/import-1688/jobs/batch-from-excel`;
    const res = await fetch(url, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, ...ngrokFetchHeaders() },
      body: form,
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(formatFastApiDetail(body?.detail ?? body) || 'Upload batch import link thất bại');
    }
    return body as AdminImport1688ExcelBatchStart;
  },

  getImport1688ExcelBatchStatus: (batchToken: string) =>
    fetchAdmin<AdminImport1688BatchStatus>(
      `/import-1688/jobs/batch-excel/${encodeURIComponent(batchToken)}/status`,
      { timeoutMs: 60_000 },
    ),

  listImport1688ExcelBatches: (params?: { limit?: number }) => {
    const tail = typeof params?.limit === 'number' ? `?limit=${params.limit}` : '';
    return fetchAdmin<AdminImport1688ExcelBatchListResponse>(`/import-1688/jobs/excel-batches${tail}`, {
      timeoutMs: 60_000,
    });
  },

  deleteImport1688ExcelBatch: (batchToken: string) =>
    fetchAdmin<AdminImport1688ExcelBatchDeleteResponse>(
      `/import-1688/jobs/excel-batches/${encodeURIComponent(batchToken)}`,
      { method: 'DELETE', timeoutMs: 120_000 },
    ),

  resumeImport1688ExcelBatch: (batchToken: string) =>
    fetchAdmin<AdminImport1688BatchResumeResponse>(
      `/import-1688/jobs/excel-batches/${encodeURIComponent(batchToken)}/resume`,
      { method: 'POST', timeoutMs: 120_000 },
    ),

  listImport1688Drafts: (params?: { status?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.limit != null) qs.set('limit', String(params.limit));
    if (params?.offset != null) qs.set('offset', String(params.offset));
    const tail = qs.toString() ? `?${qs.toString()}` : '';
    return fetchAdmin<AdminImport1688DraftListResponse>(`/import-1688/drafts${tail}`, { timeoutMs: 60_000 });
  },

  exportImport1688DraftsExcelBulk: async (draftIds: number[]) => {
    const token = getAdminToken();
    if (!token) throw new Error('Chưa đăng nhập admin');
    const url = `${getApiBaseUrl()}/import-1688/drafts/export-excel-bulk`;
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        ...ngrokFetchHeaders(),
      },
      body: JSON.stringify({ draft_ids: draftIds }),
    });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(formatFastApiDetail(errBody?.detail ?? errBody) || 'Export gộp draft thất bại');
    }
    const blob = await res.blob();
    const disposition = res.headers.get('Content-Disposition');
    const match = disposition?.match(/filename="?([^";]+)"?/);
    const filename = match ? match[1] : 'import_1688_drafts_bulk.xlsx';
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  },

  getImport1688CookieSettings: () =>
    fetchAdmin<AdminImport1688CookieSettings>('/import-1688/settings/cookie', {
      timeoutMs: 60_000,
    }).catch((err) => {
      const msg = err instanceof Error ? err.message : String(err);
      if (!/\b404\b|not found/i.test(msg)) throw err;
      return fetchAdmin<AdminImport1688CookieSettings>('/admin/import-1688-cookie', {
        timeoutMs: 60_000,
      });
    }),

  saveImport1688CookieSettings: (cookieText: string) =>
    fetchAdmin<AdminImport1688CookieSettings>('/import-1688/settings/cookie', {
      method: 'PUT',
      body: JSON.stringify({ cookie_text: cookieText }),
      timeoutMs: 60_000,
    }).catch((err) => {
      const msg = err instanceof Error ? err.message : String(err);
      if (!/\b404\b|not found/i.test(msg)) throw err;
      return fetchAdmin<AdminImport1688CookieSettings>('/admin/import-1688-cookie', {
        method: 'PUT',
        body: JSON.stringify({ cookie_text: cookieText }),
        timeoutMs: 60_000,
      });
    }),

  restartBackendApi: () =>
    fetchAdmin<{ success: boolean; message: string }>('/import-1688/settings/restart-api', {
      method: 'POST',
      timeoutMs: 30_000,
    }).catch((err) => {
      const msg = err instanceof Error ? err.message : String(err);
      if (!/\b404\b|not found/i.test(msg)) throw err;
      return fetchAdmin<{ success: boolean; message: string }>('/admin/restart-api', {
        method: 'POST',
        timeoutMs: 30_000,
      });
    }),

  /** Đồng bộ danh sách/mã lên Google Sheet (cần cấu hình server + quyền admin). */
  syncGoogleSheetSkus: () =>
    fetchAdmin<AdminGoogleSheetSkuSyncResult>('/import-export/sync/google-sheet-skus', {
      method: 'POST',
      body: JSON.stringify({}),
      timeoutMs: 300_000,
    }),

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

  /** Excel một cột sku: mã chưa có trên SP và chưa từng export (đã ghi nhận ở server). */
  exportUnusedInternalSkus: async (count: number) => {
    const token = getAdminToken();
    if (!token) throw new Error('Chưa đăng nhập admin');
    const sp = new URLSearchParams();
    sp.set('count', String(Math.max(1, Math.min(10_000, Math.floor(count)))));
    const url = `${getApiBaseUrl()}/products/export-unused-internal-skus?${sp.toString()}`;
    const res = await fetch(url, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, ...ngrokFetchHeaders() },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(formatFastApiDetail(err?.detail ?? err) || 'Export SKU trống thất bại');
    }
    const blob = await res.blob();
    const disposition = res.headers.get('Content-Disposition');
    const match = disposition?.match(/filename="?([^";]+)"?/);
    const filename = match ? match[1] : `internal_skus_unused_${Date.now()}.xlsx`;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  },

  getUnusedInternalSkuStats: () =>
    fetchAdmin<{
      total_space: number;
      available: number;
      used_on_products: number;
      exported_reserved: number;
      blocked_distinct: number;
    }>('/products/export-unused-internal-skus/available-count'),

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
      throw new Error(formatFastApiDetail(err?.detail ?? err) || 'Tải file mẫu thất bại');
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

  getStats: (params?: AdminOrderStatsQuery | 'today' | 'week' | 'month' | 'year' | 'all') => {
    const sp = new URLSearchParams();
    if (typeof params === 'string') {
      sp.set('period', params);
    } else if (params) {
      if (params.period) sp.set('period', params.period);
      if (params.preset) sp.set('preset', params.preset);
      if (params.date) sp.set('date', params.date);
      if (params.year != null) sp.set('year', String(params.year));
      if (params.date_from) sp.set('date_from', params.date_from);
      if (params.date_to) sp.set('date_to', params.date_to);
    } else {
      sp.set('period', 'today');
    }
    return fetchAdmin<AdminOrderStats>(`/orders/admin/stats?${sp.toString()}`);
  },

  updateOrder: (orderId: number, data: {
    status?: string;
    payment_status?: string;
    staff_consultation_contacted?: boolean;
    tracking_number?: string;
    shipping_provider?: string;
  }) =>
    fetchAdmin<AdminOrder>(`/orders/admin/${orderId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  getOrderShipmentTimeline: (orderId: number) =>
    fetchAdmin<{
      order_id: number;
      order_code: string;
      order_status: string;
      tracking_number?: string | null;
      shipping_provider?: string | null;
      footer_note: string;
      current_step_key?: string | null;
      waiting_admin_at_customs: boolean;
      waiting_admin_domestic_delivery: boolean;
      can_confirm_received: boolean;
      events: Array<{
        step_key: string;
        title: string;
        status: string;
        scheduled_at?: string | null;
        completed_at?: string | null;
        note?: string | null;
      }>;
      ems_tracking?: {
        available: boolean;
        tracking_code?: string | null;
        current_status?: number | null;
        current_status_description?: string | null;
        events: Array<{
          status_code?: number | null;
          description: string;
          address?: string | null;
          traced_at?: string | null;
        }>;
        error?: string | null;
      } | null;
    }>(`/orders/admin/${orderId}/shipment-timeline`),

  clearCustomsShipment: (orderId: number) =>
    fetchAdmin<AdminOrder>(`/orders/admin/${orderId}/shipment/clear-customs`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),

  markOutForCustomerConfirm: (orderId: number, data?: { tracking_number?: string; shipping_provider?: string }) =>
    fetchAdmin<AdminOrder>(`/orders/admin/${orderId}/shipment/mark-out-for-confirm`, {
      method: 'POST',
      body: JSON.stringify(data || {}),
    }),

  getOrderPayments: (orderId: number) =>
    fetchAdmin<PaymentRecord[]>(`/orders/admin/${orderId}/payments`),

  lookupOrderByCode: (orderCode: string) =>
    fetchAdmin<AdminOrder>(`/orders/admin/lookup-by-code/${encodeURIComponent(orderCode.trim())}`),

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

  refundDeposit: (orderId: number, data?: { refund_note?: string }) =>
    fetchAdmin<AdminOrder>(`/orders/admin/${orderId}/refund-deposit`, {
      method: 'POST',
      body: JSON.stringify(data || {}),
    }),

  approveReturnReceived: (orderId: number, data?: { note?: string }) =>
    fetchAdmin<AdminOrder>(`/orders/admin/${orderId}/approve-return-received`, {
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

export interface AdminIntegrationKeyRow {
  env_var: string;
  label: string;
  configured: boolean;
  hint: string;
}

export interface AdminIntegrationKeyGroup {
  title: string;
  items: AdminIntegrationKeyRow[];
}

export interface AdminIntegrationKeysOverview {
  groups: AdminIntegrationKeyGroup[];
  disclaimer: string;
}

export const adminIntegrationsAPI = {
  getApiKeysOverview: () =>
    fetchAdmin<AdminIntegrationKeysOverview>('/admin/integrations/api-keys-overview'),
};

export interface AdminBirthdayPromoTestSettings {
  birthday_promo_enabled: boolean;
  birthday_promo_expires_at?: string | null;
  test_duration_minutes?: number;
  admin_email?: string | null;
  test_email?: string | null;
  linked_user_id?: number | null;
  can_apply_on_web: boolean;
  test_email_sent?: boolean;
  test_email_error?: string | null;
}

export interface AdminSiteSaleTestSettings {
  site_sale_test_enabled: boolean;
  site_sale_test_expires_at?: string | null;
  site_sale_test_phase: 'teaser' | 'active';
  test_duration_minutes?: number;
  admin_email?: string | null;
  test_email?: string | null;
  linked_user_id?: number | null;
  can_apply_on_web: boolean;
}

async function fetchAdminFirstOk<T>(
  endpoints: string[],
  options: RequestInit & { timeoutMs?: number } = {},
): Promise<T> {
  let lastError: Error | null = null;
  for (const endpoint of endpoints) {
    try {
      return await fetchAdmin<T>(endpoint, options);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (message.includes('[404')) {
        lastError = err instanceof Error ? err : new Error(message);
        continue;
      }
      throw err;
    }
  }
  throw lastError ?? new Error('Không tìm thấy API admin phù hợp.');
}

export const adminFeatureTestAPI = {
  getBirthdayPromoSettings: () =>
    fetchAdmin<AdminBirthdayPromoTestSettings>('/birthday-promo/admin/test-settings'),
  updateBirthdayPromoSettings: (birthday_promo_enabled: boolean, test_email?: string | null) =>
    fetchAdmin<AdminBirthdayPromoTestSettings>('/birthday-promo/admin/test-settings', {
      method: 'PUT',
      body: JSON.stringify({ birthday_promo_enabled, test_email }),
    }),
  getSiteSaleSettings: () =>
    fetchAdminFirstOk<AdminSiteSaleTestSettings>([
      '/birthday-promo/admin/site-sale-test-settings',
      '/sale-calendar/admin/test-settings',
    ]),
  updateSiteSaleSettings: (
    site_sale_test_enabled: boolean,
    site_sale_test_phase: 'teaser' | 'active',
    test_email?: string | null,
  ) =>
    fetchAdminFirstOk<AdminSiteSaleTestSettings>(
      [
        '/birthday-promo/admin/site-sale-test-settings',
        '/sale-calendar/admin/test-settings',
      ],
      {
        method: 'PUT',
        body: JSON.stringify({ site_sale_test_enabled, site_sale_test_phase, test_email }),
      },
    ),
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
        localStorage.removeItem('admin_role');
        localStorage.removeItem('admin_modules');
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
  has_linked_admin?: boolean;
  linked_admin_role?: string | null;
  linked_admin_username?: string | null;
  linked_admin_modules?: string[] | null;
}

export interface AdminMembersResponse {
  items: AdminMember[];
  total: number;
}

export type LinkedStaffRoleOption =
  | 'none'
  | 'order_manager'
  | 'admin'
  | 'product_manager'
  | 'content_manager';

export interface AdminStaffAccountRow {
  id: number;
  username: string;
  email: string;
  full_name?: string | null;
  phone?: string | null;
  role: string;
  is_active: boolean;
  linked_user_id?: number | null;
  modules: string[];
  uses_custom_modules: boolean;
}

export type StaffPermissionsModulesMode = 'unchanged' | 'preset' | 'custom';

export const adminStaffAPI = {
  list: () => fetchAdmin<{ items: AdminStaffAccountRow[] }>('/admin/admin-users'),
  patchPermissions: (
    id: number,
    body: {
      role?: string;
      modules_mode: StaffPermissionsModulesMode;
      modules?: string[];
    },
  ) =>
    fetchAdmin<AdminStaffAccountRow>(`/admin/admin-users/${id}/permissions`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
};

export interface StaffRolePresetCrudFlags {
  view: boolean;
  create: boolean;
  update: boolean;
  delete: boolean;
}

export interface StaffRolePresetItem {
  role: string;
  modules: string[];
  module_crud: Record<string, StaffRolePresetCrudFlags>;
}

export const adminStaffRolePresetsAPI = {
  list: () => fetchAdmin<{ items: StaffRolePresetItem[] }>('/admin/staff-role-presets'),
  put: (role: string, body: { modules: string[]; module_crud: Record<string, StaffRolePresetCrudFlags> }) =>
    fetchAdmin<StaffRolePresetItem>(`/admin/staff-role-presets/${encodeURIComponent(role)}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
};

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
  setLinkedStaff: (
    id: number,
    staff_role: LinkedStaffRoleOption,
    modules?: string[],
  ) =>
    fetchAdmin<AdminMember>(`/admin/users/${id}/linked-staff`, {
      method: 'PATCH',
      body: JSON.stringify(
        modules === undefined ? { staff_role } : { staff_role, modules },
      ),
    }),
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
      throw new Error(formatFastApiDetail(err?.detail ?? err) || 'Import thất bại');
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
  user_id?: number | null;
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

  deleteAll: () =>
    fetchAdmin<{ message: string; deleted: number }>('/product-reviews/admin/delete-all', {
      method: 'DELETE',
    }),

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
      throw new Error(formatFastApiDetail(err?.detail ?? err) || 'Import thất bại');
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

export interface AdminWelcomePromoSettings {
  code: string;
  name: string;
  description?: string | null;
  discount_percent: number;
  max_discount_amount: number;
  eligible_within_days?: number | null;
  show_days_remaining: boolean;
  is_active: boolean;
  first_order_only: boolean;
}

export interface AdminPromotionCode {
  id: number;
  code: string;
  name: string;
  description?: string | null;
  discount_percent: number;
  max_discount_amount?: number | null;
  first_order_only: boolean;
  stack_with_birthday: boolean;
  stack_with_loyalty: boolean;
  is_active: boolean;
  valid_from?: string | null;
  valid_to?: string | null;
  usage_limit?: number | null;
  per_user_limit: number;
  eligible_within_days?: number | null;
  grant_valid_days?: number | null;
  requires_wallet_grant: boolean;
  auto_grant_trigger: string;
  grants_count: number;
  usages_count: number;
  is_system_template: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export type AdminPromotionCodeInput = {
  code: string;
  name: string;
  description?: string;
  discount_percent: number;
  max_discount_amount?: number | null;
  first_order_only?: boolean;
  stack_with_birthday?: boolean;
  stack_with_loyalty?: boolean;
  is_active?: boolean;
  valid_from?: string | null;
  valid_to?: string | null;
  usage_limit?: number | null;
  per_user_limit?: number;
  eligible_within_days?: number | null;
  grant_valid_days?: number | null;
  requires_wallet_grant?: boolean;
  auto_grant_trigger?: string;
  is_system_template?: boolean;
};

export const adminPromotionsAPI = {
  listPromotions: () =>
    fetchAdmin<{ items: AdminPromotionCode[] }>('/promotions/admin/promotions'),
  getPromotion: (id: number) =>
    fetchAdmin<AdminPromotionCode>(`/promotions/admin/promotions/${id}`),
  createPromotion: (data: AdminPromotionCodeInput) =>
    fetchAdmin<AdminPromotionCode>('/promotions/admin/promotions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updatePromotion: (id: number, data: Partial<AdminPromotionCodeInput>) =>
    fetchAdmin<AdminPromotionCode>(`/promotions/admin/promotions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  getWelcomeSettings: () => fetchAdmin<AdminWelcomePromoSettings>('/promotions/admin/welcome'),
  updateWelcomeSettings: (data: {
    name?: string;
    description?: string;
    discount_percent?: number;
    max_discount_amount?: number;
    eligible_within_days?: number;
    is_active?: boolean;
  }) =>
    fetchAdmin<AdminWelcomePromoSettings>('/promotions/admin/welcome', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  grantToUser: (data: {
    user_id: number;
    promo_code: string;
    expires_in_days?: number;
    message?: string;
    notify?: boolean;
  }) =>
    fetchAdmin<AdminUserGrantRow>('/promotions/admin/grant', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  grantComebackSegment: (inactive_days?: number) =>
    fetchAdmin<{ granted: number; skipped: number }>('/promotions/admin/grant-segment', {
      method: 'POST',
      body: JSON.stringify({ segment: 'comeback', inactive_days: inactive_days ?? 30 }),
    }),
  backfillWelcome: () =>
    fetchAdmin<{ granted: number; skipped: number }>('/promotions/admin/grant-segment', {
      method: 'POST',
      body: JSON.stringify({ segment: 'welcome_backfill' }),
    }),
  runCartAbandon: (abandon_hours?: number) =>
    fetchAdmin<{ granted: number; skipped: number }>('/promotions/admin/grant-segment', {
      method: 'POST',
      body: JSON.stringify({ segment: 'cart_abandon', abandon_hours: abandon_hours ?? 24 }),
    }),
  listUserGrants: (user_id: number) =>
    fetchAdmin<AdminUserGrantRow[]>(`/promotions/admin/grants?user_id=${user_id}`),
};

export type AdminSaleCalendarSettings = {
  enabled: boolean;
  teaser_days: number;
  schedule_mode: 'auto' | 'scheduled' | 'manual';
  scheduled_sale_date?: string | null;
  scheduled_discount_percent?: number | null;
  manual_sale_date?: string | null;
  manual_discount_percent?: number | null;
  month_rules: Array<{
    month: number;
    enabled: boolean;
    discount_percent_override: number | null;
    default_discount_percent: number;
  }>;
  upcoming: Array<{
    event_date: string;
    event_label: string;
    discount_percent: number;
    teaser_start: string;
    active_start: string;
    active_end: string;
    month_parity: string;
  }>;
  current: import('@/types/api').SiteSaleCalendarState;
};

export const adminSaleCalendarAPI = {
  getSettings: () => fetchAdmin<AdminSaleCalendarSettings>('/sale-calendar/admin/settings'),
  updateSettings: (data: {
    enabled?: boolean;
    teaser_days?: number;
    schedule_mode?: 'auto' | 'scheduled' | 'manual';
    scheduled_sale_date?: string | null;
    scheduled_discount_percent?: number | null;
    manual_sale_date?: string | null;
    manual_discount_percent?: number | null;
    clear_scheduled?: boolean;
    clear_manual?: boolean;
  }) =>
    fetchAdmin<AdminSaleCalendarSettings>('/sale-calendar/admin/settings', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  updateMonthRule: (data: {
    month: number;
    enabled?: boolean;
    discount_percent_override?: number | null;
  }) =>
    fetchAdmin<AdminSaleCalendarSettings['month_rules'][number]>('/sale-calendar/admin/month-rules', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
};

export interface AdminUserGrantRow {
  id: number;
  user_id: number;
  code: string;
  name: string;
  status: string;
  source: string;
  granted_at?: string | null;
  expires_at?: string | null;
}

export interface AdminWalletWithdrawal {
  id: number;
  user_id: number;
  amount: number;
  bank_name: string;
  bank_account: string;
  account_holder: string;
  status: string;
  admin_note?: string | null;
  created_at: string;
  processed_at?: string | null;
}

export interface AdminAffiliateCommission {
  id: number;
  referrer_user_id: number;
  buyer_user_id?: number | null;
  order_id: number;
  order_base_amount: number;
  commission_percent: number;
  commission_amount: number;
  status: string;
  created_at: string;
  confirmed_at?: string | null;
}

export interface AdminAffiliateSettings {
  id: number;
  enabled: boolean;
  commission_percent: number;
  min_withdrawal: number;
  ref_cookie_days: number;
  commission_policy?: string | null;
  updated_by?: number | null;
  updated_at?: string | null;
}

export interface AdminAffiliateApplication {
  id: number;
  user_id: number;
  status: string;
  social_links: string[];
  note?: string | null;
  admin_note?: string | null;
  reviewed_by?: number | null;
  submitted_at: string;
  reviewed_at?: string | null;
  updated_at?: string | null;
}

export const adminAffiliateAPI = {
  getSettings: () => fetchAdmin<AdminAffiliateSettings>('/affiliate/admin/settings'),
  updateSettings: (data: Omit<AdminAffiliateSettings, 'id' | 'updated_by' | 'updated_at'>) =>
    fetchAdmin<AdminAffiliateSettings>('/affiliate/admin/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  listCommissions: (status?: string) => {
    const q = status ? `?status=${encodeURIComponent(status)}` : '';
    return fetchAdmin<AdminAffiliateCommission[]>(`/affiliate/admin/commissions${q}`);
  },
  listApplications: (status?: string) => {
    const q = status ? `?status=${encodeURIComponent(status)}` : '';
    return fetchAdmin<AdminAffiliateApplication[]>(`/affiliate/admin/applications${q}`);
  },
  approveApplication: (id: number, admin_note?: string) =>
    fetchAdmin<AdminAffiliateApplication>(`/affiliate/admin/applications/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ admin_note: admin_note ?? null }),
    }),
  rejectApplication: (id: number, admin_note?: string) =>
    fetchAdmin<AdminAffiliateApplication>(`/affiliate/admin/applications/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ admin_note: admin_note ?? null }),
    }),
  listWithdrawals: (status?: string) => {
    const q = status ? `?status=${encodeURIComponent(status)}` : '';
    return fetchAdmin<AdminWalletWithdrawal[]>(`/affiliate/admin/withdrawals${q}`);
  },
  approveWithdrawal: (id: number) =>
    fetchAdmin<AdminWalletWithdrawal>(`/affiliate/admin/withdrawals/${id}/approve`, { method: 'POST' }),
  rejectWithdrawal: (id: number, admin_note?: string) =>
    fetchAdmin<AdminWalletWithdrawal>(`/affiliate/admin/withdrawals/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ admin_note: admin_note ?? null }),
    }),
};

export type EmsShippingSyncStatus =
  | 'matched'
  | 'in_progress'
  | 'mismatch'
  | 'unlinked'
  | 'order_not_found'
  | 'ems_not_found'
  | 'parse_error'
  | 'pending';

export interface EmsShippingImportRow {
  id?: number | null;
  row_number: number;
  reference_code: string;
  recipient_label: string;
  order_code?: string | null;
  order_id?: number | null;
  order_status?: string | null;
  current_step_key?: string | null;
  tracking_number_saved?: string | null;
  ems_tracking_code?: string | null;
  ems_reference_code?: string | null;
  ems_status?: string | null;
  ems_phase?: string | null;
  sync_status: EmsShippingSyncStatus;
  sync_message: string;
    ems_error?: string | null;
    cod_amount?: number | null;
    cod_paid_amount?: number | null;
  cod_paid_date?: string | null;
  cod_settlement_status?: string | null;
  cod_settlement_message?: string | null;
  freight_amount?: number | null;
  freight_settled_at?: string | null;
  freight_settlement_status?: string | null;
  freight_settlement_message?: string | null;
  freight_high_fee_warning?: string | null;
}

export interface EmsShippingListPagination {
  skip: number;
  limit: number;
  total: number;
  filtered_total: number;
  search?: string | null;
}

export type EmsShippingImportAction = 'created' | 'updated';

export interface EmsShippingImportReportRow extends EmsShippingImportRow {
  import_action?: EmsShippingImportAction | null;
}

export interface EmsShippingImportReport {
  order_count: number;
  total_cod_amount: number;
  created: number;
  updated: number;
  skipped_no_reference: number;
  orders_synced: number;
  rows: EmsShippingImportReportRow[];
}

export interface EmsShippingImportResult {
  ok: boolean;
  warnings: string[];
  summary: {
    total_rows: number;
    matched: number;
    in_progress: number;
    mismatch: number;
    unlinked?: number;
    order_not_found: number;
    ems_not_found: number;
    parse_error: number;
    total_cod_amount?: number;
    breakdown?: Array<{ key: string; count: number; cod_total: number }>;
  };
  import_stats?: {
    file_rows_processed: number;
    created: number;
    updated: number;
    skipped_no_reference: number;
    orders_synced: number;
  } | null;
  import_report?: EmsShippingImportReport | null;
  tracking_refresh_job_id?: string | null;
  pagination?: EmsShippingListPagination | null;
  rows: EmsShippingImportRow[];
}

export interface EmsTrackingRefreshJob {
  job_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  source?: string | null;
  total: number;
  processed: number;
  ok: number;
  errors: number;
  message: string;
  created_at?: string | null;
  updated_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  seconds_since_update?: number | null;
  is_stale?: boolean;
  resume_ok?: boolean | null;
  resume_message?: string | null;
}

export type EmsShippingListParams = {
  skip?: number;
  limit?: number;
  sync_status?: string;
  q?: string;
};

export const adminShippingAPI = {
  listEmsRecords: (params: EmsShippingListParams = {}) => {
    const qs = new URLSearchParams();
    if (params.skip != null && params.skip > 0) qs.set('skip', String(params.skip));
    if (params.limit != null) qs.set('limit', String(params.limit));
    if (params.sync_status && params.sync_status !== 'all') qs.set('sync_status', params.sync_status);
    if (params.q?.trim()) qs.set('q', params.q.trim());
    const query = qs.toString();
    return fetchAdmin<EmsShippingImportResult>(
      `/orders/admin/shipping/ems-records${query ? `?${query}` : ''}`,
    );
  },

  getOperationsStats: () =>
    fetchAdmin<EmsShippingOperationsStats>('/orders/admin/shipping/operations-stats'),

  getTimelineStats: async (params: EmsShippingTimelineParams = {}) => {
    const qs = new URLSearchParams();
    qs.set('view', 'timeline');
    if (params.granularity) qs.set('granularity', params.granularity);
    if (params.limit != null) qs.set('limit', String(params.limit));
    if (params.date_from) qs.set('date_from', params.date_from);
    if (params.date_to) qs.set('date_to', params.date_to);
    if (params.preset) qs.set('preset', params.preset);
    if (params.year != null) qs.set('year', String(params.year));
    const data = await fetchAdmin<EmsShippingTimelineStats>(
      `/orders/admin/shipping/operations-stats?${qs.toString()}`,
    );
    if (!Array.isArray(data.items) || typeof data.granularity !== 'string') {
      throw new Error(
        'Backend chưa cập nhật API thống kê timeline. Restart FastAPI (port 8001) rồi thử lại.',
      );
    }
    return data;
  },

  listOperationsRecords: (params: { bucket: string; skip?: number; limit?: number }) => {
    const qs = new URLSearchParams();
    qs.set('bucket', params.bucket);
    if (params.skip != null && params.skip > 0) qs.set('skip', String(params.skip));
    if (params.limit != null) qs.set('limit', String(params.limit));
    return fetchAdmin<EmsShippingOperationsRecords>(
      `/orders/admin/shipping/operations-stats/records?${qs.toString()}`,
    );
  },

  listTimelineRecords: (params: EmsShippingTimelineRecordsParams) => {
    const qs = new URLSearchParams();
    qs.set('bucket', params.bucket);
    if (params.granularity) qs.set('granularity', params.granularity);
    if (params.period_key) qs.set('period_key', params.period_key);
    if (params.date_from) qs.set('date_from', params.date_from);
    if (params.date_to) qs.set('date_to', params.date_to);
    if (params.preset) qs.set('preset', params.preset);
    if (params.year != null) qs.set('year', String(params.year));
    if (params.skip != null && params.skip > 0) qs.set('skip', String(params.skip));
    if (params.limit != null) qs.set('limit', String(params.limit));
    return fetchAdmin<EmsShippingOperationsRecords>(
      `/orders/admin/shipping/operations-stats/timeline/records?${qs.toString()}`,
    );
  },

  importEmsExcel: async (file: File): Promise<EmsShippingImportResult> => {
    const token = getAdminToken();
    if (!token) throw new Error('Chưa đăng nhập admin');
    const form = new FormData();
    form.append('file', file);
    const url = `${getApiBaseUrl()}/orders/admin/shipping/ems-import`;
    const res = await fetch(url, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, ...ngrokFetchHeaders() },
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(formatFastApiDetail(err?.detail ?? err) || 'Import EMS thất bại');
    }
    return res.json();
  },

  deleteEmsRecords: (ids: number[]) =>
    fetchAdmin<{ ok: boolean; deleted: number }>('/orders/admin/shipping/ems-records', {
      method: 'DELETE',
      body: JSON.stringify({ ids }),
    }),

  getEmsTrackingRefreshJob: (jobId: string) =>
    fetchAdmin<EmsTrackingRefreshJob>(`/orders/admin/shipping/ems-tracking-refresh/job/${encodeURIComponent(jobId)}`),

  resumeEmsTrackingRefreshJob: (jobId: string) =>
    fetchAdmin<EmsTrackingRefreshJob>(
      `/orders/admin/shipping/ems-tracking-refresh/resume/${encodeURIComponent(jobId)}`,
      { method: 'POST' },
    ),

  getActiveEmsTrackingRefreshJob: async (): Promise<EmsTrackingRefreshJob | null> => {
    try {
      return await fetchAdmin<EmsTrackingRefreshJob>('/orders/admin/shipping/ems-tracking-refresh/active');
    } catch {
      return null;
    }
  },

  enqueueEmsTrackingRefresh: (payload: {
    ids?: number[];
    q?: string;
    sync_status?: string;
    non_terminal_only?: boolean;
  }) =>
    fetchAdmin<{ ok: boolean; job_id?: string | null; queued: number; message: string }>(
      '/orders/admin/shipping/ems-tracking-refresh',
      { method: 'POST', body: JSON.stringify(payload) },
    ),
};

export interface EmsShippingOperationsStats {
  total_ems_records: number;
  total_with_cod: number;
  in_transit_count: number;
  delivered_count: number;
  returned_count: number;
  pending_status_count: number;
  cod_in_transit_unpaid_count: number;
  cod_delivered_unpaid_count: number;
  cod_paid_count: number;
  cod_returned_unpaid_count: number;
  cod_pending_unpaid_count: number;
  cod_in_transit_unpaid_total: number;
  cod_delivered_unpaid_total: number;
  cod_paid_total: number;
  shop_linked_count: number;
  shop_return_received_count: number;
  freight_unsettled_count: number;
  shop_shipping_orders: number;
  shop_delivered_orders: number;
  shop_returned_orders: number;
  /** @deprecated legacy aliases */
  shipping_orders: number;
  delivered_success_orders: number;
  returned_orders: number;
  cod_success_unpaid_count: number;
  cod_success_unpaid_total: number;
  cod_success_paid_count: number;
  cod_success_paid_total: number;
  shipping_cod_unpaid_count: number;
}

export type EmsShippingTimelineGranularity = 'year' | 'month' | 'week' | 'day';

export type EmsShippingTimelinePreset = 'this_week' | 'last_week' | 'this_month' | 'last_month';

export interface EmsShippingTimelineParams {
  granularity?: EmsShippingTimelineGranularity;
  limit?: number;
  date_from?: string;
  date_to?: string;
  preset?: EmsShippingTimelinePreset;
  year?: number;
}

export interface EmsShippingTimelineItem {
  period_key: string;
  period_label: string;
  period_start: string;
  period_end: string;
  total: number;
  in_transit_count: number;
  delivered_count: number;
  returned_count: number;
  pending_status_count: number;
  total_with_cod: number;
  cod_delivered_unpaid_count: number;
  cod_paid_count: number;
  total_cod_amount: number;
  cod_delivered_unpaid_total: number;
  cod_paid_total: number;
}

export interface EmsShippingTimelineStats {
  granularity: EmsShippingTimelineGranularity;
  timezone: string;
  date_field: string;
  limit: number;
  filter_from?: string | null;
  filter_to?: string | null;
  filter_label?: string | null;
  preset?: string | null;
  year?: number | null;
  available_years: number[];
  items: EmsShippingTimelineItem[];
  totals: Pick<
    EmsShippingTimelineItem,
    | 'total'
    | 'in_transit_count'
    | 'delivered_count'
    | 'returned_count'
    | 'pending_status_count'
    | 'total_with_cod'
    | 'cod_delivered_unpaid_count'
    | 'cod_paid_count'
    | 'total_cod_amount'
    | 'cod_delivered_unpaid_total'
    | 'cod_paid_total'
  >;
}

export type OpsBucketKey =
  | 'total'
  | 'in_transit'
  | 'delivered'
  | 'returned'
  | 'pending'
  | 'has_cod'
  | 'cod_in_transit_unpaid'
  | 'cod_delivered_unpaid'
  | 'cod_paid'
  | 'cod_returned_unpaid'
  | 'cod_pending_unpaid'
  | 'freight_unsettled'
  | 'shop_linked'
  | 'shop_return_received'
  | 'shop_shipping';

export interface EmsShippingOperationsRecords {
  ok: boolean;
  bucket: OpsBucketKey;
  bucket_label: string;
  period_key?: string | null;
  granularity?: string | null;
  pagination: EmsShippingListPagination;
  rows: EmsShippingImportRow[];
}

export type EmsShippingTimelineRecordsParams = {
  bucket: OpsBucketKey;
  granularity?: EmsShippingTimelineGranularity;
  period_key?: string;
  date_from?: string;
  date_to?: string;
  preset?: EmsShippingTimelinePreset;
  year?: number;
  skip?: number;
  limit?: number;
};

export type EmsCodReconcileStatus = 'matched' | 'amount_mismatch' | 'record_not_found' | 'parse_error';

export interface EmsCodSettlementRow {
  id?: number | null;
  batch_id?: number | null;
  row_number: number;
  ems_reference_code?: string | null;
  ems_tracking_code?: string | null;
  paid_amount?: number | null;
  ems_shipping_record_id?: number | null;
  db_cod_amount?: number | null;
  amount_difference?: number | null;
  reconcile_status: EmsCodReconcileStatus | string;
  reconcile_message: string;
}

export interface EmsCodSettlementImportResult {
  ok: boolean;
  warnings: string[];
  summary: {
    total_rows: number;
    matched: number;
    amount_mismatch: number;
    record_not_found: number;
    parse_error: number;
    total_paid_amount: number;
    total_db_cod_amount: number;
    total_amount_difference: number;
    breakdown?: Array<{ key: string; count: number; paid_total: number; db_cod_total: number }>;
  };
  import_batch?: {
    id: number;
    payment_date?: string | null;
    source_filename?: string | null;
    total_rows: number;
    matched_count: number;
    amount_mismatch_count: number;
    record_not_found_count: number;
    parse_error_count: number;
    total_paid_amount: number;
    total_db_cod_amount: number;
    total_amount_difference: number;
    rows: EmsCodSettlementRow[];
  } | null;
  batches: Array<{
    id: number;
    payment_date?: string | null;
    source_filename?: string | null;
    total_rows: number;
    matched_count: number;
    amount_mismatch_count: number;
    record_not_found_count: number;
    parse_error_count: number;
    total_paid_amount: number;
    total_db_cod_amount: number;
    total_amount_difference: number;
    created_at?: string | null;
    rows: EmsCodSettlementRow[];
  }>;
}

export const adminCodSettlementAPI = {
  listBatches: () =>
    fetchAdmin<EmsCodSettlementImportResult>('/orders/admin/shipping/cod-settlement-batches'),

  importExcel: async (file: File): Promise<EmsCodSettlementImportResult> => {
    const token = getAdminToken();
    if (!token) throw new Error('Chưa đăng nhập admin');
    const form = new FormData();
    form.append('file', file);
    const url = `${getApiBaseUrl()}/orders/admin/shipping/cod-settlement-import`;
    const res = await fetch(url, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, ...ngrokFetchHeaders() },
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(formatFastApiDetail(err?.detail ?? err) || 'Import đối soát COD thất bại');
    }
    return res.json();
  },
};

export type EmsFreightReconcileStatus = 'settled' | 'already_settled' | 'record_not_found' | 'parse_error';

export interface EmsFreightSettlementRow {
  id?: number | null;
  batch_id?: number | null;
  row_number: number;
  ems_tracking_code?: string | null;
  freight_amount?: number | null;
  ems_shipping_record_id?: number | null;
  high_fee_warning?: string | null;
  reconcile_status: EmsFreightReconcileStatus | string;
  reconcile_message: string;
}

export interface EmsFreightSettlementImportResult {
  ok: boolean;
  warnings: string[];
  summary: {
    total_rows: number;
    settled: number;
    already_settled: number;
    record_not_found: number;
    parse_error: number;
    high_fee_warning_count: number;
    total_freight_amount: number;
    breakdown?: Array<{ key: string; count: number; freight_total: number }>;
  };
  import_batch?: {
    id: number;
    source_filename?: string | null;
    total_rows: number;
    settled_count: number;
    record_not_found_count: number;
    already_settled_count: number;
    parse_error_count: number;
    high_fee_warning_count: number;
    total_freight_amount: number;
    rows: EmsFreightSettlementRow[];
  } | null;
  batches: Array<{
    id: number;
    source_filename?: string | null;
    total_rows: number;
    settled_count: number;
    record_not_found_count: number;
    already_settled_count: number;
    parse_error_count: number;
    high_fee_warning_count: number;
    total_freight_amount: number;
    created_at?: string | null;
    rows: EmsFreightSettlementRow[];
  }>;
}

export const adminFreightSettlementAPI = {
  listBatches: () =>
    fetchAdmin<EmsFreightSettlementImportResult>('/orders/admin/shipping/freight-settlement-batches'),

  importExcel: async (file: File): Promise<EmsFreightSettlementImportResult> => {
    const token = getAdminToken();
    if (!token) throw new Error('Chưa đăng nhập admin');
    const form = new FormData();
    form.append('file', file);
    const url = `${getApiBaseUrl()}/orders/admin/shipping/freight-settlement-import`;
    const res = await fetch(url, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, ...ngrokFetchHeaders() },
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(formatFastApiDetail(err?.detail ?? err) || 'Import đối soát cước thất bại');
    }
    return res.json();
  },
};

export interface AdminLoginResponse {
  access_token: string;
  token_type?: string;
  admin_id?: number;
  username?: string;
  role: string;
  modules?: string[] | null;
}

export async function adminLogin(username: string, password: string): Promise<AdminLoginResponse> {
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
