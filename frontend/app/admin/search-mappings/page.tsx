'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import AdminLayout from '@/components/admin/AdminLayout';
import {
  adminSearchMappingAPI,
  type AdminSearchMapping,
  type AdminSearchMappingsResponse,
  type AdminSearchMappingCreateRequest,
} from '@/lib/admin-api';

const PAGE_SIZE = 50;

export default function AdminSearchMappingsPage() {
  const [data, setData] = useState<AdminSearchMappingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [keyword, setKeyword] = useState('');
  const [mappingType, setMappingType] = useState<string>('');
  const [page, setPage] = useState(1);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [newMapping, setNewMapping] = useState<AdminSearchMappingCreateRequest>({
    keyword_input: '',
    keyword_target: '',
    type: 'product_search',
  });

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 3000);
  };

  const fetchMappings = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminSearchMappingAPI.getMappings({
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
        keyword: keyword.trim() || undefined,
        mapping_type: mappingType || undefined,
      });
      setData(res);
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Lỗi tải danh sách mapping');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [page, keyword, mappingType]);

  useEffect(() => {
    fetchMappings();
  }, [fetchMappings]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchMappings();
  };

  const handleDelete = async (mapping: AdminSearchMapping) => {
    if (!confirm(`Xóa mapping: "${mapping.keyword_input}" -> "${mapping.keyword_target}"?`)) return;
    setDeletingId(mapping.id);
    try {
      await adminSearchMappingAPI.deleteMapping(mapping.id);
      showToast('ok', 'Đã xóa mapping');
      await fetchMappings();
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Xóa thất bại');
    } finally {
      setDeletingId(null);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMapping.keyword_input.trim() || !newMapping.keyword_target.trim()) {
      showToast('err', 'Vui lòng nhập đầy đủ từ khóa');
      return;
    }
    setCreating(true);
    try {
      await adminSearchMappingAPI.createMapping({
        ...newMapping,
        keyword_input: newMapping.keyword_input.trim(),
        keyword_target: newMapping.keyword_target.trim(),
      });
      showToast('ok', 'Đã tạo mapping');
      setNewMapping({ keyword_input: '', keyword_target: '', type: 'product_search' });
      await fetchMappings();
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Tạo mapping thất bại');
    } finally {
      setCreating(false);
    }
  };

  const totalPages = data?.total_pages ?? 1;
  const items = useMemo(() => data?.items || [], [data?.items]);

  return (
    <AdminLayout>
      <div className="p-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Danh sách từ khóa mapping</h1>
          {toast && (
            <span
              className={`text-sm px-3 py-1.5 rounded-lg ${
                toast.type === 'ok' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
              }`}
            >
              {toast.msg}
            </span>
          )}
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6">
          <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Keyword input</label>
              <input
                type="text"
                value={newMapping.keyword_input}
                onChange={(e) => setNewMapping((s) => ({ ...s, keyword_input: e.target.value }))}
                placeholder="Từ khóa người dùng nhập"
                className="w-56 rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Keyword target</label>
              <input
                type="text"
                value={newMapping.keyword_target}
                onChange={(e) => setNewMapping((s) => ({ ...s, keyword_target: e.target.value }))}
                placeholder="Từ khóa chuẩn hoặc /danh-muc/..."
                className="w-64 rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Loại mapping</label>
              <select
                value={newMapping.type}
                onChange={(e) => setNewMapping((s) => ({ ...s, type: e.target.value as AdminSearchMappingCreateRequest['type'] }))}
                className="w-56 rounded-lg border border-gray-300 px-3 py-2 text-sm"
              >
                <option value="product_search">product_search</option>
                <option value="category_redirect">category_redirect</option>
              </select>
            </div>
            <button
              type="submit"
              disabled={creating}
              className="px-4 py-2 rounded-lg bg-[#ea580c] text-white text-sm font-semibold hover:bg-[#d97706] disabled:opacity-60"
            >
              {creating ? 'Đang tạo...' : 'Tạo mapping'}
            </button>
          </form>

          <form onSubmit={handleSearch} className="flex flex-wrap items-end gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Từ khóa</label>
              <input
                type="text"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="keyword_input / keyword_target"
                className="w-64 rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Loại mapping</label>
              <select
                value={mappingType}
                onChange={(e) => setMappingType(e.target.value)}
                className="w-56 rounded-lg border border-gray-300 px-3 py-2 text-sm"
              >
                <option value="">Tất cả</option>
                <option value="product_search">product_search</option>
                <option value="category_redirect">category_redirect</option>
              </select>
            </div>
            <button
              type="submit"
              className="px-4 py-2 rounded-lg bg-[#ea580c] text-white text-sm font-semibold hover:bg-[#d97706]"
            >
              Lọc
            </button>
          </form>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="text-left px-4 py-3 w-[220px]">Keyword Input</th>
                  <th className="text-left px-4 py-3">Keyword Target</th>
                  <th className="text-left px-4 py-3 w-[160px]">Type</th>
                  <th className="text-right px-4 py-3 w-[110px]">Hit</th>
                  <th className="text-left px-4 py-3 w-[180px]">Updated</th>
                  <th className="text-right px-4 py-3 w-[110px]">Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-6 text-center text-gray-500">
                      Đang tải...
                    </td>
                  </tr>
                ) : items.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-6 text-center text-gray-500">
                      Không có mapping
                    </td>
                  </tr>
                ) : (
                  items.map((item) => (
                    <tr key={item.id} className="border-t border-gray-100">
                      <td className="px-4 py-3 font-medium text-gray-800">{item.keyword_input}</td>
                      <td className="px-4 py-3 text-gray-700 break-all">{item.keyword_target}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex px-2 py-1 rounded-full text-xs font-semibold ${
                            item.type === 'category_redirect'
                              ? 'bg-blue-50 text-blue-700'
                              : 'bg-amber-50 text-amber-700'
                          }`}
                        >
                          {item.type}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right text-gray-700">{item.hit_count ?? 0}</td>
                      <td className="px-4 py-3 text-gray-600">
                        {item.updated_at ? new Date(item.updated_at).toLocaleString('vi-VN') : '-'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={() => handleDelete(item)}
                          disabled={deletingId === item.id}
                          className="text-xs font-semibold text-red-600 hover:text-red-700 disabled:opacity-50"
                        >
                          {deletingId === item.id ? 'Đang xóa...' : 'Xóa'}
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 bg-white">
            <span className="text-sm text-gray-600">
              Tổng: {data?.total ?? 0}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-3 py-1.5 text-sm rounded-lg border border-gray-300 text-gray-700 disabled:opacity-50"
              >
                ← Trước
              </button>
              <span className="text-sm text-gray-600">
                Trang {page} / {totalPages}
              </span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="px-3 py-1.5 text-sm rounded-lg border border-gray-300 text-gray-700 disabled:opacity-50"
              >
                Sau →
              </button>
            </div>
          </div>
        </div>
      </div>
    </AdminLayout>
  );
}
