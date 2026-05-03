'use client';

/**
 * Admin /admin/taxonomy
 *
 * Quản lý cây danh mục + SEO cluster qua file Excel 4 sheet hoặc form thủ công (cùng pipeline upsert).
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';

interface TaxonomyInfo {
  categories: { cat1: number; cat2: number; cat3: number };
  clusters: number;
  products: { total: number; linked_to_cat3: number };
}

interface UpsertCounts {
  inserted: number;
  updated: number;
}

interface ImportSummary {
  ok: boolean;
  summary: {
    categories: {
      '1': UpsertCounts;
      '2': UpsertCounts;
      '3': UpsertCounts;
    };
    clusters: UpsertCounts & { in_database_after: number };
  };
  errors: {
    seo_clusters: string[];
    categories: string[];
    category_paths: string[];
  };
  meta: Record<string, string>;
  elapsed_ms: number;
}

interface FormTreeNode {
  db_id: number;
  external_id: string | null;
  parent_id?: number | null;
  level: number;
  name: string;
  slug: string;
  full_slug: string;
  sort_order?: number;
  seo_index: boolean;
  children: FormTreeNode[];
}

interface ClusterOption {
  external_id: string;
  slug: string;
  name: string;
  index_policy: string;
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

  const [formTree, setFormTree] = useState<FormTreeNode[]>([]);
  const [clusters, setClusters] = useState<ClusterOption[]>([]);
  const [formLoading, setFormLoading] = useState(false);

  const [cat1New, setCat1New] = useState(false);
  const [cat1ExistingId, setCat1ExistingId] = useState('');
  const [cat1Name, setCat1Name] = useState('');
  const [cat1Slug, setCat1Slug] = useState('');

  const [cat2New, setCat2New] = useState(true);
  const [cat2ExistingId, setCat2ExistingId] = useState('');
  const [cat2Name, setCat2Name] = useState('');
  const [cat2Slug, setCat2Slug] = useState('');

  const [cat3Name, setCat3Name] = useState('');
  const [cat3Slug, setCat3Slug] = useState('');
  const [cat3SeoIndex, setCat3SeoIndex] = useState<'index' | 'noindex'>('noindex');
  const [cat3SortOrder, setCat3SortOrder] = useState(0);

  const [clusterNew, setClusterNew] = useState(true);
  const [clusterExistingId, setClusterExistingId] = useState('');
  const [clusterName, setClusterName] = useState('');
  const [clusterSlug, setClusterSlug] = useState('');
  const [clusterIndexPolicy, setClusterIndexPolicy] = useState<'index' | 'noindex'>('index');

  const [isActive, setIsActive] = useState(true);

  const [manualSubmitting, setManualSubmitting] = useState(false);
  const [manualResult, setManualResult] = useState<ImportSummary | null>(null);
  const [manualError, setManualError] = useState<string | null>(null);

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

  const loadFormRefs = useCallback(async () => {
    setFormLoading(true);
    try {
      const [t, c] = await Promise.all([
        callApi<{ tree: FormTreeNode[] }>('/taxonomy/form-tree'),
        callApi<{ clusters: ClusterOption[] }>('/taxonomy/clusters-list'),
      ]);
      setFormTree(Array.isArray(t.tree) ? t.tree : []);
      setClusters(Array.isArray(c.clusters) ? c.clusters : []);
    } catch {
      // Tree/chưa đăng nhập — form vẫn dùng toàn tạo mới
    } finally {
      setFormLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadFormRefs();
  }, [loadFormRefs]);

  useEffect(() => {
    if (cat1New) {
      setCat2New(true);
      setCat2ExistingId('');
    }
  }, [cat1New]);

  const cat1Options = useMemo(
    () => formTree.filter((n) => Boolean(n.external_id) && n.level === 1),
    [formTree],
  );

  const cat2Options = useMemo(() => {
    if (!cat1ExistingId) return [];
    const n1 = formTree.find((x) => x.external_id === cat1ExistingId);
    return (n1?.children || []).filter((c) => Boolean(c.external_id) && c.level === 2);
  }, [formTree, cat1ExistingId]);

  const handleSampleDownload = useCallback(async () => {
    try {
      await downloadFile('/taxonomy/sample');
    } catch (e) {
      alert(`Tải file mẫu thất bại: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, []);

  const handleStructureOnlyDownload = useCallback(async () => {
    try {
      await downloadFile('/taxonomy/sample?blank_template=true');
    } catch (e) {
      alert(`Tải mẫu cấu trúc thất bại: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, []);

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
        void loadFormRefs();
      } catch (e) {
        setImportError(e instanceof Error ? e.message : String(e));
      } finally {
        setImporting(false);
      }
    },
    [reloadInfo, loadFormRefs],
  );

  const handleManualSubmit = useCallback(async () => {
    const err = (msg: string) => {
      alert(msg);
    };
    if (!cat3Name.trim()) {
      err('Nhập tên cấp 3 (danh mục lá).');
      return;
    }
    if (!cat1New) {
      if (!cat1ExistingId) {
        err('Chọn cấp 1 có sẵn hoặc bật «Tạo mới cấp 1».');
        return;
      }
    } else {
      if (!cat1Name.trim()) {
        err('Nhập tên cấp 1 mới.');
        return;
      }
    }
    if (!cat2New) {
      if (!cat2ExistingId) {
        err('Chọn cấp 2 có sẵn.');
        return;
      }
    } else {
      if (!cat2Name.trim()) {
        err('Nhập tên cấp 2 mới.');
        return;
      }
    }
    if (!clusterNew) {
      if (!clusterExistingId) {
        err('Chọn SEO cluster có sẵn.');
        return;
      }
    } else {
      if (!clusterName.trim()) {
        err('Nhập tên SEO cluster mới.');
        return;
      }
    }

    setManualSubmitting(true);
    setManualError(null);
    setManualResult(null);
    try {
      const payload: Record<string, unknown> = {
        cat3_name: cat3Name.trim(),
        cat3_slug: cat3Slug.trim() || null,
        cat3_seo_index: cat3SeoIndex,
        cat3_sort_order: Number.isFinite(cat3SortOrder) ? cat3SortOrder : 0,
        is_active: isActive,
      };
      if (cat1New) {
        payload.cat1_name = cat1Name.trim();
        payload.cat1_slug = cat1Slug.trim() || null;
      } else {
        payload.cat1_existing_external_id = cat1ExistingId;
      }
      if (cat2New) {
        payload.cat2_name = cat2Name.trim();
        payload.cat2_slug = cat2Slug.trim() || null;
      } else {
        payload.cat2_existing_external_id = cat2ExistingId;
      }
      if (clusterNew) {
        payload.cluster_name = clusterName.trim();
        payload.cluster_slug = clusterSlug.trim() || null;
        payload.cluster_index_policy = clusterIndexPolicy;
      } else {
        payload.cluster_existing_external_id = clusterExistingId;
      }
      const data = await callApi<ImportSummary>('/taxonomy/manual-upsert', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      setManualResult(data);
      void reloadInfo();
      void loadFormRefs();
    } catch (e) {
      setManualError(e instanceof Error ? e.message : String(e));
    } finally {
      setManualSubmitting(false);
    }
  }, [
    cat1New,
    cat1ExistingId,
    cat1Name,
    cat1Slug,
    cat2New,
    cat2ExistingId,
    cat2Name,
    cat2Slug,
    cat3Name,
    cat3Slug,
    cat3SeoIndex,
    cat3SortOrder,
    clusterNew,
    clusterExistingId,
    clusterName,
    clusterSlug,
    clusterIndexPolicy,
    isActive,
    reloadInfo,
    loadFormRefs,
  ]);

  const totalErrors =
    (importResult?.errors.seo_clusters.length ?? 0) +
    (importResult?.errors.categories.length ?? 0) +
    (importResult?.errors.category_paths.length ?? 0);

  const totalManualErrors =
    (manualResult?.errors.seo_clusters.length ?? 0) +
    (manualResult?.errors.categories.length ?? 0) +
    (manualResult?.errors.category_paths.length ?? 0);

  return (
      <div className="space-y-6 p-4 sm:p-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Cây danh mục (taxonomy)</h1>
          <p className="mt-1 text-sm text-gray-600">
            Import Excel 4 sheet hoặc form thủ công — cùng cơ chế: khớp theo cột <code>id</code> (chuỗi, ví dụ{' '}
            <code>cat3__…</code>, <code>cluster__…</code>). <strong>Có sẵn trong DB → cập nhật theo file; chưa có →
            thêm mới.</strong> Import lặp lại không xóa dòng chỉ vì thiếu trong file. Sản phẩm tự link{' '}
            <code>category_id</code> theo slug cat3.
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
            Tải <strong>taxonomy_import.xlsx</strong>: bản đầy đủ dòng trong{' '}
            <code>backend/temp_uploads/</code> (nếu deploy có); không thì{' '}
            <code>backend/assets/taxonomy_import_template.xlsx</code> — đủ 4 sheet và đủ cột (trong đó{' '}
            <code>category_paths</code> có cat1–cat3 + slug cluster). Luôn có thể sinh từ API nếu thiếu cả hai file.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void handleSampleDownload()}
              className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
            >
              Tải taxonomy_import.xlsx
            </button>
            <button
              type="button"
              onClick={() => void handleStructureOnlyDownload()}
              className="rounded-md border border-indigo-600 bg-white px-4 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-50"
            >
              Chỉ mẫu đủ cột (nhẹ)
            </button>
          </div>
        </section>

        <section className="rounded-lg border border-amber-100 bg-amber-50 p-4 text-sm text-amber-950">
          <p className="font-medium text-amber-900">Migration taxonomy lần đầu (xoá SP + tái tạo bảng danh mục)</p>
          <p className="mt-2 text-amber-900/90">
            Không có trên web. Trên máy dev mở thư mục <code className="rounded bg-white/70 px-1">backend</code>, chạy:{' '}
            <code className="rounded bg-white/70 px-1">python scripts/wipe_taxonomy_migration.py</code>
            {' '}(hoặc thêm <code className="rounded bg-white/70 px-1">--yes</code>). Sau đó dùng bước upload bên dưới.
          </p>
        </section>

        <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">2. Upload taxonomy_import.xlsx</h2>
          <p className="mt-1 text-sm text-gray-600">
            File đủ 4 sheet: <code>categories</code>, <code>category_paths</code>, <code>seo_clusters</code>,{' '}
            <code>meta</code>. Khóa là cột <code>id</code>: <strong>trùng id → ghi đè/cập nhật; id mới → chèn
            bản ghi.</strong> Sheet <code>category_paths</code> dùng để đối chiếu cat3/cluster (không xóa dữ liệu
            khi thiếu dòng).
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
                <StatUpsert
                  label="Cat1 (theo file)"
                  inserted={importResult.summary.categories['1'].inserted}
                  updated={importResult.summary.categories['1'].updated}
                />
                <StatUpsert
                  label="Cat2 (theo file)"
                  inserted={importResult.summary.categories['2'].inserted}
                  updated={importResult.summary.categories['2'].updated}
                />
                <StatUpsert
                  label="Cat3 (theo file)"
                  inserted={importResult.summary.categories['3'].inserted}
                  updated={importResult.summary.categories['3'].updated}
                />
                <StatUpsert
                  label="Cluster (dòng trong file)"
                  inserted={importResult.summary.clusters.inserted}
                  updated={importResult.summary.clusters.updated}
                  hint={`Tổng cluster trong DB sau import: ${importResult.summary.clusters.in_database_after}`}
                />
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

        <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">3. Thêm nhánh thủ công (upsert như Excel)</h2>
          <p className="mt-1 text-sm text-gray-600">
            Cùng quy tắc <code>id</code> tự sinh/khớp: <strong>đã tồn tại → cập nhật; chưa có → tạo mới.</strong> Chọn
            hoặc tạo cấp 1 → cấp 2 → nhập cấp 3, gán SEO cluster (có sẵn hoặc mới).{' '}
            <strong>seo_index</strong> cấp 3: <code>index</code> = URL cấp 3 có thể index; <code>noindex</code> = thường
            gom về landing <code>/c/…</code> (giống file mẫu). Cluster <strong>index_policy</strong> điều khiển trang
            <code>/c/slug</code>.
          </p>
          {formLoading ? (
            <p className="mt-2 text-sm text-gray-500">Đang tải cây danh mục / clusters…</p>
          ) : null}

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div className="space-y-3 rounded-md border border-gray-100 bg-gray-50/80 p-3">
              <h3 className="text-sm font-semibold text-gray-800">Cấp 1</h3>
              <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={cat1New}
                  onChange={(e) => {
                    const v = e.target.checked;
                    setCat1New(v);
                    if (v) setCat1ExistingId('');
                  }}
                />
                Tạo mới cấp 1
              </label>
              {!cat1New ? (
                <select
                  className="w-full rounded-md border border-gray-300 px-2 py-2 text-sm"
                  value={cat1ExistingId}
                  onChange={(e) => {
                    setCat1ExistingId(e.target.value);
                    setCat2ExistingId('');
                  }}
                >
                  <option value="">— Chọn cấp 1 có sẵn —</option>
                  {cat1Options.map((n) => (
                    <option key={n.external_id!} value={n.external_id!}>
                      {n.name}
                    </option>
                  ))}
                </select>
              ) : (
                <div className="flex flex-col gap-2">
                  <input
                    className="rounded-md border border-gray-300 px-2 py-2 text-sm"
                    placeholder="Tên cấp 1 *"
                    value={cat1Name}
                    onChange={(e) => setCat1Name(e.target.value)}
                  />
                  <input
                    className="rounded-md border border-gray-300 px-2 py-2 text-sm"
                    placeholder="Slug (để trống → sinh từ tên)"
                    value={cat1Slug}
                    onChange={(e) => setCat1Slug(e.target.value)}
                  />
                </div>
              )}
            </div>

            <div className="space-y-3 rounded-md border border-gray-100 bg-gray-50/80 p-3">
              <h3 className="text-sm font-semibold text-gray-800">Cấp 2</h3>
              {!cat1New ? (
                <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={cat2New}
                    disabled={cat1New}
                    onChange={(e) => {
                      const v = e.target.checked;
                      setCat2New(v);
                      if (v) setCat2ExistingId('');
                    }}
                  />
                  Tạo mới cấp 2
                </label>
              ) : (
                <p className="text-xs text-gray-500">Đang tạo cấp 1 mới — luôn nhập cấp 2 mới bên dưới.</p>
              )}
              {!cat2New && !cat1New ? (
                <select
                  className="w-full rounded-md border border-gray-300 px-2 py-2 text-sm"
                  value={cat2ExistingId}
                  onChange={(e) => setCat2ExistingId(e.target.value)}
                  disabled={!cat1ExistingId}
                >
                  <option value="">— Chọn cấp 2 có sẵn —</option>
                  {cat2Options.map((n) => (
                    <option key={n.external_id!} value={n.external_id!}>
                      {n.name}
                    </option>
                  ))}
                </select>
              ) : (
                <div className="flex flex-col gap-2">
                  <input
                    className="rounded-md border border-gray-300 px-2 py-2 text-sm"
                    placeholder="Tên cấp 2 *"
                    value={cat2Name}
                    onChange={(e) => setCat2Name(e.target.value)}
                  />
                  <input
                    className="rounded-md border border-gray-300 px-2 py-2 text-sm"
                    placeholder="Slug (để trống → sinh từ tên)"
                    value={cat2Slug}
                    onChange={(e) => setCat2Slug(e.target.value)}
                  />
                </div>
              )}
            </div>

            <div className="space-y-3 rounded-md border border-gray-100 bg-gray-50/80 p-3 lg:col-span-2">
              <h3 className="text-sm font-semibold text-gray-800">Cấp 3 (danh mục lá) &amp; hiển thị</h3>
              <div className="grid gap-3 sm:grid-cols-2">
                <input
                  className="rounded-md border border-gray-300 px-2 py-2 text-sm"
                  placeholder="Tên cấp 3 *"
                  value={cat3Name}
                  onChange={(e) => setCat3Name(e.target.value)}
                />
                <input
                  className="rounded-md border border-gray-300 px-2 py-2 text-sm"
                  placeholder="Slug cấp 3 (tuỳ chọn)"
                  value={cat3Slug}
                  onChange={(e) => setCat3Slug(e.target.value)}
                />
              </div>
              <div className="flex flex-wrap items-center gap-4 text-sm">
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-gray-500">Trang cấp 3 (SEO)</span>
                  <select
                    className="rounded-md border border-gray-300 px-2 py-1.5"
                    value={cat3SeoIndex}
                    onChange={(e) => setCat3SeoIndex(e.target.value as 'index' | 'noindex')}
                  >
                    <option value="noindex">noindex (thường dùng — vào cluster)</option>
                    <option value="index">index</option>
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-gray-500">Thứ tự sort cấp 3</span>
                  <input
                    type="number"
                    className="w-24 rounded-md border border-gray-300 px-2 py-1.5"
                    value={cat3SortOrder}
                    onChange={(e) => setCat3SortOrder(Number.parseInt(e.target.value, 10) || 0)}
                  />
                </label>
                <label className="flex items-center gap-2 pt-5">
                  <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
                  Đang hoạt động
                </label>
              </div>
            </div>

            <div className="space-y-3 rounded-md border border-indigo-100 bg-indigo-50/40 p-3 lg:col-span-2">
              <h3 className="text-sm font-semibold text-gray-800">SEO cluster (landing /c/slug)</h3>
              <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={clusterNew}
                  onChange={(e) => {
                    const v = e.target.checked;
                    setClusterNew(v);
                    if (v) setClusterExistingId('');
                  }}
                />
                Tạo cluster mới
              </label>
              {!clusterNew ? (
                <select
                  className="w-full max-w-xl rounded-md border border-gray-300 px-2 py-2 text-sm"
                  value={clusterExistingId}
                  onChange={(e) => setClusterExistingId(e.target.value)}
                >
                  <option value="">— Chọn cluster —</option>
                  {clusters.map((c) => (
                    <option key={c.external_id} value={c.external_id}>
                      {c.name} ({c.slug}) · {c.index_policy}
                    </option>
                  ))}
                </select>
              ) : (
                <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-end">
                  <input
                    className="min-w-[10rem] flex-1 rounded-md border border-gray-300 px-2 py-2 text-sm"
                    placeholder="Tên cluster *"
                    value={clusterName}
                    onChange={(e) => setClusterName(e.target.value)}
                  />
                  <input
                    className="min-w-[10rem] flex-1 rounded-md border border-gray-300 px-2 py-2 text-sm"
                    placeholder="Slug cluster (tuỳ chọn)"
                    value={clusterSlug}
                    onChange={(e) => setClusterSlug(e.target.value)}
                  />
                  <label className="flex flex-col gap-1 text-sm">
                    <span className="text-xs text-gray-500">index policy</span>
                    <select
                      className="rounded-md border border-gray-300 px-2 py-2"
                      value={clusterIndexPolicy}
                      onChange={(e) => setClusterIndexPolicy(e.target.value as 'index' | 'noindex')}
                    >
                      <option value="index">index</option>
                      <option value="noindex">noindex</option>
                    </select>
                  </label>
                </div>
              )}
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={manualSubmitting}
              onClick={() => void handleManualSubmit()}
              className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {manualSubmitting ? 'Đang ghi…' : 'Lưu nhánh (upsert)'}
            </button>
            <button
              type="button"
              onClick={() => void loadFormRefs()}
              className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
            >
              Tải lại cây / clusters
            </button>
          </div>

          {manualError ? (
            <div className="mt-3 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">{manualError}</div>
          ) : null}

          {manualResult ? (
            <div className="mt-4 space-y-3">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <StatUpsert
                  label="Cat1 (theo file)"
                  inserted={manualResult.summary.categories['1'].inserted}
                  updated={manualResult.summary.categories['1'].updated}
                />
                <StatUpsert
                  label="Cat2 (theo file)"
                  inserted={manualResult.summary.categories['2'].inserted}
                  updated={manualResult.summary.categories['2'].updated}
                />
                <StatUpsert
                  label="Cat3 (theo file)"
                  inserted={manualResult.summary.categories['3'].inserted}
                  updated={manualResult.summary.categories['3'].updated}
                />
                <StatUpsert
                  label="Cluster (dòng trong file)"
                  inserted={manualResult.summary.clusters.inserted}
                  updated={manualResult.summary.clusters.updated}
                  hint={`Tổng cluster trong DB: ${manualResult.summary.clusters.in_database_after}`}
                />
              </div>
              <div className="text-xs text-gray-500">Thời gian: {manualResult.elapsed_ms} ms</div>
              {totalManualErrors > 0 ? (
                <details className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                  <summary className="cursor-pointer font-medium">
                    {totalManualErrors} cảnh báo / lỗi (xem chi tiết)
                  </summary>
                  {(['seo_clusters', 'categories', 'category_paths'] as const).map((k) => {
                    const list = manualResult.errors[k];
                    if (!list.length) return null;
                    return (
                      <div key={k} className="mt-2">
                        <div className="font-medium">
                          {k} ({list.length}):
                        </div>
                        <ul className="ml-4 list-disc">
                          {list.slice(0, 30).map((m, i) => (
                            <li key={`m-${k}-${i}`}>{m}</li>
                          ))}
                        </ul>
                      </div>
                    );
                  })}
                </details>
              ) : (
                <div className="rounded border border-green-200 bg-green-50 p-2 text-sm text-green-800">
                  Không có lỗi validation.
                </div>
              )}
            </div>
          ) : null}
        </section>
      </div>
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

function StatUpsert({
  label,
  inserted,
  updated,
  hint,
}: {
  label: string;
  inserted: number;
  updated: number;
  hint?: string;
}) {
  const total = inserted + updated;
  return (
    <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
      <div className="text-xs uppercase tracking-wide text-gray-500">{label}</div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-sm">
        <span className="text-emerald-700 font-semibold">+ Thêm: {inserted}</span>
        <span className="text-amber-800 font-semibold">⟲ Cập nhật: {updated}</span>
      </div>
      <div className="mt-1 text-xs text-gray-600">Tổng dòng xử lý: {total}</div>
      {hint ? <div className="mt-0.5 text-xs text-gray-500">{hint}</div> : null}
    </div>
  );
}
