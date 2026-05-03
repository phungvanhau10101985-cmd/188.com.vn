'use client';

import { useState, useEffect, useCallback } from 'react';
import { adminLoyaltyAPI, AdminLoyaltyTier } from '@/lib/admin-api';

export default function AdminLoyaltyPage() {
  const [tiers, setTiers] = useState<AdminLoyaltyTier[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<AdminLoyaltyTier | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 3000);
  };

  const fetchTiers = useCallback(async () => {
    setLoading(true);
    try {
      const data = await adminLoyaltyAPI.getTiers();
      setTiers(data);
    } catch (err) {
      showToast('err', 'Lỗi tải danh sách hạng thành viên');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchTiers();
  }, [fetchTiers]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editing) return;

    try {
      if (isCreating) {
        await adminLoyaltyAPI.createTier(editing);
        showToast('ok', 'Đã tạo hạng thành viên mới');
      } else {
        await adminLoyaltyAPI.updateTier(editing.id, editing);
        showToast('ok', 'Đã cập nhật hạng thành viên');
      }
      setEditing(null);
      setIsCreating(false);
      fetchTiers();
    } catch (err) {
      showToast('err', 'Lỗi lưu dữ liệu');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Bạn có chắc chắn muốn xóa hạng thành viên này?')) return;
    try {
      await adminLoyaltyAPI.deleteTier(id);
      showToast('ok', 'Đã xóa hạng thành viên');
      fetchTiers();
    } catch (err) {
      showToast('err', 'Lỗi xóa dữ liệu');
    }
  };

  const startEdit = (tier: AdminLoyaltyTier) => {
    setEditing({ ...tier });
    setIsCreating(false);
  };

  const startCreate = () => {
    setEditing({
      id: 0,
      name: '',
      min_spend: 0,
      discount_percent: 0,
      description: '',
    });
    setIsCreating(true);
  };

  return (
      <div className="p-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Cấu hình hạng thành viên</h1>

        <div className="mb-6">
          <button
            onClick={startCreate}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
          >
            + Thêm hạng mới
          </button>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {loading ? (
            <div className="p-12 text-center text-gray-500">Đang tải...</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="bg-gray-50 border-b border-gray-200 text-gray-700 uppercase">
                  <tr>
                    <th className="px-6 py-3">Tên hạng</th>
                    <th className="px-6 py-3">Chi tiêu tối thiểu</th>
                    <th className="px-6 py-3">Giảm giá (%)</th>
                    <th className="px-6 py-3">Mô tả</th>
                    <th className="px-6 py-3 text-right">Hành động</th>
                  </tr>
                </thead>
                <tbody>
                  {tiers.map((tier) => (
                    <tr key={tier.id} className="border-b hover:bg-gray-50">
                      <td className="px-6 py-4 font-bold">{tier.name}</td>
                      <td className="px-6 py-4">
                        {new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(tier.min_spend)}
                      </td>
                      <td className="px-6 py-4 text-green-600 font-bold">{tier.discount_percent}%</td>
                      <td className="px-6 py-4 max-w-xs truncate" title={tier.description}>
                        {tier.description}
                      </td>
                      <td className="px-6 py-4 text-right space-x-2">
                        <button
                          onClick={() => startEdit(tier)}
                          className="text-blue-600 hover:underline"
                        >
                          Sửa
                        </button>
                        <button
                          onClick={() => handleDelete(tier.id)}
                          className="text-red-600 hover:underline"
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
        </div>

        {/* Modal Edit/Create */}
        {editing && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl shadow-lg p-6 w-full max-w-lg">
              <h2 className="text-xl font-bold mb-4">
                {isCreating ? 'Thêm hạng mới' : 'Chỉnh sửa hạng'}
              </h2>
              <form onSubmit={handleSave} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Tên hạng</label>
                  <input
                    type="text"
                    required
                    value={editing.name}
                    onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Chi tiêu tối thiểu (VND)</label>
                    <input
                      type="number"
                      required
                      min="0"
                      value={editing.min_spend}
                      onChange={(e) => setEditing({ ...editing, min_spend: Number(e.target.value) })}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Giảm giá (%)</label>
                    <input
                      type="number"
                      required
                      min="0"
                      max="100"
                      step="0.1"
                      value={editing.discount_percent}
                      onChange={(e) => setEditing({ ...editing, discount_percent: Number(e.target.value) })}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Mô tả ưu đãi</label>
                  <textarea
                    rows={3}
                    value={editing.description}
                    onChange={(e) => setEditing({ ...editing, description: e.target.value })}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2"
                  />
                </div>
                <div className="flex justify-end gap-2 mt-6">
                  <button
                    type="button"
                    onClick={() => setEditing(null)}
                    className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg"
                  >
                    Hủy
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                  >
                    Lưu
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

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
  );
}
