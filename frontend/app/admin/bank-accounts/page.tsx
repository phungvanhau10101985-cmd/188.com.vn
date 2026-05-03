'use client';

import { useState, useEffect, useCallback } from 'react';
import { adminBankAPI, type BankAccountAdmin } from '@/lib/admin-api';
import { DEFAULT_SEPAY_QR_TEMPLATE } from '@/lib/deposit-qr';

type DepositFormState = {
  account_number: string;
  bank_code: string;
  bank_name: string;
  account_holder: string;
  qr_template_url: string;
  branch: string;
  note: string;
  is_active: boolean;
  sort_order: number;
};

const emptyForm = (): DepositFormState => ({
  account_number: '',
  bank_code: '',
  bank_name: '',
  account_holder: '',
  qr_template_url: DEFAULT_SEPAY_QR_TEMPLATE,
  branch: '',
  note: '',
  is_active: true,
  sort_order: 0,
});

export default function AdminBankAccountsPage() {
  const [list, setList] = useState<BankAccountAdmin[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<DepositFormState>(emptyForm);

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 3500);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await adminBankAPI.getAll();
      setList(data);
    } catch {
      showToast('err', 'Lỗi tải danh sách');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openAdd = () => {
    setEditingId(null);
    setForm(emptyForm());
    setShowForm(true);
  };

  const openEdit = (acc: BankAccountAdmin) => {
    setEditingId(acc.id);
    setForm({
      account_number: acc.account_number,
      bank_code: acc.bank_code ?? '',
      bank_name: acc.bank_name,
      account_holder: acc.account_holder,
      qr_template_url: (acc.qr_template_url || DEFAULT_SEPAY_QR_TEMPLATE).trim(),
      branch: acc.branch ?? '',
      note: acc.note ?? '',
      is_active: acc.is_active,
      sort_order: acc.sort_order,
    });
    setShowForm(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.account_number.trim() || !form.bank_code.trim() || !form.bank_name.trim()) {
      showToast('err', 'Vui lòng điền số TK, mã NH và tên ngân hàng hiển thị');
      return;
    }
    if (!form.account_holder.trim()) {
      showToast('err', 'Vui lòng điền chủ tài khoản');
      return;
    }
    const payload = {
      bank_name: form.bank_name.trim(),
      account_number: form.account_number.trim(),
      account_holder: form.account_holder.trim(),
      bank_code: form.bank_code.trim() || null,
      qr_template_url: form.qr_template_url.trim() || null,
      branch: form.branch.trim() || undefined,
      note: form.note.trim() || undefined,
      is_active: form.is_active,
      sort_order: form.sort_order,
    };
    try {
      if (editingId != null) {
        await adminBankAPI.update(editingId, payload);
        showToast('ok', 'Đã lưu cấu hình');
      } else {
        await adminBankAPI.create(payload);
        showToast('ok', 'Đã thêm cấu hình nạp tiền');
      }
      setShowForm(false);
      load();
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Lỗi lưu');
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Xóa cấu hình tài khoản này?')) return;
    try {
      await adminBankAPI.delete(id);
      showToast('ok', 'Đã xóa');
      load();
    } catch {
      showToast('err', 'Không xóa được');
    }
  };

  return (
      <div className="p-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Cấu hình nạp tiền / đặt cọc</h1>
        <p className="text-gray-600 mb-6 max-w-3xl">
          Quản lý tài khoản nhận tiền và URL mẫu QR (SePay, VietQR…). Chỉ tài khoản đang bật mới hiện cho khách khi
          thanh toán cọc.
        </p>
        <button
          type="button"
          onClick={openAdd}
          className="mb-4 px-4 py-2.5 bg-slate-900 text-white rounded-lg hover:bg-slate-800 text-sm font-medium"
        >
          + Thêm cấu hình
        </button>

        {loading ? (
          <p className="text-gray-500">Đang tải...</p>
        ) : list.length === 0 ? (
          <p className="text-gray-500">Chưa có cấu hình nào.</p>
        ) : (
          <div className="border border-gray-200 rounded-xl overflow-hidden bg-white">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left py-3 px-4 font-semibold">Ngân hàng</th>
                  <th className="text-left py-3 px-4 font-semibold">Mã NH</th>
                  <th className="text-left py-3 px-4 font-semibold">Số TK</th>
                  <th className="text-left py-3 px-4 font-semibold">Chủ TK</th>
                  <th className="text-left py-3 px-4 font-semibold">QR mẫu</th>
                  <th className="text-left py-3 px-4 font-semibold">Trạng thái</th>
                  <th className="text-right py-3 px-4 font-semibold">Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {list.map((acc) => (
                  <tr key={acc.id} className="border-t border-gray-100">
                    <td className="py-3 px-4">{acc.bank_name}</td>
                    <td className="py-3 px-4 font-mono text-xs">{acc.bank_code || '—'}</td>
                    <td className="py-3 px-4 font-mono">{acc.account_number}</td>
                    <td className="py-3 px-4">{acc.account_holder}</td>
                    <td className="py-3 px-4 max-w-[200px] truncate text-xs text-gray-600" title={acc.qr_template_url || ''}>
                      {acc.qr_template_url ? 'Có' : '—'}
                    </td>
                    <td className="py-3 px-4">{acc.is_active ? 'Đang dùng' : 'Tắt'}</td>
                    <td className="py-3 px-4 text-right">
                      <button type="button" onClick={() => openEdit(acc)} className="text-blue-600 hover:underline mr-3">
                        Sửa
                      </button>
                      <button type="button" onClick={() => handleDelete(acc.id)} className="text-red-600 hover:underline">
                        Xóa
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {showForm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" role="dialog" aria-modal="true" aria-labelledby="deposit-config-title">
            <div className="bg-white rounded-2xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto">
              <div className="sticky top-0 bg-white border-b border-gray-100 px-6 py-4 flex items-start justify-between gap-4">
                <div>
                  <h2 id="deposit-config-title" className="text-lg font-bold text-gray-900">
                    {editingId != null ? 'Sửa cấu hình' : 'Thêm cấu hình nạp tiền'}
                  </h2>
                  <p className="text-sm text-gray-500 mt-1">Nhập số tài khoản nhận tiền và thông tin ngân hàng.</p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="p-2 rounded-lg text-gray-500 hover:bg-gray-100"
                  aria-label="Đóng"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-800 mb-1">
                    Số tài khoản <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    value={form.account_number}
                    onChange={(e) => setForm((f) => ({ ...f, account_number: e.target.value }))}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-gray-900 focus:ring-2 focus:ring-orange-500/30 focus:border-orange-500"
                    placeholder="107000958284"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-800 mb-1">
                    Mã ngân hàng <span className="text-red-500">*</span> <span className="text-gray-500 font-normal">(MB, VCB, ICB…)</span>
                  </label>
                  <input
                    type="text"
                    required
                    value={form.bank_code}
                    onChange={(e) => setForm((f) => ({ ...f, bank_code: e.target.value.trim() }))}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-gray-900 focus:ring-2 focus:ring-orange-500/30 focus:border-orange-500"
                    placeholder="ICB"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-800 mb-1">
                    Tên ngân hàng hiển thị <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    value={form.bank_name}
                    onChange={(e) => setForm((f) => ({ ...f, bank_name: e.target.value }))}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-gray-900 focus:ring-2 focus:ring-orange-500/30 focus:border-orange-500"
                    placeholder="VietinBank"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-800 mb-1">Chủ tài khoản <span className="text-red-500">*</span></label>
                  <input
                    type="text"
                    required
                    value={form.account_holder}
                    onChange={(e) => setForm((f) => ({ ...f, account_holder: e.target.value }))}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-gray-900 focus:ring-2 focus:ring-orange-500/30 focus:border-orange-500"
                    placeholder="PHUNG VAN HAU"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-800 mb-1">URL mẫu QR</label>
                  <textarea
                    value={form.qr_template_url}
                    onChange={(e) => setForm((f) => ({ ...f, qr_template_url: e.target.value }))}
                    rows={3}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm text-gray-900 font-mono focus:ring-2 focus:ring-orange-500/30 focus:border-orange-500"
                    placeholder={DEFAULT_SEPAY_QR_TEMPLATE}
                  />
                  <p className="text-xs text-gray-500 mt-1.5">
                    Placeholder: <code className="bg-gray-100 px-1 rounded">{'{bank_acc}'}</code>,{' '}
                    <code className="bg-gray-100 px-1 rounded">{'{bank_id}'}</code>,{' '}
                    <code className="bg-gray-100 px-1 rounded">{'{amount}'}</code>,{' '}
                    <code className="bg-gray-100 px-1 rounded">{'{des}'}</code> (SePay / tuỳ chỉnh).
                  </p>
                </div>

                <details className="text-sm">
                  <summary className="cursor-pointer text-gray-600 hover:text-gray-900">Thêm chi nhánh / ghi chú / thứ tự</summary>
                  <div className="mt-3 space-y-3 pl-1">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Chi nhánh</label>
                      <input
                        type="text"
                        value={form.branch}
                        onChange={(e) => setForm((f) => ({ ...f, branch: e.target.value }))}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-gray-900"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Ghi chú nội bộ</label>
                      <input
                        type="text"
                        value={form.note}
                        onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-gray-900"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Thứ tự hiển thị</label>
                      <input
                        type="number"
                        value={form.sort_order}
                        onChange={(e) => setForm((f) => ({ ...f, sort_order: Number(e.target.value) || 0 }))}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-gray-900"
                      />
                    </div>
                  </div>
                </details>

                <label className="flex items-center gap-2 cursor-pointer pt-1">
                  <input
                    type="checkbox"
                    checked={form.is_active}
                    onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
                    className="rounded border-gray-300 text-orange-600 focus:ring-orange-500"
                  />
                  <span className="text-sm text-gray-800">Đang sử dụng (hiện khi nạp tiền)</span>
                </label>

                <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
                  <button
                    type="button"
                    onClick={() => setShowForm(false)}
                    className="px-5 py-2.5 rounded-lg border border-gray-300 text-gray-800 bg-white hover:bg-gray-50 text-sm font-medium"
                  >
                    Hủy
                  </button>
                  <button type="submit" className="px-5 py-2.5 rounded-lg bg-slate-900 text-white hover:bg-slate-800 text-sm font-medium">
                    Lưu
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {toast && (
          <div
            className={`fixed bottom-4 right-4 px-4 py-2 rounded-lg shadow-lg text-white text-sm z-[60] ${
              toast.type === 'ok' ? 'bg-green-600' : 'bg-red-600'
            }`}
            role="status"
          >
            {toast.msg}
          </div>
        )}
      </div>
  );
}
