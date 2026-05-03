'use client';

import { Fragment, useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import AdminLayout from '@/components/admin/AdminLayout';
import {
  adminMemberAPI,
  adminStaffRolePresetsAPI,
  type AdminMember,
  type LinkedStaffRoleOption,
} from '@/lib/admin-api';
import { getStoredAdminRole, isPrivilegedAdminRole } from '@/lib/admin-role';
import {
  ADMIN_MODULE_LABELS,
  ADMIN_MODULE_KEYS_ASSIGNABLE,
  presetModuleKeysForStaffRole,
} from '@/lib/admin-modules';

const PAGE_SIZE = 20;

const LINKED_STAFF_OPTIONS: { value: LinkedStaffRoleOption; label: string }[] = [
  { value: 'none', label: 'Không' },
  { value: 'order_manager', label: 'NV đơn hàng' },
  { value: 'admin', label: 'Quản trị (full)' },
  { value: 'product_manager', label: 'NV SP / danh mục' },
  { value: 'content_manager', label: 'NV nội dung' },
];

function linkedStaffSelectValue(m: AdminMember): LinkedStaffRoleOption {
  if (!m.has_linked_admin) return 'none';
  const r = (m.linked_admin_role || '').toLowerCase();
  if (r === 'order_manager') return 'order_manager';
  if (r === 'admin' || r === 'super_admin') return 'admin';
  if (r === 'product_manager') return 'product_manager';
  if (r === 'content_manager') return 'content_manager';
  return 'none';
}

function formatLinkedRoleDisplay(m: AdminMember): string {
  if (!m.has_linked_admin || !m.linked_admin_role) return '—';
  const r = m.linked_admin_role.toLowerCase();
  const map: Record<string, string> = {
    order_manager: 'NV đơn hàng',
    admin: 'Quản trị',
    super_admin: 'Super admin',
    product_manager: 'NV SP / danh mục',
    content_manager: 'NV nội dung',
  };
  const base = map[r] || m.linked_admin_role;
  const n = m.linked_admin_modules?.length ?? 0;
  const hint = n > 0 ? ` (${n} mục)` : '';
  return base + hint;
}

function formatDate(s: string | null | undefined) {
  if (!s) return '—';
  const d = new Date(s);
  return d.toLocaleDateString('vi-VN') + ' ' + d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
}

function formatBirthShort(s: string | null | undefined) {
  if (!s) return '—';
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) {
    const [y, m, d] = s.slice(0, 10).split('-');
    return `${d}/${m}/${y}`;
  }
  const dt = new Date(s);
  return Number.isNaN(dt.getTime()) ? '—' : dt.toLocaleDateString('vi-VN');
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
  const [linkedBusyId, setLinkedBusyId] = useState<number | null>(null);
  const [staffPanelUserId, setStaffPanelUserId] = useState<number | null>(null);
  const [staffPanelDraft, setStaffPanelDraft] = useState<string[]>([]);
  const [presetModulesByRole, setPresetModulesByRole] = useState<Record<string, string[]>>({});

  const canManageLinkedStaff = isPrivilegedAdminRole(getStoredAdminRole());

  useEffect(() => {
    if (!canManageLinkedStaff) return;
    let cancelled = false;
    adminStaffRolePresetsAPI
      .list()
      .then((res) => {
        if (cancelled) return;
        const m: Record<string, string[]> = {};
        for (const it of res.items) {
          m[it.role] = it.modules;
        }
        setPresetModulesByRole(m);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [canManageLinkedStaff]);

  function presetModulesForLinkedRole(role: LinkedStaffRoleOption): string[] {
    if (role === 'order_manager' || role === 'product_manager' || role === 'content_manager') {
      const fromApi = presetModulesByRole[role];
      if (fromApi && fromApi.length > 0) return [...fromApi];
    }
    return presetModuleKeysForStaffRole(role);
  }

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

  const handleLinkedStaffChange = async (m: AdminMember, staff_role: LinkedStaffRoleOption) => {
    if (!canManageLinkedStaff) return;
    setLinkedBusyId(m.id);
    try {
      await adminMemberAPI.setLinkedStaff(m.id, staff_role);
      showToast('ok', 'Đã cập nhật quyền quản trị web');
      setStaffPanelUserId((prev) => (prev === m.id ? null : prev));
      fetchMembers();
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Lỗi cập nhật');
    } finally {
      setLinkedBusyId(null);
    }
  };

  const toggleStaffPanel = (m: AdminMember) => {
    const role = linkedStaffSelectValue(m);
    if (role === 'none' || role === 'admin') return;
    if (staffPanelUserId === m.id) {
      setStaffPanelUserId(null);
      return;
    }
    setStaffPanelUserId(m.id);
    const seed =
      m.linked_admin_modules && m.linked_admin_modules.length > 0
        ? [...m.linked_admin_modules]
        : presetModulesForLinkedRole(role);
    setStaffPanelDraft(seed);
  };

  const toggleStaffPanelModule = (key: string) => {
    setStaffPanelDraft((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  };

  const saveStaffPanelModules = async (m: AdminMember) => {
    if (!canManageLinkedStaff) return;
    const role = linkedStaffSelectValue(m);
    setLinkedBusyId(m.id);
    try {
      await adminMemberAPI.setLinkedStaff(m.id, role, staffPanelDraft);
      showToast('ok', 'Đã lưu quyền theo mục');
      setStaffPanelUserId(null);
      fetchMembers();
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Lỗi cập nhật');
    } finally {
      setLinkedBusyId(null);
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
            <p className="text-gray-600 text-sm mt-1">
              Danh sách khách hàng — bấm <strong>Chi tiết</strong> để xem email, ngày sinh, thời gian tạo.
            </p>
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
                      <th className="py-3 px-4">Ngày sinh</th>
                      <th className="py-3 px-4">Trạng thái</th>
                      <th className="py-3 px-4">Ngày đăng ký</th>
                      <th className="py-3 px-4">Đăng nhập gần nhất</th>
                      <th className="py-3 px-4 min-w-[200px]">Quản trị web</th>
                      <th className="py-3 px-4 text-center">Thao tác</th>
                    </tr>
                  </thead>
                  <tbody>
                    {members.map((m) => {
                      const selRole = linkedStaffSelectValue(m);
                      const showModuleBtn =
                        canManageLinkedStaff &&
                        (m.email || '').trim() &&
                        selRole !== 'none' &&
                        selRole !== 'admin';
                      return (
                        <Fragment key={m.id}>
                          <tr className="border-b border-gray-100 hover:bg-gray-50/50">
                            <td className="py-3 px-4 font-mono text-gray-600">{m.id}</td>
                            <td className="py-3 px-4 font-medium">{m.phone || '—'}</td>
                            <td className="py-3 px-4">{m.full_name || '—'}</td>
                            <td className="py-3 px-4 text-gray-600">{m.email || '—'}</td>
                            <td className="py-3 px-4 text-gray-600 whitespace-nowrap">{formatBirthShort(m.date_of_birth)}</td>
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
                            <td className="py-3 px-4 align-middle">
                              {canManageLinkedStaff ? (
                                <div className="flex flex-col gap-1.5 max-w-[260px]">
                                  <select
                                    value={selRole}
                                    disabled={linkedBusyId === m.id || !(m.email || '').trim()}
                                    title={
                                      !(m.email || '').trim()
                                        ? 'Thành viên cần có email để gán quyền'
                                        : 'Đăng nhập shop → Cá nhân → Quản trị web'
                                    }
                                    onChange={(e) => {
                                      const v = e.target.value as LinkedStaffRoleOption;
                                      if (staffPanelUserId === m.id) setStaffPanelUserId(null);
                                      handleLinkedStaffChange(m, v);
                                    }}
                                    className="w-full px-2 py-1.5 border border-gray-200 rounded-lg text-xs bg-white disabled:opacity-50"
                                  >
                                    {LINKED_STAFF_OPTIONS.map((o) => (
                                      <option key={o.value} value={o.value}>
                                        {o.label}
                                      </option>
                                    ))}
                                  </select>
                                  {showModuleBtn ? (
                                    <button
                                      type="button"
                                      disabled={linkedBusyId === m.id}
                                      onClick={() => toggleStaffPanel(m)}
                                      className="text-left text-xs font-medium text-slate-700 underline-offset-2 hover:underline disabled:opacity-50"
                                    >
                                      {staffPanelUserId === m.id ? 'Đóng chọn mục' : 'Chọn mục cụ thể'}
                                    </button>
                                  ) : null}
                                </div>
                              ) : (
                                <span className="text-gray-600 text-xs">{formatLinkedRoleDisplay(m)}</span>
                              )}
                            </td>
                            <td className="py-3 px-4 text-center">
                              <div className="flex flex-wrap items-center justify-center gap-1.5">
                                <Link
                                  href={`/admin/members/${m.id}`}
                                  className="inline-block px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 text-slate-800 hover:bg-slate-200"
                                >
                                  Chi tiết
                                </Link>
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
                              </div>
                            </td>
                          </tr>
                          {staffPanelUserId === m.id ? (
                            <tr className="border-b border-gray-100 bg-slate-50">
                              <td colSpan={10} className="p-4">
                                <p className="text-xs text-gray-600 mb-3">
                                  Chọn mục được phép trong menu quản trị. <strong>Lưu</strong> gửi danh sách lên server;
                                  đổi vai trò ở dropdown trên (không đánh dấu mục) = preset mặc định của vai đó.
                                </p>
                                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2 mb-4">
                                  {ADMIN_MODULE_KEYS_ASSIGNABLE.map((key) => (
                                    <label
                                      key={key}
                                      className="flex items-center gap-2 text-xs text-gray-800 cursor-pointer"
                                    >
                                      <input
                                        type="checkbox"
                                        checked={staffPanelDraft.includes(key)}
                                        onChange={() => toggleStaffPanelModule(key)}
                                        className="rounded border-gray-300"
                                      />
                                      <span>{ADMIN_MODULE_LABELS[key] || key}</span>
                                    </label>
                                  ))}
                                </div>
                                <div className="flex flex-wrap gap-2">
                                  <button
                                    type="button"
                                    disabled={linkedBusyId === m.id}
                                    onClick={() => saveStaffPanelModules(m)}
                                    className="px-3 py-1.5 rounded-lg bg-slate-700 text-white text-xs font-medium hover:bg-slate-600 disabled:opacity-50"
                                  >
                                    Lưu quyền mục
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => setStaffPanelUserId(null)}
                                    className="px-3 py-1.5 rounded-lg border border-gray-300 text-xs font-medium text-gray-700 hover:bg-white"
                                  >
                                    Huỷ
                                  </button>
                                </div>
                              </td>
                            </tr>
                          ) : null}
                        </Fragment>
                      );
                    })}
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
