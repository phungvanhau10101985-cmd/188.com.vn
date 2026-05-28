'use client';

import PromoCodesManager from '@/components/admin/PromoCodesManager';
import SaleCalendarSettingsPanel from '@/components/admin/SaleCalendarSettingsPanel';
import { useEffect, useState } from 'react';
import { adminPromotionsAPI, AdminPromotionCode } from '@/lib/admin-api';

export default function AdminPromotionsPage() {
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (window.location.hash === '#site-sale') {
      window.requestAnimationFrame(() => {
        document.getElementById('site-sale')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    }
  }, []);

  return (
    <div className="p-6 max-w-6xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Khuyến mãi</h1>
      <p className="text-sm text-gray-600 mb-6">
        Quản lý toàn bộ mã khuyến mãi, sale site-wide, tặng mã vào ví khách và chạy chiến dịch tự động.
      </p>

      <PromoCodesManager />

      <SaleCalendarSettingsPanel embedded />

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
  const [promoCodes, setPromoCodes] = useState<AdminPromotionCode[]>([]);
  const [days, setDays] = useState('7');
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    void adminPromotionsAPI
      .listPromotions()
      .then((res) => {
        const active = res.items.filter((item) => item.is_active);
        setPromoCodes(active);
        if (active.length > 0) {
          setCode((prev) => (active.some((item) => item.code === prev) ? prev : active[0].code));
        }
      })
      .catch(() => setPromoCodes([]));
  }, []);

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
          {promoCodes.length > 0 ? (
            promoCodes.map((promo) => (
              <option key={promo.id} value={promo.code}>
                {promo.code} — {promo.name}
              </option>
            ))
          ) : (
            <option value="WELCOME188">WELCOME188 — Chào mừng</option>
          )}
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
