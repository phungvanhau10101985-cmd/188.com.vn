'use client';

import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import AdminLayout from '@/components/admin/AdminLayout';
import {
  adminProductAPI,
  type AdminImportExcelJob,
  type AdminProduct,
  type AdminProductsResponse,
} from '@/lib/admin-api';

const PAGE_SIZE = 100;

const API_V1 = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8001/api/v1';

/** Nội dung panel + toast sau khi poll job import xong */
function formatImportExcelJobOutcome(job: AdminImportExcelJob): {
  panel: { variant: 'err' | 'warn' | 'ok'; title: string; body: string } | null;
  toast: { type: 'ok' | 'err'; msg: string };
} {
  if (job.status === 'error') {
    const parts: string[] = [];
    parts.push(job.detail?.trim() || job.message?.trim() || 'Import thất bại');
    if (job.total_rows != null) parts.push('', `Số dòng trong file (tham khảo): ${job.total_rows}`);
    if (job.errors?.length) {
      parts.push('', 'Chi tiết:');
      for (const line of job.errors.slice(0, 200)) parts.push(typeof line === 'string' ? line : String(line));
      if (job.errors.length > 200) parts.push(`… và ${job.errors.length - 200} dòng khác`);
    }
    if (job.warnings?.length) {
      parts.push('', 'Cảnh báo đi kèm:');
      for (const w of job.warnings.slice(0, 50)) parts.push(typeof w === 'string' ? w : String(w));
    }
    return {
      panel: { variant: 'err', title: 'Import thất bại', body: parts.join('\n') },
      toast: { type: 'err', msg: 'Import lỗi — xem chi tiết phía dưới ô Import.' },
    };
  }

  const d = job.result?.data;
  const rowErrs = job.result?.errors ?? [];
  const warns = job.result?.warnings ?? [];
  const headline = `Tạo mới ${d?.created ?? 0}, cập nhật ${d?.updated ?? 0} (${d?.success_rate ?? '—'} thành công, tổng xử lý ${d?.total_processed ?? 0}).`;

  if (!rowErrs.length && !warns.length) {
    return {
      panel: null,
      toast: { type: 'ok', msg: `Import xong: ${d?.created ?? 0} mới, ${d?.updated ?? 0} cập nhật` },
    };
  }

  const body: string[] = [headline];
  if (rowErrs.length) {
    body.push('', `Lỗi theo dòng (${rowErrs.length}):`);
    rowErrs.slice(0, 200).forEach((e) => body.push(typeof e === 'string' ? e : String(e)));
    if (rowErrs.length > 200) body.push(`… và ${rowErrs.length - 200} lỗi khác`);
  }
  if (warns.length) {
    body.push('', `Cảnh báo (${warns.length}):`);
    warns.slice(0, 80).forEach((w) => body.push(typeof w === 'string' ? w : String(w)));
    if (warns.length > 80) body.push(`… và ${warns.length - 80} cảnh báo khác`);
  }

  const variant = rowErrs.length ? 'warn' : 'ok';
  const toastMsg = rowErrs.length
    ? 'Import hoàn thành nhưng có lỗi ở một số dòng — xem chi tiết phía dưới ô Import.'
    : 'Import xong có cảnh báo — xem chi tiết phía dưới ô Import.';

  return {
    panel: {
      variant,
      title: rowErrs.length ? 'Import xong nhưng còn lỗi dòng' : 'Import xong (cảnh báo)',
      body: body.join('\n'),
    },
    toast: { type: 'ok', msg: toastMsg },
  };
}

/** Feed TSV công khai — Commerce Manager / Ads dùng “URL đến file” */
const FEED_MERCHANT_CENTER_TSV = `${API_V1}/import-export/export/merchant-center-feed.tsv`;
const FEED_META_CATALOG_TSV = `${API_V1}/import-export/export/meta-catalog-feed.tsv`;
const FEED_TIKTOK_CATALOG_TSV = `${API_V1}/import-export/export/tiktok-catalog-feed.tsv`;

