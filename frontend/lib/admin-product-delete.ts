/**
 * Xóa SP admin theo product_id Excel (có dấu /) — POST body, không đưa ID vào path URL.
 * Dùng proxy /api/v1 (ổn định trên VPS); tránh route riêng /api/admin/... có thể chưa deploy.
 * Chia lô; gặp 502/504/timeout thì giảm kích thước lô; lô = 1 vẫn lỗi thì chờ rồi tự thử lại.
 */
import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';
import {
  adminStepUpHeaders,
  isAdminStepUpRequiredDetail,
  promptAdminStepUpAndRetry,
} from '@/lib/admin-step-up';

const TIMEOUT_RETRY_DELAY_MS = 40_000;
const MAX_CONSECUTIVE_TIMEOUT_RETRIES = 10;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
export type AdminBulkDeleteProductsResult = {
  deleted: string[];
  deleted_count: number;
  errors: { product_id: string; status: number; detail: string }[];
};

function adminToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('admin_token');
}

function isGatewayOrTimeout(err: unknown): boolean {
  const msg = err instanceof Error ? err.message : String(err);
  return /\[502\]|\[504\]|Hết giờ chờ proxy|Hết thời gian chờ server|gateway timeout|Gateway Timeout/i.test(
    msg,
  );
}

async function bulkDeleteOnce(productIds: string[]): Promise<AdminBulkDeleteProductsResult> {
  const token = adminToken();
  if (!token) throw new Error('Chưa đăng nhập admin');

  const res = await fetch(`${getApiBaseUrl()}/products/by-product-id/bulk-delete`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...ngrokFetchHeaders(),
      ...adminStepUpHeaders(),
    },
    body: JSON.stringify({ product_ids: productIds }),
    cache: 'no-store',
    credentials: 'include',
  });

  if (res.status === 428) {
    const err = await res.clone().json().catch(() => ({}));
    if (isAdminStepUpRequiredDetail((err as { detail?: unknown }).detail)) {
      return promptAdminStepUpAndRetry(() => bulkDeleteOnce(productIds));
    }
  }

  if (res.status === 401) {
    localStorage.removeItem('admin_token');
    localStorage.removeItem('admin_role');
    localStorage.removeItem('admin_modules');
    window.location.href = '/admin/login';
    throw new Error('Phiên đăng nhập hết hạn');
  }

  const data = (await res.json().catch(() => ({}))) as {
    detail?: unknown;
    deleted?: string[];
    deleted_count?: number;
    errors?: AdminBulkDeleteProductsResult['errors'];
  };

  if (!res.ok) {
    const detail =
      typeof data.detail === 'string'
        ? data.detail
        : Array.isArray(data.detail)
          ? data.detail
              .map((x) =>
                typeof x === 'object' && x && 'msg' in x
                  ? String((x as { msg?: unknown }).msg)
                  : String(x),
              )
              .join('; ')
          : res.statusText;
    const hint =
      res.status === 404 && !detail
        ? 'API xóa chưa có trên server — deploy lại frontend + backend (endpoint POST /products/by-product-id/bulk-delete).'
        : '';
    if (res.status === 502 || res.status === 504) {
      throw new Error(
        `[${res.status}] Hết giờ chờ proxy (gateway timeout) — ${detail || hint || 'Xóa thất bại'}`,
      );
    }
    throw new Error(`[${res.status}] ${detail || hint || 'Xóa thất bại'}`);
  }

  return {
    deleted: data.deleted ?? [],
    deleted_count: data.deleted_count ?? 0,
    errors: data.errors ?? [],
  };
}

export async function bulkDeleteAdminProducts(
  productIds: string[],
): Promise<AdminBulkDeleteProductsResult> {
  const unique = [...new Set(productIds.map((p) => (p || '').trim()).filter(Boolean))];
  if (!unique.length) {
    return { deleted: [], deleted_count: 0, errors: [] };
  }

  const INITIAL_CHUNK = 3;
  const MIN_CHUNK = 1;
  let chunkSize = INITIAL_CHUNK;
  const deleted: string[] = [];
  const errors: AdminBulkDeleteProductsResult['errors'] = [];
  let cursor = 0;
  let consecutiveTimeoutRetries = 0;

  while (cursor < unique.length) {
    const chunk = unique.slice(cursor, cursor + chunkSize);
    try {
      const res = await bulkDeleteOnce(chunk);
      consecutiveTimeoutRetries = 0;
      deleted.push(...(res.deleted ?? []));
      errors.push(...(res.errors ?? []));
      cursor += chunk.length;
    } catch (err) {
      if (isGatewayOrTimeout(err) && chunkSize > MIN_CHUNK) {
        chunkSize = Math.max(MIN_CHUNK, Math.floor(chunkSize / 2));
        continue;
      }
      if (isGatewayOrTimeout(err) && consecutiveTimeoutRetries < MAX_CONSECUTIVE_TIMEOUT_RETRIES) {
        consecutiveTimeoutRetries += 1;
        await sleep(TIMEOUT_RETRY_DELAY_MS);
        continue;
      }
      const done = deleted.length;
      const left = unique.length - cursor;
      const base = err instanceof Error ? err.message : String(err);
      throw new Error(
        done > 0
          ? `Đã xóa ${done}/${unique.length} sản rồi dừng (còn ${left}). Đã tự thử lại ${consecutiveTimeoutRetries} lần sau mỗi ${Math.round(TIMEOUT_RETRY_DELAY_MS / 1000)}s vẫn lỗi. ${base}`
          : base,
      );
    }
  }

  return {
    deleted,
    deleted_count: deleted.length,
    errors,
  };
}
