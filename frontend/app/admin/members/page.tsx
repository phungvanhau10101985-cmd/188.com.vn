'use client';

import { useState, useEffect, useCallback } from 'react';
import AdminLayout from '@/components/admin/AdminLayout';
import { adminMemberAPI, type AdminMember } from '@/lib/admin-api';

const PAGE_SIZE = 20;

function formatDate(s: string | null | undefined) {
  if (!s) return '—';
  const d = new Date(s);
  return d.toLocaleDateString('vi-VN') + ' ' + d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
}

export default function AdminMembersPage() {
  const [loading, setLoading] = useState(true);
  const [members, setMembers] = useState<AdminMember[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [keyword, setKeyword] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [updatingId, setUpdatingId] = useState<number | null>(null);

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 3000);
  };

  const fetchMembers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminMemberAPI.getMembers({
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
        keyword: keyword.trim() || undefined,
      });
      setMembers(res.items);
      setTotal(res.total);
    } catch {
      showToast('err', 'Lỗi tải danh sách thành viên');
      setMembers([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [page, keyword]);

  useEffect(() => {
    fetchMembers();
  }, [fetchMembers]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setKeyword(searchInput.trim());
    setPage(0);
  };

  const handleToggleActive = async (m: AdminMember) => {
    setUpdatingId(m.id);
    try {
      await adminMemberAPI.updateMember(m.id, { is_active: !m.is_active });
      showToast('ok', m.is_active ? 'Đã tắt kích hoạt' : 'Đã bật kích hoạt');
      fetchMembers();
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Lỗi cập nhật');
    } finally {
      setUpdatingId(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <AdminLayout>
      <div className="p-6">
        {toast && (
          <div
            className={`fixed top-4 right-4 z-50 px-4 py-2 rounded-lg shadow-lg ${
              toast.type === 'ok' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
            }`}
          >
            {toast.msg}
          </div>
        )}

        <div className="flex flex-wrap justify-between items-center gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Quản lý thành viên</h1>
            <p className="text-gray-600 text-sm mt-1">Xem danh sách và trạng thái tài khoản khách hàng</p>
          </div>
          <button
            type="button"
            onClick={() => fetchMembers()}
            className="px-4 py-2 bg-slate-700 text-white rounded-lg hover:bg-slate-600 text-sm font-medium"
          >
            Làm mới
          </button>
        </div>

        <div className="bg-white rounded-xl shadow border border-gray-100 overflow-hidden">
          <div className="p-4 border-b border-gray-100">
            <form onSubmit={handleSearch} className="flex flex-wrap gap-2">
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Tìm theo SĐT, email, họ tên..."
                className="flex-1 min-w-[200px] px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
              />
              <button
                type="submit"
                className="px-4 py-2 bg-slate-700 text-white rounded-lg hover:bg-slate-600 text-sm font-medium"
              >
                Tìm kiếm
              </button>
              {keyword && (
                <button
                  type="button"
                  onClick={() => { setSearchInput(''); setKeyword(''); setPage(0); }}
                  className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 text-sm"
                >
                  Xóa bộ lọc
                </button>
              )}
            </form>
          </div>

          {loading ? (
            <div className="p-12 text-center text-gray-500">Đang tải...</div>
          ) : members.length === 0 ? (
            <div className="p-12 text-center text-gray-500">
              {keyword ? 'Không có thành viên nào trùng khớp.' : 'Chưa có thành viên.'}
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-100 text-left text-gray-600 font-medium">
                      <th className="py-3 px-4">ID</th>
                      <th className="py-3 px-4">Số điện thoại</th>
                      <th className="py-3 px-4">Họ tên</th>
                      <th className="py-3 px-4">Email</th>
                      <th className="py-3 px-4">Trạng thái</th>
                      <th className="py-3 px-4">Ngày đăng ký</th>
                      <th className="py-3 px-4">Đăng nhập gần nhất</th>
                      <th className="py-3 px-4 text-center">Thao tác</th>
                    </tr>
                  </thead>
                  <tbody>
                    {members.map((m) => (
                      <tr key={m.id} className="border-b border-gray-100 hover:bg-gray-50/50">
                        <td className="py-3 px-4 font-mono text-gray-600">{m.id}</td>
                        <td className="py-3 px-4 font-medium">{m.phone}</td>
                        <td className="py-3 px-4">{m.full_name || '—'}</td>
                        <td className="py-3 px-4 text-gray-600">{m.email || '—'}</td>
                        <td className="py-3 px-4">
                          <span
                            className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                              m.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                            }`}
                          >
                            {m.is_active ? 'Đang hoạt động' : 'Đã khóa'}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-gray-600">{formatDate(m.created_at)}</td>
                        <td className="py-3 px-4 text-gray-600">{formatDate(m.last_login)}</td>
                        <td className="py-3 px-4 text-center">
                          <button
                            type="button"
                            onClick={() => handleToggleActive(m)}
                            disabled={updatingId === m.id}
                            className={`px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-50 ${
                              m.is_active
                                ? 'bg-amber-100 text-amber-800 hover:bg-amber-200'
                                : 'bg-green-100 text-green-800 hover:bg-green-200'
                            }`}
                          >
                            {updatingId === m.id ? '...' : m.is_active ? 'Khóa' : 'Mở khóa'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {totalPages > 1 && (
                <div className="p-4 border-t border-gray-100 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-gray-600 text-sm">
                    Hiển thị {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} / {total}
                  </p>
                  <div className="flex gap-1">
                    <button
                      type="button"
                      onClick={() => setPage((p) => Math.max(0, p - 1))}
                      disabled={page === 0}
                      className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm font-medium disabled:opacity-50 hover:bg-gray-50"
                    >
                      Trước
                    </button>
                    <span className="px-3 py-1.5 text-sm text-gray-600">
                      Trang {page + 1} / {totalPages}
                    </span>
                    <button
                      type="button"
                      onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                      disabled={page >= totalPages - 1}
                      className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm font-medium disabled:opacity-50 hover:bg-gray-50"
                    >
                      Sau
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </AdminLayout>
  );
}
