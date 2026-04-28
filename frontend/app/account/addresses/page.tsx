'use client';

import { useState, useEffect } from 'react';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/features/auth/hooks/useAuth';
import type { UserAddress, AddressCreateInput } from '@/types/api';
import { VIETNAM_PROVINCES } from '@/lib/vietnam-provinces';
import { useToast } from '@/components/ToastProvider';

function formatAddressLine(addr: UserAddress): string {
  const parts = [addr.street_address];
  if (addr.ward) parts.push(addr.ward);
  if (addr.district) parts.push(addr.district);
  if (addr.province) parts.push(addr.province);
  return parts.join(', ');
}

export default function AddressesPage() {
  const { user } = useAuth();
  const [addresses, setAddresses] = useState<UserAddress[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const { pushToast } = useToast();
  const [form, setForm] = useState<AddressCreateInput & { id?: number }>({
    full_name: user?.full_name ?? '',
    phone: user?.phone ?? '',
    province: '',
    district: '',
    ward: '',
    street_address: '',
    is_default: false,
  });

  const loadAddresses = async () => {
    try {
      const list = await apiClient.getAddresses();
      setAddresses(list);
    } catch (e) {
      console.error(e);
      setAddresses([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAddresses();
  }, []);

  useEffect(() => {
    if (user) {
      setForm((f) => ({
        ...f,
        full_name: (f.full_name || user.full_name) ?? '',
        phone: (f.phone || user.phone) ?? '',
      }));
    }
  }, [user]);

  const openAdd = () => {
    setEditingId(null);
    setForm({
      full_name: user?.full_name ?? '',
      phone: user?.phone ?? '',
      province: '',
      district: '',
      ward: '',
      street_address: '',
      is_default: addresses.length === 0,
    });
    setShowForm(true);
  };

  const openEdit = (addr: UserAddress) => {
    setEditingId(addr.id);
    setForm({
      full_name: addr.full_name,
      phone: addr.phone,
      province: addr.province ?? '',
      district: addr.district ?? '',
      ward: addr.ward ?? '',
      street_address: addr.street_address,
      is_default: addr.is_default,
      id: addr.id,
    });
    setShowForm(true);
  };

  const closeForm = () => {
    setShowForm(false);
    setEditingId(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (editingId != null) {
        await apiClient.updateAddress(editingId, {
          full_name: form.full_name,
          phone: form.phone,
          province: form.province || undefined,
          district: form.district || undefined,
          ward: form.ward || undefined,
          street_address: form.street_address,
          is_default: form.is_default,
        });
      } else {
        await apiClient.createAddress({
          full_name: form.full_name,
          phone: form.phone,
          province: form.province || undefined,
          district: form.district || undefined,
          ward: form.ward || undefined,
          street_address: form.street_address,
          is_default: form.is_default,
        });
      }
      await loadAddresses();
      closeForm();
    } catch (err: any) {
      pushToast({ title: 'Không thể lưu địa chỉ', description: err?.message || 'Vui lòng thử lại', variant: 'error', durationMs: 3000 });
    } finally {
      setSaving(false);
    }
  };

  const handleSetDefault = async (id: number) => {
    try {
      await apiClient.setDefaultAddress(id);
      await loadAddresses();
    } catch (err: any) {
      pushToast({ title: 'Không thể đặt mặc định', description: err?.message || 'Vui lòng thử lại', variant: 'error', durationMs: 3000 });
    }
  };

  const handleDelete = async (id: number) => {
    setPendingDeleteId(id);
    setShowDeleteConfirm(true);
  };

  const confirmDelete = async () => {
    if (pendingDeleteId == null) return;
    try {
      await apiClient.deleteAddress(pendingDeleteId);
      await loadAddresses();
      pushToast({ title: 'Đã xóa địa chỉ', variant: 'success', durationMs: 2500 });
    } catch (err: any) {
      pushToast({ title: 'Không thể xóa địa chỉ', description: err?.message || 'Vui lòng thử lại', variant: 'error', durationMs: 3000 });
    } finally {
      setShowDeleteConfirm(false);
      setPendingDeleteId(null);
    }
  };

  if (loading) {
    return (
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-gray-200 rounded w-1/3" />
          <div className="h-24 bg-gray-100 rounded" />
          <div className="h-24 bg-gray-100 rounded" />
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
      <div className="p-6 border-b border-gray-100 flex flex-wrap items-center justify-between gap-4">
        <h2 className="text-xl font-bold text-gray-900">Sổ địa chỉ</h2>
        <button
          type="button"
          onClick={openAdd}
          className="inline-flex items-center px-4 py-2 bg-[#ea580c] text-white font-medium rounded-lg hover:bg-[#c2410c] transition-colors"
        >
          + Thêm địa chỉ
        </button>
      </div>

      <div className="p-6">
        {addresses.length === 0 && !showForm ? (
          <p className="text-gray-500 text-center py-8">Chưa có địa chỉ nào. Nhấn &quot;Thêm địa chỉ&quot; để thêm.</p>
        ) : (
          <ul className="space-y-4">
            {addresses.map((addr) => (
              <li
                key={addr.id}
                className="border border-gray-200 rounded-xl p-4 flex flex-wrap items-start justify-between gap-4"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-gray-900">{addr.full_name}</span>
                    <span className="text-gray-500">{addr.phone}</span>
                    {addr.is_default && (
                      <span className="px-2 py-0.5 text-xs font-medium bg-blue-100 text-blue-800 rounded">
                        Mặc định
                      </span>
                    )}
                  </div>
                  <p className="text-gray-600 mt-1">{formatAddressLine(addr)}</p>
                </div>
                <div className="flex items-center gap-2">
                  {!addr.is_default && (
                    <button
                      type="button"
                      onClick={() => handleSetDefault(addr.id)}
                      className="text-sm text-blue-600 hover:text-blue-700 font-medium"
                    >
                      Đặt mặc định
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => openEdit(addr)}
                    className="text-sm text-gray-600 hover:text-gray-900"
                  >
                    Sửa
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(addr.id)}
                    className="text-sm text-red-600 hover:text-red-700"
                  >
                    Xóa
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        {showForm && (
          <div className="mt-8 p-6 border border-gray-200 rounded-xl bg-gray-50">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              {editingId != null ? 'Chỉnh sửa địa chỉ' : 'Thêm địa chỉ mới'}
            </h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Họ và tên *</label>
                  <input
                    type="text"
                    required
                    value={form.full_name}
                    onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="Nguyễn Văn A"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Số điện thoại *</label>
                  <input
                    type="tel"
                    required
                    value={form.phone}
                    onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="0912345678"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Tỉnh / Thành phố</label>
                <select
                  value={form.province}
                  onChange={(e) => setForm((f) => ({ ...f, province: e.target.value }))}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="">— Chọn tỉnh/thành phố —</option>
                  {VIETNAM_PROVINCES.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Quận / Huyện</label>
                  <input
                    type="text"
                    value={form.district}
                    onChange={(e) => setForm((f) => ({ ...f, district: e.target.value }))}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="Quận 1"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Phường / Xã</label>
                  <input
                    type="text"
                    value={form.ward}
                    onChange={(e) => setForm((f) => ({ ...f, ward: e.target.value }))}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="Phường Bến Nghé"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Địa chỉ cụ thể *</label>
                <input
                  type="text"
                  required
                  value={form.street_address}
                  onChange={(e) => setForm((f) => ({ ...f, street_address: e.target.value }))}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Số nhà, tên đường, thôn/xóm..."
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="is_default"
                  checked={form.is_default}
                  onChange={(e) => setForm((f) => ({ ...f, is_default: e.target.checked }))}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <label htmlFor="is_default" className="text-sm text-gray-700">Đặt làm địa chỉ mặc định</label>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="submit"
                  disabled={saving}
                  className="px-4 py-2 bg-[#ea580c] text-white font-medium rounded-lg hover:bg-[#c2410c] disabled:opacity-70"
                >
                  {saving ? 'Đang lưu...' : 'Lưu địa chỉ'}
                </button>
                <button
                  type="button"
                  onClick={closeForm}
                  className="px-4 py-2 border border-gray-300 text-gray-700 font-medium rounded-lg hover:bg-gray-50"
                >
                  Hủy
                </button>
              </div>
            </form>
          </div>
        )}
      </div>

      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowDeleteConfirm(false)}>
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-gray-900 mb-2">Xóa địa chỉ</h3>
            <p className="text-gray-600 text-sm mb-6">Bạn chắc chắn muốn xóa địa chỉ này?</p>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowDeleteConfirm(false)} className="px-4 py-2 border rounded-lg hover:bg-gray-50">
                Hủy
              </button>
              <button onClick={confirmDelete} className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700">
                Xóa
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
