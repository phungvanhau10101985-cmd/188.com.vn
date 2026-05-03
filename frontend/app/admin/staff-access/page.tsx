'use client';

import { Fragment, useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  adminStaffAPI,
  adminStaffRolePresetsAPI,
  type AdminStaffAccountRow,
  type StaffRolePresetCrudFlags,
  type StaffRolePresetItem,
} from '@/lib/admin-api';
import {
  ADMIN_MODULE_KEYS_ASSIGNABLE,
  ADMIN_MODULE_LABELS,
  ADMIN_MODULE_ORDER,
  presetModuleKeysForStaffRole,
} from '@/lib/admin-modules';
import { getStoredAdminRole, isPrivilegedAdminRole } from '@/lib/admin-role';
import { crudCell } from '@/lib/staff-preset-crud-matrix';

function roleLabel(role: string): string {
  const m: Record<string, string> = {
    super_admin: 'Super admin',
    admin: 'Quản trị (full)',
    order_manager: 'NV đơn hàng',
    product_manager: 'NV SP / danh mục',
    content_manager: 'NV nội dung',
  };
  return m[role.toLowerCase()] || role;
}

function presetSubtitle(roleKey: string): string {
  const m: Record<string, string> = {
    order_manager: 'Áp dụng cho NV đơn hàng khi không bật « Tùy chỉnh mục menu ».',
    product_manager:
      'Áp dụng cho NV sản phẩm / danh mục khi không bật tùy chỉnh. Super admin chỉnh cột « Xóa » từng mục rồi bấm « Lưu preset ».',
    content_manager:
      'Áp dụng cho NV nội dung khi không bật tùy chỉnh. Mặc định không xóa Q&A và đánh giá — có thể đổi nếu super_admin bật « Xóa ».',
  };
  return m[roleKey] || 'Preset lưu trong database.';
}

function fullCrud(): StaffRolePresetCrudFlags {
  return { view: true, create: true, update: true, delete: true };
}

function orderedPresetModules(modules: string[]): string[] {
  const set = new Set(modules);
  const primary = ADMIN_MODULE_ORDER.filter((k) => set.has(k));
  const rest = modules.filter((k) => !primary.includes(k)).sort();
  return [...primary, ...rest];
}

function rowNote(roleKey: string, moduleKey: string, flags: StaffRolePresetCrudFlags): string {
  if (
    roleKey === 'content_manager' &&
    (moduleKey === 'product_questions' || moduleKey === 'product_reviews') &&
    !flags.delete
  ) {
    return 'Chưa bật xóa — khớp mặc định NV nội dung.';
  }
  return '—';
}

function pickPresetModulesFromState(items: StaffRolePresetItem[], role: string): string[] {
  const r = role.toLowerCase();
  const hit = items.find((x) => x.role === r);
  if (hit?.modules?.length) return [...hit.modules];
  if (r === 'order_manager') return presetModuleKeysForStaffRole('order_manager');
  if (r === 'product_manager') return presetModuleKeysForStaffRole('product_manager');
  if (r === 'content_manager') return presetModuleKeysForStaffRole('content_manager');
  return [];
}

