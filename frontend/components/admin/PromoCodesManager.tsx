'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  adminPromotionsAPI,
  AdminPromotionCode,
  AdminPromotionCodeInput,
} from '@/lib/admin-api';

const AUTO_GRANT_OPTIONS: { value: string; label: string }[] = [
  { value: 'none', label: 'Không tự động' },
  { value: 'signup', label: 'Đăng ký tài khoản' },
  { value: 'first_delivered', label: 'Giao hàng lần đầu' },
  { value: 'comeback', label: 'Khách quay lại' },
  { value: 'cart_abandon', label: 'Bỏ giỏ hàng' },
];

const EMPTY_FORM: AdminPromotionCodeInput = {
  code: '',
  name: '',
  description: '',
  discount_percent: 10,
  max_discount_amount: 100000,
  first_order_only: false,
  stack_with_birthday: false,
  stack_with_loyalty: true,
  is_active: true,
  usage_limit: null,
  per_user_limit: 1,
  eligible_within_days: null,
  grant_valid_days: 7,
  requires_wallet_grant: true,
  auto_grant_trigger: 'none',
  valid_from: null,
  valid_to: null,
};

function formatMoney(value?: number | null) {
  if (value == null) return '—';
  return new Intl.NumberFormat('vi-VN').format(value) + ' đ';
}

function triggerLabel(value: string) {
  return AUTO_GRANT_OPTIONS.find((o) => o.value === value)?.label || value;
}

function toForm(promo: AdminPromotionCode): AdminPromotionCodeInput {
  return {
    code: promo.code,
    name: promo.name,
    description: promo.description || '',
    discount_percent: promo.discount_percent,
    max_discount_amount: promo.max_discount_amount,
    first_order_only: promo.first_order_only,
    stack_with_birthday: promo.stack_with_birthday,
    stack_with_loyalty: promo.stack_with_loyalty,
    is_active: promo.is_active,
    usage_limit: promo.usage_limit,
    per_user_limit: promo.per_user_limit,
    eligible_within_days: promo.eligible_within_days,
    grant_valid_days: promo.grant_valid_days,
    requires_wallet_grant: promo.requires_wallet_grant,
    auto_grant_trigger: promo.auto_grant_trigger,
    valid_from: promo.valid_from,
    valid_to: promo.valid_to,
  };
}

function toDatetimeLocalValue(iso?: string | null) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fromDatetimeLocalValue(value: string) {
  if (!value.trim()) return null;
  return new Date(value).toISOString();
}

