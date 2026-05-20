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

  interface MismatchItem {
    product_id: string;
    name: string;
    category: string | null;
    subcategory: string | null;
    sub_subcategory: string | null;
    inferred_domain_label?: string | null;
    reason: string;
  }
  interface MismatchScanResult {
    items: MismatchItem[];
    count: number;
    scanned: number;
    skip: number;
    limit: number;
  }
  const [mismatchL1, setMismatchL1] = useState('');
  const [mismatchLimit, setMismatchLimit] = useState(50);
  const [mismatchScanning, setMismatchScanning] = useState(false);
  const [mismatchScanAllRunning, setMismatchScanAllRunning] = useState(false);
  const [mismatchScan, setMismatchScan] = useState<MismatchScanResult | null>(null);
  const [mismatchScanAll, setMismatchScanAll] = useState<{
    total_mismatch: number;
    category_count: number;
    categories: {
      category_l1: string;
      count: number;
      scanned: number;
      samples?: MismatchItem[];
    }[];
  } | null>(null);
  const [mismatchScanError, setMismatchScanError] = useState<string | null>(null);
  const [mismatchReclassifying, setMismatchReclassifying] = useState(false);
  const [mismatchReclassifyResult, setMismatchReclassifyResult] = useState<{
    ok: number;
    failed: number;
    dry_run: boolean;
    results: { product_id: string; ok?: boolean; error?: string; new?: Record<string, unknown> }[];
  } | null>(null);
  const [mismatchReclassifyAllResult, setMismatchReclassifyAllResult] = useState<{
    ok: number;
    failed: number;
    processed: number;
    dry_run: boolean;
    categories_processed: number;
    categories: {
      category_l1: string;
      skipped?: boolean;
      ok: number;
      failed: number;
      processed: number;
    }[];
  } | null>(null);
  const [mismatchReclassifyError, setMismatchReclassifyError] = useState<string | null>(null);

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

  useEffect(() => {
    if (!mismatchL1 && cat1Options.length > 0) {
      setMismatchL1(cat1Options[0].name);
    }
  }, [cat1Options, mismatchL1]);

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

  const runMismatchScanForL1 = useCallback(
    async (l1: string) => {
      const cat = l1.trim();
      if (!cat) {
        setMismatchScanError('Chọn danh mục cấp 1 trước khi quét.');
        return;
      }
      setMismatchScanning(true);
      setMismatchScanError(null);
      setMismatchReclassifyResult(null);
      setMismatchReclassifyAllResult(null);
      setMismatchScanAll(null);
      try {
        const data = await callApi<MismatchScanResult>('/taxonomy/mismatch-scan', {
          method: 'POST',
          body: JSON.stringify({
            skip: 0,
            limit: mismatchLimit,
            category_l1: cat,
            is_active: true,
            max_scan: 12000,
          }),
        });
        setMismatchScan(data);
      } catch (e) {
        setMismatchScanError(e instanceof Error ? e.message : String(e));
      } finally {
        setMismatchScanning(false);
      }
    },
    [mismatchLimit],
  );

  const handleMismatchScan = useCallback(() => {
    void runMismatchScanForL1(mismatchL1);
  }, [mismatchL1, runMismatchScanForL1]);

  const handleMismatchScanAll = useCallback(async () => {
    setMismatchScanAllRunning(true);
    setMismatchScanError(null);
    setMismatchReclassifyResult(null);
    setMismatchReclassifyAllResult(null);
    setMismatchScan(null);
    try {
      const data = await callApi<{
        total_mismatch: number;
        category_count: number;
        categories: {
          category_l1: string;
          count: number;
          scanned: number;
          samples?: MismatchItem[];
        }[];
      }>('/taxonomy/mismatch-scan-all', {
        method: 'POST',
        body: JSON.stringify({
          limit_per_l1: mismatchLimit,
          is_active: true,
          max_scan_per_l1: 12000,
          sample_items: 2,
        }),
      });
      setMismatchScanAll(data);
    } catch (e) {
      setMismatchScanError(e instanceof Error ? e.message : String(e));
    } finally {
      setMismatchScanAllRunning(false);
    }
  }, [mismatchLimit]);

  const handleMismatchDrillDown = useCallback(
    (l1: string) => {
      setMismatchL1(l1);
      void runMismatchScanForL1(l1);
    },
    [runMismatchScanForL1],
  );

  const handleMismatchReclassify = useCallback(
    async (dryRun: boolean) => {
      const ids = (mismatchScan?.items || []).map((x) => x.product_id).filter(Boolean);
      if (!ids.length) {
        alert('Chưa có danh sách — bấm «Quét lệch taxonomy» trước.');
        return;
      }
      if (
        !dryRun &&
        !window.confirm(
          `Chạy DeepSeek tái gán taxonomy cho tối đa ${Math.min(ids.length, mismatchLimit)} SP? Việc này có thể mất vài phút.`,
        )
      ) {
        return;
      }
      setMismatchReclassifying(true);
      setMismatchReclassifyError(null);
      setMismatchReclassifyAllResult(null);
      try {
        const data = await callApi<{
          ok: number;
          failed: number;
          dry_run: boolean;
          results: { product_id: string; ok?: boolean; error?: string; new?: Record<string, unknown> }[];
        }>('/taxonomy/mismatch-reclassify', {
          method: 'POST',
          body: JSON.stringify({
            product_ids: ids,
            category_l1: mismatchL1.trim() || null,
            is_active: true,
            limit: mismatchLimit,
            only_mismatched: true,
            dry_run: dryRun,
          }),
        });
        setMismatchReclassifyResult(data);
        if (!dryRun) void reloadInfo();
      } catch (e) {
        setMismatchReclassifyError(e instanceof Error ? e.message : String(e));
      } finally {
        setMismatchReclassifying(false);
      }
    },
    [mismatchScan, mismatchL1, mismatchLimit, reloadInfo],
  );

  const mismatchL1WithIssues = useMemo(
    () => (mismatchScanAll?.categories || []).filter((row) => row.count > 0).map((row) => row.category_l1),
    [mismatchScanAll],
  );

  const handleMismatchReclassifyAll = useCallback(
    async (dryRun: boolean) => {
      const limitPerL1 = Math.min(Math.max(1, mismatchLimit), 100);
      const catCount = mismatchL1WithIssues.length;
      const estTotal = mismatchScanAll?.total_mismatch ?? 0;
      const scopeLabel =
        catCount > 0
          ? `${catCount} danh mục có lệch (tối đa ${limitPerL1} SP / danh mục)`
          : `mọi danh mục cấp 1 (tối đa ${limitPerL1} SP / danh mục)`;

      if (
        !dryRun &&
        !window.confirm(
          catCount > 0
            ? `Chạy DeepSeek tái gán taxonomy cho ${scopeLabel}? Ước tính tối đa ~${Math.min(estTotal, catCount * limitPerL1)} SP — có thể mất rất lâu và tốn API.`
            : `Chưa quét tổng — vẫn chạy trên ${scopeLabel}. Nên «Quét tất cả danh mục» trước để biết số lượng. Tiếp tục?`,
        )
      ) {
        return;
      }

      setMismatchReclassifying(true);
      setMismatchReclassifyError(null);
      setMismatchReclassifyAllResult(null);
      setMismatchReclassifyResult(null);
      try {
        const data = await callApi<{
          ok: number;
          failed: number;
          processed: number;
          dry_run: boolean;
          categories_processed: number;
          categories: {
            category_l1: string;
            skipped?: boolean;
            ok: number;
            failed: number;
            processed: number;
          }[];
        }>('/taxonomy/mismatch-reclassify-all', {
          method: 'POST',
          body: JSON.stringify({
            limit_per_l1: limitPerL1,
            is_active: true,
            max_scan_per_l1: 12000,
            only_mismatched: true,
            dry_run: dryRun,
            only_categories_with_mismatch: true,
            category_l1_names: catCount > 0 ? mismatchL1WithIssues : null,
          }),
        });
        setMismatchReclassifyAllResult(data);
        if (!dryRun) void reloadInfo();
      } catch (e) {
        setMismatchReclassifyError(e instanceof Error ? e.message : String(e));
      } finally {
        setMismatchReclassifying(false);
      }
    },
    [mismatchLimit, mismatchL1WithIssues, mismatchScanAll, reloadInfo],
  );

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

        <section className="rounded-lg border border-orange-200 bg-white p-4 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">Sửa taxonomy lệch (theo tên SP)</h2>
          <p className="mt-1 text-sm text-gray-600">
            <strong>Quét tất cả</strong> → <strong>Tái gán tất cả danh mục</strong> (không cần chọn từng nhánh).
            Hoặc quét/tái gán <strong>một danh mục</strong> qua dropdown. Cần{' '}
            <code>IMPORT_LINK_DEEPSEEK_TAXONOMY_ENABLED</code>.
          </p>
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="flex min-w-[14rem] flex-col gap-1 text-sm">
              <span className="text-xs font-medium text-gray-600">Danh mục cấp 1</span>
              <select
                className="rounded-md border border-gray-300 bg-white px-2 py-2 text-sm"
                value={mismatchL1}
                onChange={(e) => {
                  setMismatchL1(e.target.value);
                  setMismatchScan(null);
                }}
                disabled={formLoading || cat1Options.length === 0}
              >
                {cat1Options.length === 0 ? (
                  <option value="">— Chưa có cây danh mục —</option>
                ) : (
                  cat1Options.map((c) => (
                    <option key={c.external_id} value={c.name}>
                      {c.name}
                    </option>
                  ))
                )}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-gray-500">Số kết quả tối đa</span>
              <input
                type="number"
                min={1}
                max={100}
                className="w-24 rounded-md border border-gray-300 px-2 py-2 text-sm"
                value={mismatchLimit}
                onChange={(e) => setMismatchLimit(Number(e.target.value) || 50)}
              />
            </label>
            <button
              type="button"
              disabled={mismatchScanning || !mismatchL1.trim()}
              onClick={() => handleMismatchScan()}
              className="rounded-md bg-orange-600 px-4 py-2 text-sm font-medium text-white hover:bg-orange-700 disabled:opacity-50"
            >
              {mismatchScanning ? 'Đang quét…' : 'Quét danh mục này'}
            </button>
            <button
              type="button"
              disabled={mismatchScanAllRunning || mismatchScanning}
              onClick={() => void handleMismatchScanAll()}
              className="rounded-md border border-orange-600 bg-white px-4 py-2 text-sm font-medium text-orange-700 hover:bg-orange-50 disabled:opacity-50"
            >
              {mismatchScanAllRunning ? 'Đang quét tất cả…' : 'Quét tất cả danh mục'}
            </button>
            <button
              type="button"
              disabled={mismatchReclassifying || !mismatchScan?.items?.length}
              onClick={() => void handleMismatchReclassify(true)}
              className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              Xem trước (dry-run)
            </button>
            <button
              type="button"
              disabled={mismatchReclassifying || !mismatchScan?.items?.length}
              onClick={() => void handleMismatchReclassify(false)}
              className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {mismatchReclassifying ? 'Đang gán lại…' : 'Tái gán taxonomy (DeepSeek)'}
            </button>
          </div>
          {mismatchScanError ? (
            <div className="mt-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {mismatchScanError}
            </div>
          ) : null}
          {mismatchScanAll ? (
            <div className="mt-3 space-y-2">
              <p className="text-sm text-gray-700">
                Tổng <strong>{mismatchScanAll.total_mismatch}</strong> SP lệch /{' '}
                <strong>{mismatchScanAll.category_count}</strong> danh mục.
                {mismatchL1WithIssues.length > 0 ? (
                  <>
                    {' '}
                    — <strong>{mismatchL1WithIssues.length}</strong> danh mục có thể tái gán hàng loạt.
                  </>
                ) : null}
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={mismatchReclassifying || mismatchScanAllRunning}
                  onClick={() => void handleMismatchReclassifyAll(true)}
                  className="rounded-md border border-indigo-300 bg-white px-3 py-1.5 text-sm text-indigo-800 hover:bg-indigo-50 disabled:opacity-50"
                >
                  Xem trước tái gán tất cả
                </button>
                <button
                  type="button"
                  disabled={
                    mismatchReclassifying ||
                    mismatchScanAllRunning ||
                    (mismatchScanAll.total_mismatch <= 0 && mismatchL1WithIssues.length === 0)
                  }
                  onClick={() => void handleMismatchReclassifyAll(false)}
                  className="rounded-md bg-indigo-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-800 disabled:opacity-50"
                >
                  {mismatchReclassifying ? 'Đang gán lại tất cả…' : 'Tái gán tất cả danh mục (DeepSeek)'}
                </button>
              </div>
              <div className="max-h-64 overflow-auto rounded border border-gray-200">
                <table className="min-w-full text-left text-xs">
                  <thead className="sticky top-0 bg-gray-50 text-gray-600">
                    <tr>
                      <th className="px-2 py-2">Danh mục cấp 1</th>
                      <th className="px-2 py-2">SP lệch</th>
                      <th className="px-2 py-2">Đã quét</th>
                      <th className="px-2 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {mismatchScanAll.categories
                      .filter((row) => row.count > 0)
                      .map((row) => (
                        <tr key={row.category_l1} className="border-t border-gray-100">
                          <td className="px-2 py-1.5 font-medium">{row.category_l1}</td>
                          <td className="px-2 py-1.5 text-orange-700">{row.count}</td>
                          <td className="px-2 py-1.5 text-gray-500">{row.scanned}</td>
                          <td className="px-2 py-1.5">
                            <button
                              type="button"
                              className="text-indigo-600 hover:underline"
                              onClick={() => handleMismatchDrillDown(row.category_l1)}
                            >
                              Chi tiết
                            </button>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
          {mismatchScan ? (
            <div className="mt-3 text-sm text-gray-700">
              <span className="font-medium text-gray-800">{mismatchL1}</span>
              {' — '}
              đã quét <strong>{mismatchScan.scanned}</strong> SP, tìm thấy{' '}
              <strong>{mismatchScan.count}</strong> lệch.
            </div>
          ) : null}
          {mismatchScan?.items?.length ? (
            <div className="mt-3 max-h-72 overflow-auto rounded border border-gray-200">
              <table className="min-w-full text-left text-xs">
                <thead className="sticky top-0 bg-gray-50 text-gray-600">
                  <tr>
                    <th className="px-2 py-2">Mã SP</th>
                    <th className="px-2 py-2">Tên</th>
                    <th className="px-2 py-2">Danh mục hiện tại</th>
                    <th className="px-2 py-2">Gợi ý từ tên</th>
                    <th className="px-2 py-2">Lý do</th>
                  </tr>
                </thead>
                <tbody>
                  {mismatchScan.items.map((row) => (
                    <tr key={row.product_id} className="border-t border-gray-100">
                      <td className="px-2 py-1.5 font-mono">{row.product_id}</td>
                      <td className="max-w-[14rem] truncate px-2 py-1.5" title={row.name}>
                        {row.name}
                      </td>
                      <td className="px-2 py-1.5">
                        {[row.category, row.subcategory, row.sub_subcategory].filter(Boolean).join(' › ') || '—'}
                      </td>
                      <td className="px-2 py-1.5">{row.inferred_domain_label || '—'}</td>
                      <td className="max-w-[16rem] px-2 py-1.5 text-gray-600">{row.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {mismatchReclassifyError ? (
            <div className="mt-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {mismatchReclassifyError}
            </div>
          ) : null}
          {mismatchReclassifyResult ? (
            <div className="mt-3 rounded border border-green-200 bg-green-50 p-3 text-sm text-green-900">
              {mismatchReclassifyResult.dry_run ? 'Dry-run (một danh mục): ' : 'Một danh mục: '}
              Thành công {mismatchReclassifyResult.ok}, lỗi {mismatchReclassifyResult.failed}.
            </div>
          ) : null}
          {mismatchReclassifyAllResult ? (
            <div className="mt-3 space-y-2 rounded border border-green-200 bg-green-50 p-3 text-sm text-green-900">
              <p>
                {mismatchReclassifyAllResult.dry_run ? 'Dry-run (tất cả): ' : 'Tất cả danh mục: '}
                Thành công {mismatchReclassifyAllResult.ok}, lỗi {mismatchReclassifyAllResult.failed},{' '}
                đã xử lý {mismatchReclassifyAllResult.processed} SP /{' '}
                {mismatchReclassifyAllResult.categories_processed} danh mục.
              </p>
              {mismatchReclassifyAllResult.categories.some((r) => !r.skipped && r.processed > 0) ? (
                <div className="max-h-40 overflow-auto rounded border border-green-300/60 bg-white/60">
                  <table className="min-w-full text-left text-xs">
                    <thead className="sticky top-0 bg-green-50/90 text-green-900">
                      <tr>
                        <th className="px-2 py-1.5">Danh mục</th>
                        <th className="px-2 py-1.5">OK</th>
                        <th className="px-2 py-1.5">Lỗi</th>
                      </tr>
                    </thead>
                    <tbody>
                      {mismatchReclassifyAllResult.categories
                        .filter((r) => !r.skipped && r.processed > 0)
                        .map((r) => (
                          <tr key={r.category_l1} className="border-t border-green-100">
                            <td className="px-2 py-1">{r.category_l1}</td>
                            <td className="px-2 py-1">{r.ok}</td>
                            <td className="px-2 py-1">{r.failed}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
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
