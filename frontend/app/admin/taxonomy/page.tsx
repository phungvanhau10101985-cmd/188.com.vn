'use client';

/**
 * Admin /admin/taxonomy
 *
 * Quản lý cây danh mục + SEO cluster qua file Excel 4 sheet.
 *
 * Quy trình lần đầu:
 *   1. Bấm "Wipe products + categories" (xóa sạch products + 7 bảng category/seo cũ).
 *   2. Bấm "Tải file mẫu" để xem format (taxonomy_import.xlsx — 4 sheet).
 *   3. Upload file Excel → backend seed categories + seo_clusters.
 *   4. Quay sang trang Sản phẩm → import lại Excel SP — `category_id` sẽ tự link vào cat3.
 */

import { useCallback, useEffect, useState } from 'react';

import AdminLayout from '@/components/admin/AdminLayout';
import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';

interface TaxonomyInfo {
  categories: { cat1: number; cat2: number; cat3: number };
  clusters: number;
  products: { total: number; linked_to_cat3: number };
}

interface ImportSummary {
  ok: boolean;
  summary: { cat1: number; cat2: number; cat3: number; clusters: number };
  errors: {
    seo_clusters: string[];
    categories: string[];
    category_paths: string[];
  };
  meta: Record<string, string>;
  elapsed_ms: number;
}

interface WipeResult {
  ok: boolean;
  wiped: Record<string, number>;
  dropped: string[];
  created: string[];
  elapsed_ms: number;
}

function getAdminToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('admin_token');
}