export default function PromoCodesManager() {
  const [rows, setRows] = useState<AdminPromotionCode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [editing, setEditing] = useState<AdminPromotionCodeInput | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isSystemTemplate, setIsSystemTemplate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [togglingId, setTogglingId] = useState<number | null>(null);

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 3000);
  };

  const fetchRows = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await adminPromotionsAPI.listPromotions();
      setRows(data.items);
    } catch {
      setError('Không tải được danh sách mã khuyến mãi.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchRows();
  }, [fetchRows]);

  const startCreate = () => {
    setEditing({ ...EMPTY_FORM });
    setEditingId(null);
    setIsCreating(true);
    setIsSystemTemplate(false);
  };

  const startEdit = (promo: AdminPromotionCode) => {
    setEditing(toForm(promo));
    setEditingId(promo.id);
    setIsCreating(false);
    setIsSystemTemplate(promo.is_system_template);
  };

  const closeModal = () => {
    setEditing(null);
    setEditingId(null);
    setIsCreating(false);
    setIsSystemTemplate(false);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editing) return;
    setSaving(true);
    try {
      if (isCreating) {
        await adminPromotionsAPI.createPromotion({
          ...editing,
          code: editing.code.trim().toUpperCase(),
          name: editing.name.trim(),
          description: editing.description?.trim() || undefined,
        });
        showToast('ok', 'Đã tạo mã khuyến mãi mới');
      } else if (editingId != null) {
        const { code: _code, ...payload } = editing;
        await adminPromotionsAPI.updatePromotion(editingId, {
          ...payload,
          name: editing.name.trim(),
          description: editing.description?.trim() || undefined,
        });
        showToast('ok', 'Đã cập nhật mã khuyến mãi');
      }
      closeModal();
      await fetchRows();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Lưu thất bại';
      showToast('err', msg);
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (promo: AdminPromotionCode) => {
    setTogglingId(promo.id);
    try {
      await adminPromotionsAPI.updatePromotion(promo.id, { is_active: !promo.is_active });
      showToast('ok', promo.is_active ? 'Đã tắt mã' : 'Đã bật mã');
      await fetchRows();
    } catch {
      showToast('err', 'Không thể đổi trạng thái mã');
    } finally {
      setTogglingId(null);
    }
  };

  return (
    <section className="mb-10">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <h2 className="text-lg font-bold text-gray-900">Quản lý mã khuyến mãi</h2>
          <p className="text-sm text-gray-600 mt-1">
            Xem, sửa, bật/tắt và tạo mã mới. Mã chỉ dùng được khi đã tặng vào ví khách (trừ khi tắt yêu cầu ví).
          </p>
        </div>
        <button
          type="button"
          onClick={startCreate}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm"
        >
          + Tạo mã mới
        </button>
      </div>

      {error ? (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}{' '}
          <button type="button" onClick={() => void fetchRows()} className="underline font-medium">
            Thử lại
          </button>
        </div>
      ) : null}

      {toast ? (
        <div
          className={`mb-4 rounded-lg px-4 py-3 text-sm ${
            toast.type === 'ok'
              ? 'bg-green-50 text-green-800 border border-green-200'
              : 'bg-red-50 text-red-800 border border-red-200'
          }`}
        >
          {toast.msg}
        </div>
      ) : null}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-gray-500">Đang tải danh sách mã...</div>
        ) : rows.length === 0 ? (
          <div className="p-12 text-center text-gray-500">
            Chưa có mã khuyến mãi.{' '}
            <button type="button" onClick={startCreate} className="text-blue-600 underline font-medium">
              Tạo mã đầu tiên
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-gray-50 border-b border-gray-200 text-gray-700">
                <tr>
                  <th className="px-4 py-3 font-semibold">Mã</th>
                  <th className="px-4 py-3 font-semibold">Tên</th>
                  <th className="px-4 py-3 font-semibold">Giảm</th>
                  <th className="px-4 py-3 font-semibold">Tối đa</th>
                  <th className="px-4 py-3 font-semibold">Tự động tặng</th>
                  <th className="px-4 py-3 font-semibold">Thống kê</th>
                  <th className="px-4 py-3 font-semibold">Trạng thái</th>
                  <th className="px-4 py-3 font-semibold text-right">Hành động</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((promo) => (
                  <tr key={promo.id} className="border-b border-gray-100 hover:bg-gray-50/80">
                    <td className="px-4 py-3">
                      <div className="font-mono font-semibold text-gray-900">{promo.code}</div>
                      {promo.is_system_template ? (
                        <span className="inline-block mt-1 text-[11px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-700">
                          Hệ thống
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-900">{promo.name}</div>
                      {promo.description ? (
                        <div className="text-xs text-gray-500 mt-0.5 max-w-xs truncate" title={promo.description}>
                          {promo.description}
                        </div>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 text-green-700 font-semibold">{promo.discount_percent}%</td>
                    <td className="px-4 py-3">{formatMoney(promo.max_discount_amount)}</td>
                    <td className="px-4 py-3 text-gray-700">{triggerLabel(promo.auto_grant_trigger)}</td>
                    <td className="px-4 py-3 text-gray-600">
                      {promo.grants_count} tặng · {promo.usages_count} dùng
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        disabled={togglingId === promo.id}
                        onClick={() => void toggleActive(promo)}
                        className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${
                          promo.is_active
                            ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        } disabled:opacity-50`}
                        aria-label={promo.is_active ? 'Tắt mã' : 'Bật mã'}
                      >
                        {togglingId === promo.id ? '...' : promo.is_active ? 'Đang bật' : 'Đã tắt'}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => startEdit(promo)}
                        className="text-blue-600 hover:underline font-medium"
                      >
                        Sửa
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editing ? (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="promo-modal-title"
        >
          <div className="bg-white rounded-xl shadow-lg w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-gray-100">
              <h3 id="promo-modal-title" className="text-xl font-bold text-gray-900">
                {isCreating ? 'Tạo mã khuyến mãi mới' : `Sửa mã ${editing.code}`}
              </h3>
              {isSystemTemplate && !isCreating ? (
                <p className="text-xs text-amber-700 mt-2 bg-amber-50 rounded-lg px-3 py-2">
                  Mã hệ thống — deploy có thể đồng bộ lại một số trường mặc định từ template.
                </p>
              ) : null}
            </div>

            <form onSubmit={handleSave} className="p-6 space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Mã</label>
                  <input
                    type="text"
                    required
                    disabled={!isCreating}
                    value={editing.code}
                    onChange={(e) =>
                      setEditing((f) => f && { ...f, code: e.target.value.toUpperCase() })
                    }
                    placeholder="VD: SUMMER10"
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono disabled:bg-gray-50"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Tên chương trình</label>
                  <input
                    type="text"
                    required
                    value={editing.name}
                    onChange={(e) => setEditing((f) => f && { ...f, name: e.target.value })}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Mô tả (hiển thị khách)</label>
                <textarea
                  rows={2}
                  value={editing.description || ''}
                  onChange={(e) => setEditing((f) => f && { ...f, description: e.target.value })}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Giảm (%)</label>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={0.5}
                    required
                    value={editing.discount_percent}
                    onChange={(e) =>
                      setEditing((f) => f && { ...f, discount_percent: Number(e.target.value) || 0 })
                    }
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Giảm tối đa (đ)</label>
                  <input
                    type="number"
                    min={0}
                    step={1000}
                    value={editing.max_discount_amount ?? ''}
                    onChange={(e) =>
                      setEditing((f) => f && {
                        ...f,
                        max_discount_amount: e.target.value === '' ? null : Number(e.target.value),
                      })
                    }
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Hết hạn sau tặng (ngày)</label>
                  <input
                    type="number"
                    min={1}
                    max={365}
                    value={editing.grant_valid_days ?? ''}
                    onChange={(e) =>
                      setEditing((f) => f && {
                        ...f,
                        grant_valid_days: e.target.value === '' ? null : Number(e.target.value),
                      })
                    }
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Giới hạn / khách</label>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={editing.per_user_limit ?? 1}
                    onChange={(e) =>
                      setEditing((f) => f && { ...f, per_user_limit: Number(e.target.value) || 1 })
                    }
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Tổng lượt dùng</label>
                  <input
                    type="number"
                    min={1}
                    value={editing.usage_limit ?? ''}
                    onChange={(e) =>
                      setEditing((f) => f && {
                        ...f,
                        usage_limit: e.target.value === '' ? null : Number(e.target.value),
                      })
                    }
                    placeholder="Không giới hạn"
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Tự động tặng mã</label>
                <select
                  value={editing.auto_grant_trigger || 'none'}
                  onChange={(e) =>
                    setEditing((f) => f && { ...f, auto_grant_trigger: e.target.value })
                  }
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                >
                  {AUTO_GRANT_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Hiệu lực từ</label>
                  <input
                    type="datetime-local"
                    value={toDatetimeLocalValue(editing.valid_from)}
                    onChange={(e) =>
                      setEditing((f) => f && { ...f, valid_from: fromDatetimeLocalValue(e.target.value) })
                    }
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Hiệu lực đến</label>
                  <input
                    type="datetime-local"
                    value={toDatetimeLocalValue(editing.valid_to)}
                    onChange={(e) =>
                      setEditing((f) => f && { ...f, valid_to: fromDatetimeLocalValue(e.target.value) })
                    }
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                </div>
              </div>

              <div className="rounded-xl border border-gray-100 bg-gray-50 p-4 space-y-2">
                <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={editing.is_active}
                    onChange={(e) => setEditing((f) => f && { ...f, is_active: e.target.checked })}
                  />
                  Bật mã (khách có thể dùng khi đủ điều kiện)
                </label>
                <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={editing.requires_wallet_grant}
                    onChange={(e) =>
                      setEditing((f) => f && { ...f, requires_wallet_grant: e.target.checked })
                    }
                  />
                  Yêu cầu mã trong ví khách
                </label>
                <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={editing.first_order_only}
                    onChange={(e) =>
                      setEditing((f) => f && { ...f, first_order_only: e.target.checked })
                    }
                  />
                  Chỉ áp dụng đơn đầu tiên
                </label>
                <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={editing.stack_with_loyalty}
                    onChange={(e) =>
                      setEditing((f) => f && { ...f, stack_with_loyalty: e.target.checked })
                    }
                  />
                  Cộng dồn với giảm hạng thành viên
                </label>
                <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={editing.stack_with_birthday}
                    onChange={(e) =>
                      setEditing((f) => f && { ...f, stack_with_birthday: e.target.checked })
                    }
                  />
                  Cộng dồn với giảm sinh nhật
                </label>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={closeModal}
                  className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg text-sm"
                >
                  Huỷ
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium disabled:opacity-50"
                >
                  {saving ? 'Đang lưu...' : 'Lưu mã'}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </section>
  );
}
