/**
 * Xóa SP admin theo product_id Excel (có dấu /) — POST body, không đưa ID vào path URL.
 * Dùng proxy /api/v1 (ổn định trên VPS); tránh route riêng /api/admin/... có thể chưa deploy.
 */
import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';

export type AdminBulkDeleteProductsResult = {
  deleted: string[];
  deleted_count: number;
  errors: { product_id: string; status: number; detail: string }[];
};

function adminToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('admin_token');
}

export async function bulkDeleteAdminProducts(
  productIds: string[],
): Promise<AdminBulkDeleteProductsResult> {
  const token = adminToken();
  if (!token) throw new Error('Chưa đăng nhập admin');

  const res = await fetch(`${getApiBaseUrl()}/products/by-product-id/bulk-delete`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...ngrokFetchHeaders(),
    },
    body: JSON.stringify({ product_ids: productIds }),
    cache: 'no-store',
  });

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
          ? data.detail.map((x) => (typeof x === 'object' && x && 'msg' in x ? String((x as { msg?: unknown }).msg) : String(x))).join('; ')
          : res.statusText;
    const hint =
      res.status === 404 && !detail
        ? 'API xóa chưa có trên server — deploy lại frontend + backend (endpoint POST /products/by-product-id/bulk-delete).'
        : '';
    throw new Error(`[${res.status}] ${detail || hint || 'Xóa thất bại'}`);
  }

  return {
    deleted: data.deleted ?? [],
    deleted_count: data.deleted_count ?? 0,
    errors: data.errors ?? [],
  };
}