async function callApi<T>(
  path: string,
  options: RequestInit & { isFormData?: boolean } = {},
): Promise<T> {
  const token = getAdminToken();
  if (!token) throw new Error('Chưa đăng nhập admin.');
  const url = `${getApiBaseUrl()}${path}`;
  const { isFormData, headers: extraHeaders, ...rest } = options;
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    ...ngrokFetchHeaders(),
    ...(extraHeaders as Record<string, string> | undefined),
  };
  if (!isFormData && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
  const res = await fetch(url, { ...rest, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail || err);
    throw new Error(detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return {} as T;
  return res.json();
}

async function downloadFile(path: string): Promise<void> {
  const token = getAdminToken();
  if (!token) throw new Error('Chưa đăng nhập admin.');
  const url = `${getApiBaseUrl()}${path}`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}`, ...ngrokFetchHeaders() },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  const blob = await res.blob();
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'taxonomy_import.xlsx';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

export default function TaxonomyAdminPage() {
  const [info, setInfo] = useState<TaxonomyInfo | null>(null);
  const [loadingInfo, setLoadingInfo] = useState(false);
  const [errorInfo, setErrorInfo] = useState<string | null>(null);

  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportSummary | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  const [wiping, setWiping] = useState(false);
  const [wipeResult, setWipeResult] = useState<WipeResult | null>(null);
  const [wipeError, setWipeError] = useState<string | null>(null);

  const reloadInfo = useCallback(async () => {
    setLoadingInfo(true);
    setErrorInfo(null);
    try {
      const data = await callApi<TaxonomyInfo>('/taxonomy/info');
      setInfo(data);
    } catch (e) {
      setErrorInfo(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingInfo(false);
    }
  }, []);

  useEffect(() => {
    void reloadInfo();
  }, [reloadInfo]);

  const handleSampleDownload = useCallback(async () => {
    try {
      await downloadFile('/taxonomy/sample');
    } catch (e) {
      alert(`Tải file mẫu thất bại: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, []);

  const handleWipe = useCallback(async () => {
    if (
      !window.confirm(
        'CẢNH BÁO: thao tác này XÓA toàn bộ products (mọi SP đã import) + 7 bảng categories/seo cũ.\n' +
          'Orders/users/cart không bị ảnh hưởng.\n\nTiếp tục?',
      )
    )
      return;
    setWiping(true);
    setWipeError(null);
    setWipeResult(null);
    try {
      const data = await callApi<WipeResult>('/taxonomy/wipe', { method: 'POST' });
      setWipeResult(data);
      void reloadInfo();
    } catch (e) {
      setWipeError(e instanceof Error ? e.message : String(e));
    } finally {
      setWiping(false);
    }
  }, [reloadInfo]);

  const handleImport = useCallback(
    async (file: File) => {
      setImporting(true);
      setImportError(null);
      setImportResult(null);
      try {
        const fd = new FormData();
        fd.append('file', file);
        const data = await callApi<ImportSummary>('/taxonomy/import', {
          method: 'POST',
          body: fd,
          isFormData: true,
        });
        setImportResult(data);
        void reloadInfo();
      } catch (e) {
        setImportError(e instanceof Error ? e.message : String(e));
      } finally {
        setImporting(false);
      }
    },
    [reloadInfo],
  );

  const totalErrors =
    (importResult?.errors.seo_clusters.length ?? 0) +
    (importResult?.errors.categories.length ?? 0) +
    (importResult?.errors.category_paths.length ?? 0);

  return (
    <AdminLayout>
      <div className="space-y-6 p-4 sm:p-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Cây danh mục (taxonomy)</h1>
          <p className="mt-1 text-sm text-gray-600">
            Import file Excel 4 sheet (categories, category_paths, seo_clusters, meta) để seed cây danh mục
            cha-con + landing SEO. Sản phẩm import sau sẽ tự link <code>category_id</code> theo slug cat3.
          </p>
        </div>

        <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">Trạng thái hiện tại</h2>
            <button
              type="button"
              onClick={() => void reloadInfo()}
              disabled={loadingInfo}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              {loadingInfo ? 'Đang tải…' : 'Làm mới'}
            </button>
          </div>
          {errorInfo ? (
            <div className="mt-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {errorInfo}
            </div>
          ) : null}
          {info ? (
            <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-5">
              <Stat label="Cat1" value={info.categories.cat1} />
              <Stat label="Cat2" value={info.categories.cat2} />
              <Stat label="Cat3" value={info.categories.cat3} />
              <Stat label="SEO clusters" value={info.clusters} />
              <Stat
                label="Products"
                value={`${info.products.linked_to_cat3} / ${info.products.total}`}
                hint="đã link cat3 / tổng"
              />
            </div>
          ) : null}
        </section>

        <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">1. Tải file mẫu</h2>
          <p className="mt-1 text-sm text-gray-600">
            Lấy bản mẫu hiện có trên server (<code>backend/temp_uploads/taxonomy_import.xlsx</code>) — chỉnh
            tay rồi upload lại ở mục bên dưới.
          </p>
          <button
            type="button"
            onClick={handleSampleDownload}
            className="mt-3 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            Tải taxonomy_import.xlsx
          </button>
        </section>

        <section className="rounded-lg border border-red-200 bg-red-50 p-4">
          <h2 className="text-lg font-semibold text-red-900">2. Wipe products + categories</h2>
          <p className="mt-1 text-sm text-red-800">
            Xoá toàn bộ <strong>products</strong> + 7 bảng category/seo cũ trước khi import lại taxonomy. Cần làm
            trước lần đầu (vì schema categories đã đổi). Orders/users/cart KHÔNG bị động đến.
          </p>
          <button
            type="button"
            onClick={() => void handleWipe()}
            disabled={wiping}
            className="mt-3 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
          >
            {wiping ? 'Đang xoá…' : 'Wipe ngay'}
          </button>
          {wipeError ? (
            <div className="mt-3 rounded border border-red-300 bg-white p-3 text-sm text-red-700">
              {wipeError}
            </div>
          ) : null}
          {wipeResult ? (
            <div className="mt-3 rounded border border-green-300 bg-white p-3 text-sm text-green-800">
              <div>Đã xoá ({wipeResult.elapsed_ms} ms):</div>
              <ul className="ml-4 list-disc">
                {Object.entries(wipeResult.wiped).map(([t, n]) => (
                  <li key={t}>
                    <code>{t}</code>: {n}
                  </li>
                ))}
              </ul>
              <div className="mt-2">
                Re-create: <code>{wipeResult.created.join(', ') || '(không cần)'}</code>
              </div>
            </div>
          ) : null}
        </section>

        <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">3. Upload taxonomy_import.xlsx</h2>
          <p className="mt-1 text-sm text-gray-600">
            File phải có đủ 4 sheet: <code>categories</code>, <code>category_paths</code>,{' '}
            <code>seo_clusters</code>, <code>meta</code>. Upsert theo cột <code>id</code> (string), an toàn
            chạy lại nhiều lần.
          </p>
          <input
            type="file"
            accept=".xlsx,.xls"
            disabled={importing}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleImport(f);
              e.target.value = '';
            }}
            className="mt-3 block w-full max-w-md text-sm text-gray-700 file:mr-3 file:rounded-md file:border-0 file:bg-indigo-50 file:px-3 file:py-1.5 file:text-sm file:text-indigo-700 hover:file:bg-indigo-100 disabled:opacity-50"
          />
          {importing ? (
            <div className="mt-3 text-sm text-gray-600">Đang xử lý… (file lớn có thể mất 10-30s)</div>
          ) : null}
          {importError ? (
            <div className="mt-3 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">
              {importError}
            </div>
          ) : null}
          {importResult ? (
            <div className="mt-4 space-y-3">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Stat label="Cat1 đã import" value={importResult.summary.cat1} />
                <Stat label="Cat2 đã import" value={importResult.summary.cat2} />
                <Stat label="Cat3 đã import" value={importResult.summary.cat3} />
                <Stat label="Cluster đã import" value={importResult.summary.clusters} />
              </div>
              <div className="text-xs text-gray-500">Thời gian xử lý: {importResult.elapsed_ms} ms</div>
              {totalErrors > 0 ? (
                <details className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                  <summary className="cursor-pointer font-medium">
                    {totalErrors} cảnh báo / lỗi (xem chi tiết)
                  </summary>
                  {(['seo_clusters', 'categories', 'category_paths'] as const).map((k) => {
                    const list = importResult.errors[k];
                    if (!list.length) return null;
                    return (
                      <div key={k} className="mt-2">
                        <div className="font-medium">
                          {k} ({list.length}):
                        </div>
                        <ul className="ml-4 list-disc">
                          {list.slice(0, 50).map((m, i) => (
                            <li key={`${k}-${i}`}>{m}</li>
                          ))}
                          {list.length > 50 ? <li>… +{list.length - 50} lỗi nữa</li> : null}
                        </ul>
                      </div>
                    );
                  })}
                </details>
              ) : (
                <div className="rounded border border-green-200 bg-green-50 p-2 text-sm text-green-800">
                  Không có lỗi.
                </div>
              )}
              {Object.keys(importResult.meta).length > 0 ? (
                <details className="rounded border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700">
                  <summary className="cursor-pointer font-medium">Meta thống kê</summary>
                  <ul className="ml-4 list-disc">
                    {Object.entries(importResult.meta).map(([k, v]) => (
                      <li key={k}>
                        <code>{k}</code>: {v}
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </div>
          ) : null}
        </section>
      </div>
    </AdminLayout>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: number | string;
  hint?: string;
}) {
  return (
    <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
      <div className="text-xs uppercase tracking-wide text-gray-500">{label}</div>
      <div className="mt-1 text-xl font-semibold text-gray-900">{value}</div>
      {hint ? <div className="mt-0.5 text-xs text-gray-500">{hint}</div> : null}
    </div>
  );
}
