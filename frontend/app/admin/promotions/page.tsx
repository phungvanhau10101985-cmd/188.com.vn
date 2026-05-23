'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminPromotionsAPI, AdminWelcomePromoSettings } from '@/lib/admin-api';

export default function AdminPromotionsPage() {
  const [settings, setSettings] = useState<AdminWelcomePromoSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [form, setForm] = useState({
    name: '',
    description: '',
    discount_percent: 10,
    max_discount_amount: 200000,
    eligible_within_days: 7,
    unlimited_days: false,
    is_active: true,
  });

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 3000);
  };

  const applySettings = useCallback((data: AdminWelcomePromoSettings) => {
    setSettings(data);
    setForm({
      name: data.name,
      description: data.description || '',
      discount_percent: data.discount_percent,
      max_discount_amount: data.max_discount_amount,
      eligible_within_days: data.eligible_within_days ?? 7,
      unlimited_days: !data.show_days_remaining,
      is_active: data.is_active,
    });
  }, []);

  const fetchSettings = useCallback(async () => {
    setLoading(true);
    try {
      const data = await adminPromotionsAPI.getWelcomeSettings();
      applySettings(data);
    } catch {
      showToast('err', 'Không tải được cấu hình khuyến mãi');
    } finally {
      setLoading(false);
    }
  }, [applySettings]);

  useEffect(() => {
    void fetchSettings();
  }, [fetchSettings]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const updated = await adminPromotionsAPI.updateWelcomeSettings({
        name: form.name.trim() || undefined,
        description: form.description.trim() || undefined,
        discount_percent: form.discount_percent,
        max_discount_amount: form.max_discount_amount,
        eligible_within_days: form.unlimited_days ? 0 : form.eligible_within_days,
        is_active: form.is_active,
      });
      applySettings(updated);
      showToast('ok', 'Đã lưu cấu hình WELCOME188');
    } catch {
      showToast('err', 'Lưu thất bại');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Khuyến mãi</h1>
      <p className="text-sm text-gray-600 mb-6">
        Cấu hình chương trình chào mừng khách mới (mã WELCOME188). Khách thấy số ngày còn lại tại trang{' '}
        <span className="font-mono text-gray-800">/account/khuyen-mai</span> và giỏ hàng.
      </p>

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

      {loading ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-500">
          Đang tải...
        </div>
      ) : (
        <form onSubmit={handleSave} className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Mã (cố định)</label>
            <input
              type="text"
              value={settings?.code || 'WELCOME188'}
              disabled
              className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm font-mono"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Tên chương trình</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Mô tả (hiển thị khách)</label>
            <textarea
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              rows={3}
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
                value={form.discount_percent}
                onChange={(e) =>
                  setForm((f) => ({ ...f, discount_percent: Number(e.target.value) || 0 }))
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
                value={form.max_discount_amount}
                onChange={(e) =>
                  setForm((f) => ({ ...f, max_discount_amount: Number(e.target.value) || 0 }))
                }
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
              />
            </div>
          </div>

          <div className="rounded-xl border border-emerald-100 bg-emerald-50/60 p-4 space-y-3">
            <p className="text-sm font-semibold text-emerald-900">Thời hạn sử dụng mã</p>
            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
              <input
                type="checkbox"
                checked={form.unlimited_days}
                onChange={(e) => setForm((f) => ({ ...f, unlimited_days: e.target.checked }))}
              />
              Không giới hạn số ngày (ẩn countdown trên UI)
            </label>
            {!form.unlimited_days ? (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Số ngày kể từ đăng ký
                </label>
                <input
                  type="number"
                  min={1}
                  max={365}
                  value={form.eligible_within_days}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      eligible_within_days: Math.max(1, Number(e.target.value) || 1),
                    }))
                  }
                  className="w-full max-w-xs rounded-lg border border-gray-200 px-3 py-2 text-sm"
                />
                <p className="mt-1 text-xs text-gray-500">
                  Ví dụ: 7 = khách có 7 ngày từ lúc tạo tài khoản để dùng mã trên đơn đầu tiên.
                </p>
              </div>
            ) : null}
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
            />
            Bật chương trình
          </label>

          <button
            type="submit"
            disabled={saving}
            className="px-5 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? 'Đang lưu...' : 'Lưu cấu hình'}
          </button>
        </form>
      )}

      <div className="mt-8 bg-white rounded-xl border border-gray-200 p-6 space-y-3">
        <h2 className="text-lg font-bold text-gray-900">Cron tự động (VPS)</h2>
        <p className="text-sm text-gray-600">
          Cấu hình <strong>một lần</strong> trên server — hệ thống tự tặng mã + gửi email CMSN hàng ngày.
          Cần biến <code className="text-xs bg-gray-100 px-1 rounded">CRON_SECRET</code> trong .env backend.
        </p>
        <pre className="text-xs bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto whitespace-pre-wrap">
{`0 9 * * * curl -sS -H "Authorization: Bearer YOUR_CRON_SECRET" \\
  "https://YOUR_API_HOST/api/v1/promotions/cron/daily-all"`}
        </pre>
        <p className="text-xs text-gray-500">
          Endpoint gộp: CARTSAVE188 + COMEBACK10 + backfill WELCOME + email sinh nhật (7 ngày trước SN).
          WELCOME (đăng ký), THANKYOU (giao hàng lần đầu), CMSN giảm giá — chạy tự động trong app, không cần cron.
        </p>
      </div>

      <div className="mt-8 bg-white rounded-xl border border-gray-200 p-6 space-y-5">
        <div>
          <h2 className="text-lg font-bold text-gray-900">Tặng mã vào ví khách</h2>
          <p className="text-sm text-gray-600 mt-1">
            Mã chỉ hiện trong ví cá nhân của khách — không public cho mọi người.
          </p>
        </div>

        <GrantToUserForm />
        <WelcomeBackfillForm />
        <ComebackSegmentForm />
        <CartAbandonForm />
        <UserGrantHistory />
      </div>
    </div>
  );
}