export default function AdminProductsPage() {
  const [data, setData] = useState<AdminProductsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchName, setSearchName] = useState('');
  const [searchId, setSearchId] = useState('');
  const [page, setPage] = useState(1);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [importing, setImporting] = useState(false);
  const [importProgress, setImportProgress] = useState<{
    message: string;
    percent: number | null;
  } | null>(null);
  /** Chi tiết lỗi/cảnh báo sau import (giữ đến khi import lại hoặc đóng) */
  const [importDetailPanel, setImportDetailPanel] = useState<{
    variant: 'err' | 'warn' | 'ok';
    title: string;
    body: string;
  } | null>(null);
  const [exporting, setExporting] = useState(false);
  const [downloadingTemplate, setDownloadingTemplate] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [editing, setEditing] = useState<{ productId: string; field: string; value: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [selectedProductIds, setSelectedProductIds] = useState<Set<string>>(new Set());

  const showToast = (type: 'ok' | 'err', msg: string, persistMs?: number) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), persistMs ?? 3000);
  };

  const fetchProducts = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminProductAPI.getProducts({
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
        q: searchName.trim() || undefined,
        product_id: searchId.trim() || undefined,
      });
      setData(res);
    } catch {
      showToast('err', 'Lỗi tải danh sách sản phẩm');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [page, searchName, searchId]);

  useEffect(() => {
    fetchProducts();
  }, [fetchProducts]);

  useEffect(() => {
    setSelectedProductIds(new Set());
  }, [data?.products, page]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchProducts();
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setImportDetailPanel(null);
    setImportProgress({ message: 'Đang tải file lên...', percent: null });
    try {
      const { job_id } = await adminProductAPI.startImportExcelAsync(file);

      let job: AdminImportExcelJob;
      for (;;) {
        job = await adminProductAPI.getImportExcelJob(job_id);
        setImportProgress({
          message: job.message,
          percent: job.percent ?? null,
        });
        if (job.status === 'done' || job.status === 'error') break;
        await new Promise((r) => setTimeout(r, 500));
      }

      const { panel, toast: tmsg } = formatImportExcelJobOutcome(job);
      if (panel) setImportDetailPanel(panel);
      showToast(tmsg.type, tmsg.msg, tmsg.type === 'err' || panel?.variant === 'warn' ? 8000 : 4500);

      if (job.status !== 'error') fetchProducts();
    } catch (err: unknown) {
      const raw = (err as Error)?.message || 'Import thất bại';
      setImportDetailPanel({
        variant: 'err',
        title: 'Không thể bắt đầu hoặc theo dõi import',
        body: raw,
      });
      showToast('err', raw, 9000);
    } finally {
      setImporting(false);
      setImportProgress(null);
      e.target.value = '';
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      await adminProductAPI.exportExcel();
      showToast('ok', 'Đã tải file Excel xuống');
    } catch {
      showToast('err', 'Export thất bại');
    } finally {
      setExporting(false);
    }
  };

  const handleDownloadTemplate = async () => {
    setDownloadingTemplate(true);
    try {
      await adminProductAPI.downloadSampleTemplate();
      showToast('ok', 'Đã tải file mẫu xuống');
    } catch {
      showToast('err', 'Tải file mẫu thất bại');
    } finally {
      setDownloadingTemplate(false);
    }
  };

  const startEdit = (productId: string, field: string, value: string | number) => {
    setEditing({ productId, field, value: String(value ?? '') });
  };

  const cancelEdit = () => {
    setEditing(null);
  };

  const saveEdit = async () => {
    if (!editing || !data?.products) return;
    const product = data.products.find((p) => p.product_id === editing.productId);
    if (!product) return;
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {};
      if (editing.field === 'name') payload.name = editing.value;
      if (editing.field === 'price') payload.price = parseFloat(editing.value) || 0;
      if (editing.field === 'product_id') payload.product_id = editing.value;
      if (editing.field === 'brand_name') payload.brand_name = editing.value;
      if (editing.field === 'category') payload.category = editing.value;
      if (editing.field === 'code') payload.code = editing.value;
      await adminProductAPI.updateProduct(editing.productId, payload as Partial<AdminProduct>);
      showToast('ok', 'Đã lưu');
      setEditing(null);
      fetchProducts();
    } catch {
      showToast('err', 'Lưu thất bại');
    } finally {
      setSaving(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent, productId: string, field: string) => {
    if (e.key === 'Enter') saveEdit();
    if (e.key === 'Escape') cancelEdit();
  };

  const totalPages = data?.total_pages ?? 1;
  const currentPageIds = useMemo(() => (data?.products || []).map((p) => p.product_id), [data?.products]);
  const allSelectedOnPage = currentPageIds.length > 0 && currentPageIds.every((id) => selectedProductIds.has(id));

  const toggleSelectAllOnPage = () => {
    setSelectedProductIds((prev) => {
      const next = new Set(prev);
      if (allSelectedOnPage) {
        currentPageIds.forEach((id) => next.delete(id));
      } else {
        currentPageIds.forEach((id) => next.add(id));
      }
      return next;
    });
  };

  const toggleSelectOne = (productId: string) => {
    setSelectedProductIds((prev) => {
      const next = new Set(prev);
      if (next.has(productId)) next.delete(productId);
      else next.add(productId);
      return next;
    });
  };

  const handleDeleteSelected = async () => {
    if (selectedProductIds.size === 0) return;
    if (!confirm(`Xóa ${selectedProductIds.size} sản phẩm đang chọn?`)) return;
    setDeleting(true);
    try {
      await Promise.all(Array.from(selectedProductIds).map((id) => adminProductAPI.deleteProduct(id)));
      showToast('ok', `Đã xóa ${selectedProductIds.size} sản phẩm`);
      await fetchProducts();
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Xóa thất bại');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <AdminLayout>
      <div className="p-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Quản lý sản phẩm</h1>

        {/* Toolbar: search, import, export */}
        <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6">
          <form onSubmit={handleSearch} className="flex flex-wrap items-end gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Tên sản phẩm</label>
              <input
                type="text"
                value={searchName}
                onChange={(e) => setSearchName(e.target.value)}
                placeholder="Tìm theo tên..."
                className="w-56 rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">ID sản phẩm</label>
              <input
                type="text"
                value={searchId}
                onChange={(e) => setSearchId(e.target.value)}
                placeholder="Tìm theo ID..."
                className="w-48 rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <button type="submit" className="px-4 py-2 bg-slate-700 text-white rounded-lg hover:bg-slate-800 text-sm font-medium">
              Tìm kiếm
            </button>
            <button
              type="button"
              onClick={toggleSelectAllOnPage}
              disabled={!data?.products?.length}
              className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 text-sm font-medium disabled:opacity-70"
            >
              {allSelectedOnPage ? 'Bỏ chọn trang' : 'Chọn tất trang'}
            </button>
            <button
              type="button"
              onClick={handleDeleteSelected}
              disabled={selectedProductIds.size === 0 || deleting}
              className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm font-medium disabled:opacity-70"
            >
              {deleting ? 'Đang xóa...' : `Xóa (${selectedProductIds.size})`}
            </button>
            <div className="flex-1" />
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls"
              className="hidden"
              onChange={handleImport}
            />
            <button
              type="button"
              onClick={handleDownloadTemplate}
              disabled={downloadingTemplate}
              className="px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 text-sm font-medium disabled:opacity-70"
            >
              {downloadingTemplate ? 'Đang tải...' : 'Tải file mẫu'}
            </button>
            <div className="flex flex-col items-end gap-1 min-w-[10rem]">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={importing}
                className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 text-sm font-medium disabled:opacity-70 w-full sm:w-auto"
              >
                {importing ? 'Đang import...' : 'Import Excel'}
              </button>
              {importing && importProgress ? (
                <div className="w-full max-w-[20rem] space-y-1">
                  <div className="h-2 rounded-full bg-gray-200 overflow-hidden">
                    {importProgress.percent != null ? (
                      <div
                        className="h-full rounded-full bg-emerald-600 transition-[width] duration-300 ease-out"
                        style={{ width: `${Math.min(100, importProgress.percent)}%` }}
                      />
                    ) : (
                      <div className="h-full w-full bg-emerald-500/70 animate-pulse rounded-full" />
                    )}
                  </div>
                  <p className="text-xs text-gray-600 leading-snug text-right line-clamp-2">
                    {importProgress.message}
                  </p>
                </div>
              ) : null}
            </div>
            <button
              type="button"
              onClick={handleExport}
              disabled={exporting}
              className="px-4 py-2 bg-[#ea580c] text-white rounded-lg hover:bg-[#c2410c] text-sm font-medium disabled:opacity-70"
            >
              {exporting ? 'Đang export...' : 'Export Excel'}
            </button>
          </form>
          {importDetailPanel ? (
            <div
              className={`mt-3 rounded-lg border p-3 text-sm ${
                importDetailPanel.variant === 'err'
                  ? 'border-red-300 bg-red-50 text-gray-900'
                  : importDetailPanel.variant === 'warn'
                    ? 'border-amber-300 bg-amber-50 text-gray-900'
                    : 'border-sky-200 bg-sky-50 text-gray-900'
              }`}
            >
              <div className="flex justify-between gap-2 items-start mb-2">
                <span className="font-semibold">{importDetailPanel.title}</span>
                <button
                  type="button"
                  onClick={() => setImportDetailPanel(null)}
                  className="text-xs shrink-0 px-2 py-1 rounded border border-gray-400/60 hover:bg-white/80 text-gray-700"
                >
                  Đóng
                </button>
              </div>
              <pre className="whitespace-pre-wrap break-words max-h-[22rem] overflow-y-auto font-mono text-xs leading-relaxed text-gray-800">
                {importDetailPanel.body}
              </pre>
            </div>
          ) : null}
          <div className="mt-4 pt-4 border-t border-gray-100 space-y-2 text-sm text-gray-700">
            <p>
              <span className="font-medium text-gray-800">Google Merchant Center</span>{' '}
              <a
                href={FEED_MERCHANT_CENTER_TSV}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-700 hover:underline break-all"
              >
                {FEED_MERCHANT_CENTER_TSV}
              </a>
              <span className="text-gray-500"> — Nguồn dữ liệu · URL máy chủ · TSV (tab).</span>
            </p>
            <p>
              <span className="font-medium text-gray-800">Meta (Facebook / Instagram) catalogue</span>{' '}
              <a
                href={FEED_META_CATALOG_TSV}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-700 hover:underline break-all"
              >
                {FEED_META_CATALOG_TSV}
              </a>
              <span className="text-gray-500"> — Commerce Manager · Scheduled data feed · cột theo catalogue Meta (`fb_product_category` chỉnh `.env`).</span>
            </p>
            <p>
              <span className="font-medium text-gray-800">TikTok catalogue</span>{' '}
              <a
                href={FEED_TIKTOK_CATALOG_TSV}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-700 hover:underline break-all"
              >
                {FEED_TIKTOK_CATALOG_TSV}
              </a>
              <span className="text-gray-500"> — Ads Manager · Data feed schedule · ID mục là `sku_id` (= product_id).</span>
            </p>
          </div>
        </div>

        {/* Table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {loading ? (
            <div className="p-12 text-center text-gray-500">Đang tải...</div>
          ) : !data?.products?.length ? (
            <div className="p-12 text-center text-gray-500">Không có sản phẩm nào.</div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      <th className="text-left py-3 px-4 font-semibold text-gray-700 w-10">
                        <input
                          type="checkbox"
                          checked={allSelectedOnPage}
                          onChange={toggleSelectAllOnPage}
                          aria-label="Chọn tất cả sản phẩm trong trang"
                        />
                      </th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700 w-28">ID</th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Tên</th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700 w-24">Giá</th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700 w-32">Thương hiệu</th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700 w-28">Danh mục</th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700 w-20">Trạng thái</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.products.map((p) => (
                      <tr key={p.id} className="border-b border-gray-100 hover:bg-gray-50/50">
                        <td className="py-2 px-4">
                          <input
                            type="checkbox"
                            checked={selectedProductIds.has(p.product_id)}
                            onChange={() => toggleSelectOne(p.product_id)}
                            aria-label={`Chọn sản phẩm ${p.product_id}`}
                          />
                        </td>
                        <td className="py-2 px-4">
                          {editing?.productId === p.product_id && editing?.field === 'product_id' ? (
                            <input
                              autoFocus
                              value={editing.value}
                              onChange={(e) => setEditing((x) => x ? { ...x, value: e.target.value } : null)}
                              onBlur={saveEdit}
                              onKeyDown={(e) => handleKeyDown(e, p.product_id, 'product_id')}
                              className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                            />
                          ) : (
                            <span
                              className="cursor-pointer text-blue-600 hover:underline"
                              onClick={() => startEdit(p.product_id, 'product_id', p.product_id ?? '')}
                              title="Bấm để sửa"
                            >
                              {(p as AdminProduct).product_id || p.id}
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-4">
                          {editing?.productId === p.product_id && editing?.field === 'name' ? (
                            <input
                              autoFocus
                              value={editing.value}
                              onChange={(e) => setEditing((x) => x ? { ...x, value: e.target.value } : null)}
                              onBlur={saveEdit}
                              onKeyDown={(e) => handleKeyDown(e, p.product_id, 'name')}
                              className="w-full rounded border border-gray-300 px-2 py-1"
                            />
                          ) : (
                            <span
                              className="cursor-pointer hover:bg-gray-100 rounded px-1 -mx-1 line-clamp-2"
                              onClick={() => startEdit(p.product_id, 'name', p.name ?? '')}
                              title="Bấm để sửa"
                            >
                              {p.name || '—'}
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-4">
                          {editing?.productId === p.product_id && editing?.field === 'price' ? (
                            <input
                              type="number"
                              autoFocus
                              value={editing.value}
                              onChange={(e) => setEditing((x) => x ? { ...x, value: e.target.value } : null)}
                              onBlur={saveEdit}
                              onKeyDown={(e) => handleKeyDown(e, p.product_id, 'price')}
                              className="w-full rounded border border-gray-300 px-2 py-1"
                            />
                          ) : (
                            <span
                              className="cursor-pointer hover:bg-gray-100 rounded px-1 -mx-1"
                              onClick={() => startEdit(p.product_id, 'price', p.price ?? 0)}
                              title="Bấm để sửa"
                            >
                              {typeof p.price === 'number' ? new Intl.NumberFormat('vi-VN').format(p.price) : p.price}
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-4">
                          {editing?.productId === p.product_id && editing?.field === 'brand_name' ? (
                            <input
                              autoFocus
                              value={editing.value}
                              onChange={(e) => setEditing((x) => x ? { ...x, value: e.target.value } : null)}
                              onBlur={saveEdit}
                              onKeyDown={(e) => handleKeyDown(e, p.product_id, 'brand_name')}
                              className="w-full rounded border border-gray-300 px-2 py-1"
                            />
                          ) : (
                            <span
                              className="cursor-pointer hover:bg-gray-100 rounded px-1 -mx-1"
                              onClick={() => startEdit(p.product_id, 'brand_name', p.brand_name ?? '')}
                              title="Bấm để sửa"
                            >
                              {p.brand_name || '—'}
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-4">
                          {editing?.productId === p.product_id && editing?.field === 'category' ? (
                            <input
                              autoFocus
                              value={editing.value}
                              onChange={(e) => setEditing((x) => x ? { ...x, value: e.target.value } : null)}
                              onBlur={saveEdit}
                              onKeyDown={(e) => handleKeyDown(e, p.product_id, 'category')}
                              className="w-full rounded border border-gray-300 px-2 py-1"
                            />
                          ) : (
                            <span
                              className="cursor-pointer hover:bg-gray-100 rounded px-1 -mx-1"
                              onClick={() => startEdit(p.product_id, 'category', p.category ?? '')}
                              title="Bấm để sửa"
                            >
                              {p.category || '—'}
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-4">
                          <span className={p.is_active !== false ? 'text-green-600' : 'text-gray-400'}>
                            {p.is_active !== false ? 'Hiển thị' : 'Ẩn'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination: 100 sản phẩm 1 trang */}
              <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 bg-gray-50">
                <span className="text-sm text-gray-600">
                  Trang {page} / {totalPages} — Tổng {data.total} sản phẩm (100/trang)
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1}
                    className="px-3 py-1.5 rounded border border-gray-300 text-sm font-medium disabled:opacity-50 hover:bg-gray-100"
                  >
                    Trước
                  </button>
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                    className="px-3 py-1.5 rounded border border-gray-300 text-sm font-medium disabled:opacity-50 hover:bg-gray-100"
                  >
                    Sau
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {toast && (
          <div
            className={`fixed bottom-4 right-4 px-4 py-2 rounded-lg shadow-lg text-white text-sm ${
              toast.type === 'ok' ? 'bg-green-600' : 'bg-red-600'
            }`}
          >
            {toast.msg}
          </div>
        )}
      </div>
    </AdminLayout>
  );
}