export default function StaffAccessPage() {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState<AdminStaffAccountRow[]>([]);
  const [presetItems, setPresetItems] = useState<StaffRolePresetItem[]>([]);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [draftRole, setDraftRole] = useState('');
  const [useCustomModules, setUseCustomModules] = useState(false);
  const [draftModules, setDraftModules] = useState<string[]>([]);
  const [saveBusyId, setSaveBusyId] = useState<number | null>(null);
  const [presetSavingRole, setPresetSavingRole] = useState<string | null>(null);

  const isSuperEditor =
    (typeof window !== 'undefined' ? getStoredAdminRole() || '' : '').toLowerCase() === 'super_admin';

  const roleSelectOptions = [
    ...(isSuperEditor ? [{ value: 'super_admin', label: 'Super admin' }] : []),
    { value: 'admin', label: 'Quản trị (full)' },
    { value: 'order_manager', label: 'NV đơn hàng' },
    { value: 'product_manager', label: 'NV SP / danh mục' },
    { value: 'content_manager', label: 'NV nội dung' },
  ];

  useEffect(() => {
    const ok = isPrivilegedAdminRole(getStoredAdminRole());
    setAllowed(ok);
    if (!ok) router.replace('/admin/orders');
  }, [router]);

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 3500);
  };

  const load = useCallback(async () => {
    if (!allowed) return;
    setLoading(true);
    try {
      const staffRes = await adminStaffAPI.list();
      setRows(staffRes.items || []);
      try {
        const presetRes = await adminStaffRolePresetsAPI.list();
        setPresetItems(presetRes.items || []);
      } catch {
        setPresetItems([]);
      }
    } catch (e: unknown) {
      showToast('err', (e as Error)?.message || 'Không tải được danh sách');
      setRows([]);
      setPresetItems([]);
    } finally {
      setLoading(false);
    }
  }, [allowed]);

  useEffect(() => {
    load();
  }, [load]);

  const openPanel = (row: AdminStaffAccountRow) => {
    if (expandedId === row.id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(row.id);
    setDraftRole(row.role);
    setUseCustomModules(row.uses_custom_modules);
    const assignableFromApi = row.modules.filter((m) => ADMIN_MODULE_KEYS_ASSIGNABLE.includes(m));
    if (row.uses_custom_modules && assignableFromApi.length > 0) {
      setDraftModules(assignableFromApi);
    } else {
      setDraftModules(pickPresetModulesFromState(presetItems, row.role));
    }
  };

  const toggleDraftModule = (key: string) => {
    setDraftModules((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  };

  const isFullAdminRole = (r: string) => {
    const x = r.toLowerCase();
    return x === 'admin' || x === 'super_admin';
  };

  const handleSave = async (row: AdminStaffAccountRow) => {
    const full = isFullAdminRole(draftRole);
    setSaveBusyId(row.id);
    try {
      await adminStaffAPI.patchPermissions(row.id, {
        role: draftRole !== row.role ? draftRole : undefined,
        modules_mode: full ? 'preset' : useCustomModules ? 'custom' : 'preset',
        modules: full || !useCustomModules ? undefined : draftModules,
      });
      showToast('ok', 'Đã cập nhật quyền');
      setExpandedId(null);
      load();
    } catch (e: unknown) {
      showToast('err', (e as Error)?.message || 'Lưu thất bại');
    } finally {
      setSaveBusyId(null);
    }
  };

  const updatePresetCrud = (
    roleKey: string,
    moduleKey: string,
    field: keyof StaffRolePresetCrudFlags,
    value: boolean,
  ) => {
    setPresetItems((prev) =>
      prev.map((p) => {
        if (p.role !== roleKey) return p;
        const prevFlags = p.module_crud[moduleKey] || fullCrud();
        return {
          ...p,
          module_crud: {
            ...p.module_crud,
            [moduleKey]: { ...prevFlags, [field]: value },
          },
        };
      }),
    );
  };

  const addPresetModule = (roleKey: string, moduleKey: string) => {
    if (!moduleKey) return;
    setPresetItems((prev) =>
      prev.map((p) => {
        if (p.role !== roleKey || p.modules.includes(moduleKey)) return p;
        const modules = orderedPresetModules([...p.modules, moduleKey]);
        return {
          ...p,
          modules,
          module_crud: { ...p.module_crud, [moduleKey]: fullCrud() },
        };
      }),
    );
  };

  const removePresetModule = (roleKey: string, moduleKey: string) => {
    setPresetItems((prev) =>
      prev.map((p) => {
        if (p.role !== roleKey) return p;
        const modules = p.modules.filter((k) => k !== moduleKey);
        const { [moduleKey]: _, ...restCrud } = p.module_crud;
        return { ...p, modules, module_crud: restCrud };
      }),
    );
  };

  const saveStaffPreset = async (roleKey: string) => {
    const preset = presetItems.find((x) => x.role === roleKey);
    if (!preset || preset.modules.length === 0) {
      showToast('err', 'Cần ít nhất một mục trong preset.');
      return;
    }
    setPresetSavingRole(roleKey);
    try {
      await adminStaffRolePresetsAPI.put(roleKey, {
        modules: preset.modules,
        module_crud: preset.module_crud,
      });
      showToast('ok', 'Đã lưu preset vai trò');
      await load();
    } catch (e: unknown) {
      showToast('err', (e as Error)?.message || 'Không lưu được preset');
    } finally {
      setPresetSavingRole(null);
    }
  };

  if (!allowed) {
    return <div className="p-8 text-gray-600 text-sm">Đang kiểm tra quyền…</div>;
  }

  return (
      <div className="p-6 max-w-[100rem] mx-auto">
        {toast ? (
          <div
            className={`fixed top-4 right-4 z-50 px-4 py-2 rounded-lg shadow-lg text-white ${
              toast.type === 'ok' ? 'bg-green-600' : 'bg-red-600'
            }`}
          >
            {toast.msg}
          </div>
        ) : null}

        <div className="flex flex-wrap justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Quyền tài khoản nhân viên</h1>
            <p className="text-gray-600 text-sm mt-1 max-w-2xl">
              Cấu hình vai trò và quyền từng mục menu cho các tài khoản đăng nhập{' '}
              <strong>/admin</strong> (bảng admin_users). Liên kết shop hiển thị cột{' '}
              <em>Liên kết</em>.
            </p>
          </div>
          <button
            type="button"
            onClick={() => load()}
            className="px-4 py-2 bg-slate-700 text-white rounded-lg hover:bg-slate-600 text-sm font-medium self-start"
          >
            Làm mới
          </button>
        </div>

        <div className="bg-white rounded-xl shadow border border-gray-100 overflow-hidden">
          {loading ? (
            <div className="p-12 text-center text-gray-500">Đang tải…</div>
          ) : rows.length === 0 ? (
            <div className="p-12 text-center text-gray-500">Chưa có tài khoản admin.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100 text-left text-gray-600 font-medium">
                    <th className="py-3 px-4">ID</th>
                    <th className="py-3 px-4">Tài khoản</th>
                    <th className="py-3 px-4">Email</th>
                    <th className="py-3 px-4">Vai trò hiện tại</th>
                    <th className="py-3 px-4">Liên kết shop</th>
                    <th className="py-3 px-4">Quyền mục</th>
                    <th className="py-3 px-4 text-center">Chi tiết</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <Fragment key={row.id}>
                      <tr className="border-b border-gray-100 hover:bg-gray-50/60">
                        <td className="py-3 px-4 font-mono text-gray-600">{row.id}</td>
                        <td className="py-3 px-4 font-medium">{row.username}</td>
                        <td className="py-3 px-4 text-gray-600">{row.email || '—'}</td>
                        <td className="py-3 px-4">{roleLabel(row.role)}</td>
                        <td className="py-3 px-4 text-gray-600">
                          {row.linked_user_id != null ? `#${row.linked_user_id}` : '—'}
                        </td>
                        <td className="py-3 px-4 text-gray-700">
                          {row.uses_custom_modules ? (
                            <span className="text-amber-800 font-medium">Tùy chỉnh ({row.modules.length} mục)</span>
                          ) : (
                            <span>Preset theo vai trò ({row.modules.length} mục)</span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-center">
                          <button
                            type="button"
                            onClick={() => openPanel(row)}
                            className="text-xs font-semibold text-slate-700 underline-offset-2 hover:underline"
                          >
                            {expandedId === row.id ? 'Thu gọn' : 'Chỉnh sửa'}
                          </button>
                        </td>
                      </tr>
                      {expandedId === row.id ? (
                        <tr className="border-b border-gray-100 bg-slate-50">
                          <td colSpan={7} className="p-4">
                            <div className="flex flex-wrap gap-4 items-start">
                              <label className="block min-w-[200px]">
                                <span className="text-xs font-semibold text-gray-600">Vai trò</span>
                                <select
                                  value={draftRole}
                                  onChange={(e) => {
                                    const v = e.target.value;
                                    setDraftRole(v);
                                    if (!isFullAdminRole(v) && !useCustomModules) {
                                      setDraftModules(pickPresetModulesFromState(presetItems, v));
                                    }
                                  }}
                                  disabled={saveBusyId === row.id}
                                  className="mt-1 block w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white"
                                >
                                  {roleSelectOptions.map((o) => (
                                    <option key={o.value} value={o.value}>
                                      {o.label}
                                    </option>
                                  ))}
                                </select>
                              </label>
                              {!isFullAdminRole(draftRole) ? (
                                <label className="inline-flex items-center gap-2 mt-6 cursor-pointer">
                                  <input
                                    type="checkbox"
                                    checked={useCustomModules}
                                    onChange={(e) => {
                                      const on = e.target.checked;
                                      setUseCustomModules(on);
                                      if (!on) setDraftModules(pickPresetModulesFromState(presetItems, draftRole));
                                    }}
                                    disabled={saveBusyId === row.id}
                                  />
                                  <span className="text-sm text-gray-800">Tùy chỉnh mục menu</span>
                                </label>
                              ) : (
                                <p className="mt-6 text-sm text-gray-600">
                                  Vai trò full mở toàn bộ mục (không giới hạn granular).
                                </p>
                              )}
                            </div>

                            {!isFullAdminRole(draftRole) && useCustomModules ? (
                              <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                                {ADMIN_MODULE_KEYS_ASSIGNABLE.map((key) => (
                                  <label
                                    key={key}
                                    className="flex items-center gap-2 text-xs text-gray-800 cursor-pointer"
                                  >
                                    <input
                                      type="checkbox"
                                      checked={draftModules.includes(key)}
                                      onChange={() => toggleDraftModule(key)}
                                      disabled={saveBusyId === row.id}
                                      className="rounded border-gray-300"
                                    />
                                    <span>{ADMIN_MODULE_LABELS[key] || key}</span>
                                  </label>
                                ))}
                              </div>
                            ) : null}

                            <div className="mt-4 flex flex-wrap gap-2">
                              <button
                                type="button"
                                disabled={saveBusyId === row.id}
                                onClick={() => handleSave(row)}
                                className="px-4 py-2 rounded-lg bg-slate-700 text-white text-sm font-medium hover:bg-slate-600 disabled:opacity-50"
                              >
                                {saveBusyId === row.id ? 'Đang lưu…' : 'Lưu'}
                              </button>
                              <button
                                type="button"
                                onClick={() => setExpandedId(null)}
                                className="px-4 py-2 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-white"
                              >
                                Huỷ
                              </button>
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <section className="mt-10 space-y-6" aria-labelledby="preset-crud-heading">
          <div>
            <h2 id="preset-crud-heading" className="text-lg font-bold text-gray-900">
              Preset vai trò NV — Xem / Thêm / Sửa / Xóa (lưu database)
            </h2>
            <p className="text-sm text-gray-600 mt-2 max-w-3xl">
              Ba vai trò NV đơn hàng / SP-danh mục / nội dung lấy danh sách mục và ma trận CRUD từ bảng{' '}
              <code className="text-xs bg-gray-100 px-1 rounded">admin_staff_role_presets</code>. Server kiểm tra thao tác
              theo HTTP method (GET→xem, POST→thêm, PUT/PATCH→sửa, DELETE→xóa).{' '}
              <strong>Super admin</strong> có thể thêm/bớt mục và sửa ô quyền rồi bấm « Lưu preset »; quản trị (full) chỉ
              xem bảng. Tài khoản « Tùy chỉnh mục menu » không đọc ma trận preset — được đủ thao tác trên các mục đã chọn.
            </p>
            <p className="text-sm text-gray-600 mt-2 max-w-3xl">
              Super admin và Quản trị (full) luôn có toàn bộ mục và API — không cấu hình qua bảng dưới đây.
            </p>
            {isSuperEditor ? (
              <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 max-w-3xl">
                <strong>Super admin — chỗ cài quyền xóa / không xóa cho NV SP:</strong> kéo xuống preset{' '}
                <strong>NV SP / danh mục</strong>, chỉnh cột <strong>Xóa</strong> từng dòng mục, rồi bấm{' '}
                <strong>Lưu preset</strong>. Chỉ super_admin mới gọi được API lưu preset.
              </div>
            ) : null}
          </div>

          <div className="space-y-4">
            {presetItems.length === 0 && !loading ? (
              <p className="text-sm text-amber-800">Không tải được preset từ server (hoặc chưa khởi tạo).</p>
            ) : null}
            {presetItems.map((preset) => {
              const mods = orderedPresetModules(preset.modules);
              const addable = ADMIN_MODULE_KEYS_ASSIGNABLE.filter((k) => !preset.modules.includes(k));
              return (
                <details
                  key={preset.role}
                  className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden"
                  open
                >
                  <summary className="cursor-pointer list-none px-4 py-3 bg-gray-50 border-b border-gray-100 flex flex-wrap items-baseline justify-between gap-2 hover:bg-gray-100/80 marker:content-none [&::-webkit-details-marker]:hidden">
                    <span className="font-semibold text-gray-900">{roleLabel(preset.role)}</span>
                    <span className="text-xs text-gray-500">Thu gọn / mở rộng</span>
                  </summary>
                  <p className="px-4 pt-3 pb-2 text-xs text-gray-600 border-b border-gray-50">
                    {presetSubtitle(preset.role)}
                  </p>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs sm:text-sm">
                      <thead>
                        <tr className="bg-white border-b border-gray-100 text-left text-gray-600 font-medium">
                          <th className="py-2 px-4">Mục</th>
                          <th className="py-2 px-3 text-center w-14">Xem</th>
                          <th className="py-2 px-3 text-center w-14">Thêm</th>
                          <th className="py-2 px-3 text-center w-14">Sửa</th>
                          <th className="py-2 px-3 text-center w-14">Xóa</th>
                          <th className="py-2 px-4 min-w-[10rem]">Ghi chú</th>
                          {isSuperEditor ? <th className="py-2 px-3 w-24 text-center">—</th> : null}
                        </tr>
                      </thead>
                      <tbody>
                        {mods.map((mk) => {
                          const flags = preset.module_crud[mk] || fullCrud();
                          const note = rowNote(preset.role, mk, flags);
                          return (
                            <tr key={mk} className="border-b border-gray-50 hover:bg-gray-50/50">
                              <td className="py-2 px-4 text-gray-800">{ADMIN_MODULE_LABELS[mk] || mk}</td>
                              {(['view', 'create', 'update', 'delete'] as const).map((field) => (
                                <td key={field} className="py-2 px-3 text-center">
                                  {isSuperEditor ? (
                                    <input
                                      type="checkbox"
                                      checked={flags[field]}
                                      onChange={(e) =>
                                        updatePresetCrud(preset.role, mk, field, e.target.checked)
                                      }
                                      className="rounded border-gray-300"
                                      aria-label={`${mk} ${field}`}
                                    />
                                  ) : (
                                    <span className="tabular-nums">{crudCell(flags[field])}</span>
                                  )}
                                </td>
                              ))}
                              <td className="py-2 px-4 text-gray-500">{note}</td>
                              {isSuperEditor ? (
                                <td className="py-2 px-3 text-center">
                                  <button
                                    type="button"
                                    className="text-xs text-red-700 underline-offset-2 hover:underline"
                                    onClick={() => removePresetModule(preset.role, mk)}
                                  >
                                    Gỡ mục
                                  </button>
                                </td>
                              ) : null}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  {isSuperEditor ? (
                    <div className="flex flex-wrap items-center gap-3 px-4 py-3 bg-gray-50/80 border-t border-gray-100">
                      <label className="flex items-center gap-2 text-sm text-gray-800">
                        <span className="text-xs font-semibold text-gray-600">Thêm mục</span>
                        <select
                          className="border border-gray-200 rounded-lg px-2 py-1.5 text-sm bg-white"
                          defaultValue=""
                          onChange={(e) => {
                            const v = e.target.value;
                            if (v) addPresetModule(preset.role, v);
                            e.target.value = '';
                          }}
                        >
                          <option value="">— Chọn —</option>
                          {addable.map((k) => (
                            <option key={k} value={k}>
                              {ADMIN_MODULE_LABELS[k] || k}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        type="button"
                        disabled={presetSavingRole === preset.role || mods.length === 0}
                        onClick={() => saveStaffPreset(preset.role)}
                        className="px-4 py-2 rounded-lg bg-slate-800 text-white text-sm font-medium hover:bg-slate-700 disabled:opacity-50"
                      >
                        {presetSavingRole === preset.role ? 'Đang lưu…' : 'Lưu preset'}
                      </button>
                    </div>
                  ) : null}
                </details>
              );
            })}
          </div>
        </section>
      </div>
  );
}