function GrantToUserForm() {
  const [userId, setUserId] = useState('');
  const [code, setCode] = useState('WELCOME188');
  const [days, setDays] = useState('7');
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const uid = Number(userId);
    if (!uid) return;
    setSaving(true);
    try {
      await adminPromotionsAPI.grantToUser({
        user_id: uid,
        promo_code: code.trim().toUpperCase(),
        expires_in_days: Number(days) || undefined,
        message: message.trim() || undefined,
      });
      setToast(`Đã tặng mã ${code} cho user #${uid}`);
    } catch {
      setToast('Tặng mã thất bại');
    } finally {
      setSaving(false);
      setTimeout(() => setToast(null), 3000);
    }
  };

  return (
    <form onSubmit={submit} className="rounded-xl border border-gray-100 bg-gray-50 p-4 space-y-3">
      <p className="text-sm font-semibold text-gray-800">Tặng 1 khách (theo user ID)</p>
      {toast ? <p className="text-sm text-emerald-700">{toast}</p> : null}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <input
          type="number"
          placeholder="User ID"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
          required
        />
        <select
          value={code}
          onChange={(e) => setCode(e.target.value)}
          className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
        >
          <option value="WELCOME188">WELCOME188 — Chào mừng</option>
          <option value="THANKYOU188">THANKYOU188 — Cảm ơn</option>
          <option value="COMEBACK10">COMEBACK10 — Quay lại</option>
          <option value="CARTSAVE188">CARTSAVE188 — Nhắc giỏ hàng</option>
        </select>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <input
          type="number"
          min={1}
          max={365}
          placeholder="Hết hạn (ngày)"
          value={days}
          onChange={(e) => setDays(e.target.value)}
          className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
        />
        <input
          type="text"
          placeholder="Lời nhắn (tuỳ chọn)"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
        />
      </div>
      <button
        type="submit"
        disabled={saving}
        className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
      >
        {saving ? 'Đang tặng...' : 'Tặng mã'}
      </button>
    </form>
  );
}

