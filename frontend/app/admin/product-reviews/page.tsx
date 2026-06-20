'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { adminProductReviewsAPI, type ProductReviewAdmin, type ProductReviewsListResponse } from '@/lib/admin-api';
import { useDebouncedRowSave } from '@/lib/use-debounced-row-save';
import { pruneRowEditAfterSave } from '@/lib/admin-row-edit-utils';
import ViewReviewModal from './components/ViewReviewModal';

const PAGE_SIZE = 10;

const REVIEW_EDIT_KEYS = [
  'user_name', 'star', 'title', 'content', 'group', 'useful', 'reply_name', 'reply_content', 'is_active',
] as const satisfies readonly (keyof ProductReviewAdmin)[];

function formatDate(s: string | null | undefined) {
  if (!s) return '—';
  try {
    const d = new Date(s);
    return d.toLocaleString('vi-VN');
  } catch {
    return s;
  }
}

export default function AdminProductReviewsPage() {
  const [data, setData] = useState<ProductReviewsListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchGroup, setSearchGroup] = useState('');
  const [page, setPage] = useState(1);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [importing, setImporting] = useState(false);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [savedFlashId, setSavedFlashId] = useState<number | null>(null);
  const [rowEdit, setRowEdit] = useState<Record<number, Partial<ProductReviewAdmin>>>({});
  const [viewModal, setViewModal] = useState<ProductReviewAdmin | null>(null);
  const [deletingAll, setDeletingAll] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const rowEditRef = useRef<Record<number, Partial<ProductReviewAdmin>>>({});
  const dataRef = useRef<ProductReviewsListResponse | null>(null);
  const composingRef = useRef<Record<number, boolean>>({});
  const savingIdsRef = useRef<Set<number>>(new Set());
  const pendingResaveRef = useRef<Set<number>>(new Set());
  const { scheduleSave, flushSave } = useDebouncedRowSave();

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 3000);
  };

  const fetchList = useCallback(async (pageOverride?: number, options?: { silent?: boolean }) => {
    const p = typeof pageOverride === 'number' ? pageOverride : page;
    if (!options?.silent) setLoading(true);
    try {
      const res = await adminProductReviewsAPI.getList({
        skip: (p - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
        search_group: searchGroup.trim() || undefined,
      });
      setData(res);
    } catch {
      showToast('err', 'Lỗi tải danh sách');
      if (!options?.silent) setData(null);
    } finally {
      if (!options?.silent) setLoading(false);
    }
  }, [page, searchGroup]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchList(1);
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const result = await adminProductReviewsAPI.importExcel(file);
      const created = (result as { created?: number })?.created ?? 0;
      showToast('ok', `Import xong: ${created} đánh giá`);
      await fetchList();
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Import thất bại');
    } finally {
      setImporting(false);
      e.target.value = '';
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Bạn có chắc muốn xóa đánh giá này?')) return;
    try {
      await adminProductReviewsAPI.delete(id);
      setRowEdit((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      showToast('ok', 'Đã xóa');
      await fetchList(undefined, { silent: true });
    } catch {
      showToast('err', 'Xóa thất bại');
    }
  };

  const handleDeleteAll = async () => {
    const total = data?.total ?? 0;
    if (total <= 0) return;
    if (
      !confirm(
        `Bạn có chắc muốn xóa HẾT ${total} đánh giá? Thao tác này không thể hoàn tác.`
      )
    ) {
      return;
    }
    setDeletingAll(true);
    try {
      const res = await adminProductReviewsAPI.deleteAll();
      showToast('ok', `Đã xóa ${res.deleted} đánh giá`);
      setPage(1);
      await fetchList(1);
    } catch {
      showToast('err', 'Xóa hết thất bại');
    } finally {
      setDeletingAll(false);
    }
  };

  const getRowVal = (r: ProductReviewAdmin, key: keyof ProductReviewAdmin) => {
    const e = rowEditRef.current[r.id] ?? rowEdit[r.id];
    if (e && key in e) return (e as Record<string, unknown>)[key];
    return (r as unknown as Record<string, unknown>)[key];
  };

  useEffect(() => {
    dataRef.current = data;
  }, [data]);

  const buildReviewPayload = useCallback((r: ProductReviewAdmin, e?: Partial<ProductReviewAdmin>) => {
    const edit = e ?? rowEditRef.current[r.id] ?? rowEdit[r.id];
    return {
      user_name: (edit?.user_name !== undefined ? edit.user_name : r.user_name) ?? '',
      star: Math.max(1, Math.min(5, (edit?.star ?? r.star ?? 5) as number)),
      title: (edit?.title !== undefined ? edit.title : r.title) ?? '',
      content: (edit?.content !== undefined ? edit.content : r.content) ?? '',
      group: Math.max(0, (edit?.group ?? r.group ?? 0) as number),
      useful: Math.max(0, (edit?.useful ?? r.useful ?? 0) as number),
      reply_name: (edit?.reply_name !== undefined ? edit.reply_name : r.reply_name) ?? '',
      reply_content: (edit?.reply_content !== undefined ? edit.reply_content : r.reply_content) ?? '',
      is_active: edit?.is_active !== undefined ? edit.is_active! : r.is_active,
    };
  }, [rowEdit]);

  const reviewRowDirty = useCallback((r: ProductReviewAdmin, payload: ReturnType<typeof buildReviewPayload>) => {
    return (
      payload.user_name !== (r.user_name ?? '') ||
      payload.star !== (r.star ?? 5) ||
      payload.title !== (r.title ?? '') ||
      payload.content !== (r.content ?? '') ||
      payload.group !== (r.group ?? 0) ||
      payload.useful !== (r.useful ?? 0) ||
      payload.reply_name !== (r.reply_name ?? '') ||
      payload.reply_content !== (r.reply_content ?? '') ||
      payload.is_active !== r.is_active
    );
  }, []);

  const handleSaveRow = useCallback(async (r: ProductReviewAdmin, opts?: { silent?: boolean }) => {
    if (savingIdsRef.current.has(r.id)) {
      pendingResaveRef.current.add(r.id);
      return;
    }
    const edit = rowEditRef.current[r.id];
    const payload = buildReviewPayload(r, edit);
    if (!reviewRowDirty(r, payload)) return;

    savingIdsRef.current.add(r.id);
    setSavingId(r.id);
    try {
      const updated = await adminProductReviewsAPI.update(r.id, payload);
      setData((prev) => {
        if (!prev) return prev;
        const next = {
          ...prev,
          items: prev.items.map((item) => (item.id === r.id ? { ...item, ...updated } : item)),
        };
        dataRef.current = next;
        return next;
      });
      setRowEdit((prev) => {
        const pruned = pruneRowEditAfterSave(edit, updated as ProductReviewAdmin, REVIEW_EDIT_KEYS);
        const next = { ...prev };
        if (Object.keys(pruned).length === 0) {
          delete next[r.id];
        } else {
          next[r.id] = pruned;
        }
        rowEditRef.current = next;
        return next;
      });
      setSavedFlashId(r.id);
      setTimeout(() => setSavedFlashId((cur) => (cur === r.id ? null : cur)), 1500);
      if (!opts?.silent) showToast('ok', 'Đã lưu');
    } catch {
      showToast('err', 'Lưu thất bại');
    } finally {
      savingIdsRef.current.delete(r.id);
      setSavingId((cur) => (cur === r.id ? null : cur));
      if (pendingResaveRef.current.has(r.id)) {
        pendingResaveRef.current.delete(r.id);
        const latest = dataRef.current?.items.find((item) => item.id === r.id);
        if (latest) void handleSaveRow(latest, { silent: true });
      }
    }
  }, [buildReviewPayload, reviewRowDirty]);

  const triggerAutoSave = useCallback((r: ProductReviewAdmin) => {
    if (composingRef.current[r.id]) return;
    scheduleSave(r.id, () => {
      const latest = dataRef.current?.items.find((item) => item.id === r.id) ?? r;
      void handleSaveRow(latest, { silent: true });
    });
  }, [handleSaveRow, scheduleSave]);

  const setRowVal = useCallback((r: ProductReviewAdmin, key: keyof ProductReviewAdmin, value: unknown) => {
    const nextEdit = { ...rowEditRef.current[r.id], [key]: value };
    const next = { ...rowEditRef.current, [r.id]: nextEdit };
    rowEditRef.current = next;
    setRowEdit(next);
    triggerAutoSave(r);
  }, [triggerAutoSave]);

  const flushRowSave = useCallback((r: ProductReviewAdmin) => {
    flushSave(r.id, () => {
      const latest = dataRef.current?.items.find((item) => item.id === r.id) ?? r;
      void handleSaveRow(latest, { silent: true });
    });
  }, [flushSave, handleSaveRow]);

  const onComposeStart = useCallback((id: number) => {
    composingRef.current[id] = true;
  }, []);

  const onComposeEnd = useCallback((r: ProductReviewAdmin) => {
    composingRef.current[r.id] = false;
    triggerAutoSave(r);
  }, [triggerAutoSave]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
      <>
      <div className="p-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Quản lý đánh giá sản phẩm</h1>

        {toast && (
          <div
            className={`fixed top-4 right-4 z-50 px-4 py-2 rounded-lg ${
              toast.type === 'ok' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
            }`}
          >
            {toast.msg}
          </div>
        )}

        <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
          <a href="/" className="text-blue-600 hover:underline">Trang chủ</a>
          <span className="text-gray-400">|</span>
          <a href="/" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
            Xem website
          </a>
          <span className="text-gray-400">|</span>
          <button
            type="button"
            onClick={() => adminProductReviewsAPI.downloadSampleExcel().catch((e) => showToast('err', (e as Error)?.message || 'Lỗi tải file'))}
            className="text-blue-600 hover:underline"
          >
            Tải file Excel mẫu
          </button>
          <span className="text-gray-400">|</span>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={importing}
            className="text-blue-600 hover:underline disabled:opacity-70"
          >
            {importing ? 'Đang import...' : 'Import'}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls"
            className="hidden"
            onChange={handleImport}
          />
        </div>

        <div className="mb-4 p-3 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-700">
          Sửa trực tiếp trong bảng — hệ thống <strong>tự lưu</strong> sau ~0,7 giây. Email thông báo gửi <strong>sau 2 phút</strong> kể từ lần sửa cuối (một email duy nhất với nội dung cuối cùng).
        </div>

        <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
          <strong>Logic hiển thị:</strong> Đánh giá từ khách hàng (product_id có) → hiển thị trên sản phẩm đã mua.
          Đánh giá import (product_id trống) → hiển thị trên sản phẩm có nhóm đánh giá (group_rating) trùng với cột Nhóm.
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-4 mb-4">
          <form onSubmit={handleSearch} className="flex flex-wrap items-end gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Tìm kiếm theo mã nhóm đánh giá
              </label>
              <input
                type="text"
                inputMode="numeric"
                value={searchGroup}
                onChange={(e) => setSearchGroup(e.target.value)}
                placeholder="Ví dụ: 24, 94..."
                className="w-48 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#ea580c]/30 focus:border-[#ea580c]"
                aria-label="Mã nhóm đánh giá"
              />
            </div>
            <button
              type="submit"
              className="px-4 py-2 bg-slate-700 text-white rounded-lg hover:bg-slate-800 text-sm font-medium"
            >
              Tìm kiếm
            </button>
            {searchGroup.trim() && (
              <button
                type="button"
                onClick={() => {
                  setSearchGroup('');
                  setPage(1);
                }}
                className="px-4 py-2 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-50"
              >
                Xóa lọc
              </button>
            )}
          </form>
        </div>

        <div className="mb-2 flex items-center justify-between flex-wrap gap-2">
          <span className="text-sm text-gray-600">Tổng số bản ghi: {data?.total ?? 0}</span>
          <button
            type="button"
            onClick={handleDeleteAll}
            disabled={deletingAll || !data || data.total <= 0}
            className="text-sm px-3 py-1.5 rounded-lg border border-red-300 text-red-700 bg-red-50 hover:bg-red-100 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {deletingAll ? 'Đang xóa...' : 'Xóa hết đánh giá'}
          </button>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {loading ? (
            <div className="p-12 text-center text-gray-500">Đang tải...</div>
          ) : !data?.items?.length ? (
            <div className="p-12 text-center text-gray-500">
              Chưa có đánh giá nào. Dùng Import để tải file Excel.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="text-left py-2 px-2 font-semibold text-gray-700 w-10">STT</th>
                    <th className="text-left py-2 px-2 font-semibold text-gray-700 w-20">Loại</th>
                    <th className="text-left py-2 px-2 font-semibold text-gray-700 w-24">Hiển thị tại</th>
                    <th className="text-left py-2 px-2 font-semibold text-gray-700">Tên người</th>
                    <th className="text-left py-2 px-2 font-semibold text-gray-700 w-14">Sao</th>
                    <th className="text-left py-2 px-2 font-semibold text-gray-700">Tiêu đề</th>
                    <th className="text-left py-2 px-2 font-semibold text-gray-700 min-w-[120px]">Nội dung</th>
                    <th className="text-left py-2 px-2 font-semibold text-gray-700 w-14" title="Khớp product.group_rating cho đánh giá import">Nhóm</th>
                    <th className="text-left py-2 px-2 font-semibold text-gray-700 w-16">Hữu ích</th>
                    <th className="text-left py-2 px-2 font-semibold text-gray-700">Trả lời</th>
                    <th className="text-left py-2 px-2 font-semibold text-gray-700 w-20">Kích hoạt</th>
                    <th className="text-left py-2 px-2 font-semibold text-gray-700 whitespace-nowrap">Thời gian</th>
                    <th className="text-left py-2 px-2 font-semibold text-gray-700 w-24">Chức năng</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((r, idx) => (
                    <tr key={r.id} className="border-b border-gray-100 hover:bg-gray-50/50">
                      <td className="py-2 px-2">{(page - 1) * PAGE_SIZE + idx + 1}</td>
                      <td className="py-2 px-2">
                        <span className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${r.is_imported ? 'bg-slate-200 text-slate-700' : 'bg-green-100 text-green-800'}`}>
                          {r.is_imported ? 'Import' : 'Khách hàng'}
                        </span>
                      </td>
                      <td className="py-2 px-2 text-xs">
                        {r.is_imported ? (
                          <span title="Đánh giá import: hiển thị trên SP có group_rating trùng Nhóm">Nhóm {r.group ?? 0}</span>
                        ) : r.product_id ? (
                          r.product_slug ? (
                            <a href={`/products/${r.product_slug}#review-${r.id}`} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
                              SP #{r.product_id}
                            </a>
                          ) : (
                            <span>SP #{r.product_id}</span>
                          )
                        ) : (
                          <span className="text-gray-400">—</span>
                        )}
                      </td>
                      <td className="py-2 px-2">
                        <input
                          type="text"
                          value={String(getRowVal(r, 'user_name') ?? '')}
                          onChange={(e) => setRowVal(r, 'user_name', e.target.value)}
                          onCompositionStart={() => onComposeStart(r.id)}
                          onCompositionEnd={() => onComposeEnd(r)}
                          onBlur={() => flushRowSave(r)}
                          className="rounded border border-gray-300 px-2 py-1 text-xs w-full min-w-0"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <input
                          type="number"
                          min={1}
                          max={5}
                          value={Number(getRowVal(r, 'star') ?? 5)}
                          onChange={(e) => setRowVal(r, 'star', Math.min(5, Math.max(1, parseInt(e.target.value, 10) || 5)))}
                          onBlur={() => flushRowSave(r)}
                          className="rounded border border-gray-300 px-1 py-0.5 text-xs w-12"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <input
                          type="text"
                          value={String(getRowVal(r, 'title') ?? '')}
                          onChange={(e) => setRowVal(r, 'title', e.target.value)}
                          onCompositionStart={() => onComposeStart(r.id)}
                          onCompositionEnd={() => onComposeEnd(r)}
                          onBlur={() => flushRowSave(r)}
                          className="rounded border border-gray-300 px-2 py-1 text-xs w-full min-w-0"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <input
                          type="text"
                          value={String(getRowVal(r, 'content') ?? '')}
                          onChange={(e) => setRowVal(r, 'content', e.target.value)}
                          onCompositionStart={() => onComposeStart(r.id)}
                          onCompositionEnd={() => onComposeEnd(r)}
                          onBlur={() => flushRowSave(r)}
                          className="rounded border border-gray-300 px-2 py-1 text-xs w-full min-w-0"
                          placeholder="Nội dung"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <input
                          type="number"
                          min={0}
                          value={Math.max(0, Number(getRowVal(r, 'group') ?? 0) || 0)}
                          onChange={(e) => setRowVal(r, 'group', Math.max(0, parseInt(e.target.value, 10) || 0))}
                          onBlur={() => flushRowSave(r)}
                          className="rounded border border-gray-300 px-1 py-0.5 text-xs w-14"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <input
                          type="number"
                          min={0}
                          value={Math.max(0, Number(getRowVal(r, 'useful') ?? 0) || 0)}
                          onChange={(e) => setRowVal(r, 'useful', Math.max(0, parseInt(e.target.value, 10) || 0))}
                          onBlur={() => flushRowSave(r)}
                          className="rounded border border-gray-300 px-1 py-0.5 text-xs w-16"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <div className="space-y-1">
                          <input
                            type="text"
                            value={String(getRowVal(r, 'reply_name') ?? '')}
                            onChange={(e) => setRowVal(r, 'reply_name', e.target.value)}
                            onCompositionStart={() => onComposeStart(r.id)}
                            onCompositionEnd={() => onComposeEnd(r)}
                            onBlur={() => flushRowSave(r)}
                            className="rounded border border-gray-300 px-2 py-0.5 text-xs w-full"
                            placeholder="Tên"
                          />
                          <input
                            type="text"
                            value={String(getRowVal(r, 'reply_content') ?? '')}
                            onChange={(e) => setRowVal(r, 'reply_content', e.target.value)}
                            onCompositionStart={() => onComposeStart(r.id)}
                            onCompositionEnd={() => onComposeEnd(r)}
                            onBlur={() => flushRowSave(r)}
                            className="rounded border border-gray-300 px-2 py-0.5 text-xs w-full"
                            placeholder="Nội dung"
                          />
                        </div>
                      </td>
                      <td className="py-2 px-2">
                        <select
                          value={getRowVal(r, 'is_active') ? '1' : '0'}
                          onChange={(e) => setRowVal(r, 'is_active', e.target.value === '1')}
                          onBlur={() => flushRowSave(r)}
                          className="rounded border border-gray-300 px-1 py-0.5 text-xs"
                        >
                          <option value="1">Hiển thị</option>
                          <option value="0">Ẩn</option>
                        </select>
                      </td>
                      <td className="py-2 px-2 text-gray-600 whitespace-nowrap text-xs">
                        {formatDate(r.created_at)}
                      </td>
                      <td className="py-2 px-2 whitespace-nowrap">
                        {r.product_slug && (
                          <button
                            type="button"
                            onClick={() => setViewModal(r)}
                            className="text-blue-600 hover:underline text-xs mr-1"
                          >
                            Xem đánh giá
                          </button>
                        )}
                        <span className="text-xs text-gray-500 mr-1" aria-live="polite">
                          {savingId === r.id ? 'Đang lưu...' : savedFlashId === r.id ? 'Đã lưu' : rowEdit[r.id] ? 'Chờ lưu...' : ''}
                        </span>
                        <button
                          type="button"
                          onClick={() => handleDelete(r.id)}
                          className="text-red-600 hover:underline text-xs"
                        >
                          Xóa
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {data && data.total > PAGE_SIZE && (
            <div className="p-3 border-t border-gray-100 flex items-center justify-between">
              <span className="text-sm text-gray-600">Tổng số bản ghi: {data.total}</span>
              <div className="flex gap-1">
                <button
                  type="button"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="px-3 py-1 rounded border border-gray-300 text-sm disabled:opacity-50"
                >
                  «
                </button>
                <span className="px-3 py-1 text-sm">
                  {page} / {totalPages}
                </span>
                <button
                  type="button"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="px-3 py-1 rounded border border-gray-300 text-sm disabled:opacity-50"
                >
                  »
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {viewModal && viewModal.product_slug && (
        <ViewReviewModal
          productSlug={viewModal.product_slug}
          selectedReview={viewModal}
          onClose={() => setViewModal(null)}
        />
      )}
      </>
  );
}
