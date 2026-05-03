'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { adminProductReviewsAPI, type ProductReviewAdmin, type ProductReviewsListResponse } from '@/lib/admin-api';
import ViewReviewModal from './components/ViewReviewModal';

const PAGE_SIZE = 10;

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
  const [page, setPage] = useState(1);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [importing, setImporting] = useState(false);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [rowEdit, setRowEdit] = useState<Record<number, Partial<ProductReviewAdmin>>>({});
  const [viewModal, setViewModal] = useState<ProductReviewAdmin | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 3000);
  };

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminProductReviewsAPI.getList({
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      });
      setData(res);
    } catch {
      showToast('err', 'Lỗi tải danh sách');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const result = await adminProductReviewsAPI.importExcel(file);
      const created = (result as { created?: number })?.created ?? 0;
      showToast('ok', `Import xong: ${created} đánh giá`);
      fetchList();
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
      showToast('ok', 'Đã xóa');
      fetchList();
    } catch {
      showToast('err', 'Xóa thất bại');
    }
  };

  const getRowVal = (r: ProductReviewAdmin, key: keyof ProductReviewAdmin) => {
    if (rowEdit[r.id] && key in rowEdit[r.id]) return (rowEdit[r.id] as Record<string, unknown>)[key];
    return (r as unknown as Record<string, unknown>)[key];
  };

  const setRowVal = (id: number, key: keyof ProductReviewAdmin, value: unknown) => {
    setRowEdit((prev) => ({ ...prev, [id]: { ...prev[id], [key]: value } }));
  };

  const handleSaveRow = async (r: ProductReviewAdmin) => {
    const e = rowEdit[r.id];
    const payload: Partial<ProductReviewAdmin> = {
      user_name: (e?.user_name !== undefined ? e.user_name : r.user_name) ?? '',
      star: Math.max(1, Math.min(5, (e?.star ?? r.star ?? 5) as number)),
      title: (e?.title !== undefined ? e.title : r.title) ?? '',
      content: (e?.content !== undefined ? e.content : r.content) ?? '',
      group: Math.max(0, (e?.group ?? r.group ?? 0) as number),
      useful: Math.max(0, (e?.useful ?? r.useful ?? 0) as number),
      reply_name: (e?.reply_name !== undefined ? e.reply_name : r.reply_name) ?? '',
      reply_content: (e?.reply_content !== undefined ? e.reply_content : r.reply_content) ?? '',
      is_active: e?.is_active !== undefined ? e.is_active! : r.is_active,
    };
    setSavingId(r.id);
    try {
      await adminProductReviewsAPI.update(r.id, payload);
      setRowEdit((prev) => {
        const next = { ...prev };
        delete next[r.id];
        return next;
      });
      showToast('ok', 'Đã lưu');
      fetchList();
    } catch {
      showToast('err', 'Lưu thất bại');
    } finally {
      setSavingId(null);
    }
  };

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

        <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
          <strong>Logic hiển thị:</strong> Đánh giá từ khách hàng (product_id có) → hiển thị trên sản phẩm đã mua.
          Đánh giá import (product_id trống) → hiển thị trên sản phẩm có nhóm đánh giá (group_rating) trùng với cột Nhóm.
        </div>

        <div className="mb-2 flex items-center justify-between flex-wrap gap-2">
          <span className="text-sm text-gray-600">Tổng số bản ghi: {data?.total ?? 0}</span>
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
                            <a href={`/products/${r.product_slug}#reviews`} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
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
                          onChange={(e) => setRowVal(r.id, 'user_name', e.target.value)}
                          onBlur={() => handleSaveRow(r)}
                          className="rounded border border-gray-300 px-2 py-1 text-xs w-full min-w-0"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <input
                          type="number"
                          min={1}
                          max={5}
                          value={Number(getRowVal(r, 'star') ?? 5)}
                          onChange={(e) => setRowVal(r.id, 'star', Math.min(5, Math.max(1, parseInt(e.target.value, 10) || 5)))}
                          onBlur={() => handleSaveRow(r)}
                          className="rounded border border-gray-300 px-1 py-0.5 text-xs w-12"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <input
                          type="text"
                          value={String(getRowVal(r, 'title') ?? '')}
                          onChange={(e) => setRowVal(r.id, 'title', e.target.value)}
                          onBlur={() => handleSaveRow(r)}
                          className="rounded border border-gray-300 px-2 py-1 text-xs w-full min-w-0"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <input
                          type="text"
                          value={String(getRowVal(r, 'content') ?? '')}
                          onChange={(e) => setRowVal(r.id, 'content', e.target.value)}
                          onBlur={() => handleSaveRow(r)}
                          className="rounded border border-gray-300 px-2 py-1 text-xs w-full min-w-0"
                          placeholder="Nội dung"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <input
                          type="number"
                          min={0}
                          value={Math.max(0, Number(getRowVal(r, 'group') ?? 0) || 0)}
                          onChange={(e) => setRowVal(r.id, 'group', Math.max(0, parseInt(e.target.value, 10) || 0))}
                          onBlur={() => handleSaveRow(r)}
                          className="rounded border border-gray-300 px-1 py-0.5 text-xs w-14"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <input
                          type="number"
                          min={0}
                          value={Math.max(0, Number(getRowVal(r, 'useful') ?? 0) || 0)}
                          onChange={(e) => setRowVal(r.id, 'useful', Math.max(0, parseInt(e.target.value, 10) || 0))}
                          onBlur={() => handleSaveRow(r)}
                          className="rounded border border-gray-300 px-1 py-0.5 text-xs w-16"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <div className="space-y-1">
                          <input
                            type="text"
                            value={String(getRowVal(r, 'reply_name') ?? '')}
                            onChange={(e) => setRowVal(r.id, 'reply_name', e.target.value)}
                            onBlur={() => handleSaveRow(r)}
                            className="rounded border border-gray-300 px-2 py-0.5 text-xs w-full"
                            placeholder="Tên"
                          />
                          <input
                            type="text"
                            value={String(getRowVal(r, 'reply_content') ?? '')}
                            onChange={(e) => setRowVal(r.id, 'reply_content', e.target.value)}
                            onBlur={() => handleSaveRow(r)}
                            className="rounded border border-gray-300 px-2 py-0.5 text-xs w-full"
                            placeholder="Nội dung"
                          />
                        </div>
                      </td>
                      <td className="py-2 px-2">
                        <select
                          value={getRowVal(r, 'is_active') ? '1' : '0'}
                          onChange={(e) => setRowVal(r.id, 'is_active', e.target.value === '1')}
                          onBlur={() => handleSaveRow(r)}
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
                        <button
                          type="button"
                          onClick={() => handleSaveRow(r)}
                          disabled={savingId === r.id}
                          className="text-blue-600 hover:underline text-xs mr-1 disabled:opacity-50"
                        >
                          {savingId === r.id ? 'Đang lưu...' : 'Lưu'}
                        </button>
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