function WelcomeBackfillForm() {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [armed, setArmed] = useState(false);

  const run = async () => {
    if (!armed) {
      setArmed(true);
      return;
    }
    setRunning(true);
    setResult(null);
    try {
      const res = await adminPromotionsAPI.backfillWelcome();
      setResult(`Đã tặng ${res.granted} khách, bỏ qua ${res.skipped}.`);
      setArmed(false);
    } catch {
      setResult('Backfill thất bại.');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="rounded-xl border border-amber-100 bg-amber-50 p-4 space-y-3">
      <p className="text-sm font-semibold text-gray-800">Backfill WELCOME (user cũ)</p>
      <p className="text-xs text-gray-600">
        Tự chạy khi deploy (migration). Có thể bấm lại thủ công — chỉ tặng user chưa có đơn và
        chưa từng được tặng/dùng WELCOME188.
      </p>
      {armed ? (
        <p className="text-xs text-amber-800 bg-amber-100 rounded-lg px-3 py-2">
          Thao tác này có thể tặng mã cho nhiều tài khoản. Bấm lần nữa để xác nhận chạy.
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void run()}
          disabled={running}
          className="px-4 py-2 bg-amber-600 text-white rounded-lg text-sm font-medium hover:bg-amber-700 disabled:opacity-50"
        >
          {running ? 'Đang chạy...' : armed ? 'Xác nhận chạy backfill' : 'Chạy backfill WELCOME'}
        </button>
        {armed && !running ? (
          <button
            type="button"
            onClick={() => setArmed(false)}
            className="px-4 py-2 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-white"
          >
            Huỷ
          </button>
        ) : null}
      </div>
      {result ? <p className="text-sm text-gray-700">{result}</p> : null}
    </div>
  );
}

function ComebackSegmentForm() {
  const [days, setDays] = useState('30');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setResult(null);
    try {
      const res = await adminPromotionsAPI.grantComebackSegment(Number(days) || 30);
      setResult(`Đã tặng ${res.granted} khách, bỏ qua ${res.skipped}.`);
    } catch {
      setResult('Chạy chiến dịch thất bại.');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="rounded-xl border border-gray-100 bg-gray-50 p-4 space-y-3">
      <p className="text-sm font-semibold text-gray-800">Chiến dịch quay lại (COMEBACK10)</p>
      <p className="text-xs text-gray-500">
        Tự động tặng cho khách có đơn giao thành công nhưng không mua lại trong X ngày.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="number"
          min={7}
          max={180}
          value={days}
          onChange={(e) => setDays(e.target.value)}
          className="w-28 rounded-lg border border-gray-200 px-3 py-2 text-sm"
        />
        <span className="text-sm text-gray-600">ngày không mua lại</span>
        <button
          type="button"
          onClick={() => void run()}
          disabled={running}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
        >
          {running ? 'Đang chạy...' : 'Chạy tặng mã'}
        </button>
      </div>
      {result ? <p className="text-sm text-gray-700">{result}</p> : null}
    </div>
  );
}

function CartAbandonForm() {
  const [hours, setHours] = useState('24');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setResult(null);
    try {
      const res = await adminPromotionsAPI.runCartAbandon(Number(hours) || 24);
      setResult(`Đã tặng ${res.granted} khách, bỏ qua ${res.skipped}.`);
    } catch {
      setResult('Chạy nhắc giỏ hàng thất bại.');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="rounded-xl border border-gray-100 bg-gray-50 p-4 space-y-3">
      <p className="text-sm font-semibold text-gray-800">Nhắc bỏ giỏ hàng (CARTSAVE188)</p>
      <p className="text-xs text-gray-500">
        Tặng mã cho khách có sản phẩm trong giỏ nhưng không đặt hàng sau X giờ. Đã gộp trong cron{' '}
        <code className="text-xs bg-gray-100 px-1 rounded">/promotions/cron/daily-all</code>.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="number"
          min={6}
          max={168}
          value={hours}
          onChange={(e) => setHours(e.target.value)}
          className="w-28 rounded-lg border border-gray-200 px-3 py-2 text-sm"
        />
        <span className="text-sm text-gray-600">giờ không checkout</span>
        <button
          type="button"
          onClick={() => void run()}
          disabled={running}
          className="px-4 py-2 bg-orange-600 text-white rounded-lg text-sm font-medium hover:bg-orange-700 disabled:opacity-50"
        >
          {running ? 'Đang chạy...' : 'Chạy nhắc giỏ'}
        </button>
      </div>
      {result ? <p className="text-sm text-gray-700">{result}</p> : null}
    </div>
  );
}

function UserGrantHistory() {
  const [userId, setUserId] = useState('');
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<
    Awaited<ReturnType<typeof adminPromotionsAPI.listUserGrants>>
  >([]);

  const load = async () => {
    const uid = Number(userId);
    if (!uid) return;
    setLoading(true);
    try {
      setRows(await adminPromotionsAPI.listUserGrants(uid));
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-gray-100 bg-gray-50 p-4 space-y-3">
      <p className="text-sm font-semibold text-gray-800">Lịch sử mã trong ví (theo user ID)</p>
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="number"
          placeholder="User ID"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          className="w-40 rounded-lg border border-gray-200 px-3 py-2 text-sm"
        />
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="px-4 py-2 bg-gray-800 text-white rounded-lg text-sm font-medium hover:bg-gray-900 disabled:opacity-50"
        >
          {loading ? 'Đang tải...' : 'Xem lịch sử'}
        </button>
      </div>
      {rows.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="text-gray-500 border-b border-gray-200">
                <th className="py-2 pr-3">Mã</th>
                <th className="py-2 pr-3">Trạng thái</th>
                <th className="py-2 pr-3">Nguồn</th>
                <th className="py-2">Hết hạn</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-gray-100">
                  <td className="py-2 pr-3 font-mono">{row.code}</td>
                  <td className="py-2 pr-3">{row.status}</td>
                  <td className="py-2 pr-3">{row.source}</td>
                  <td className="py-2">
                    {row.expires_at ? new Date(row.expires_at).toLocaleDateString('vi-VN') : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : userId && !loading ? (
        <p className="text-sm text-gray-500">Không có mã hoặc chưa tra cứu.</p>
      ) : null}
    </div>
  );
}
