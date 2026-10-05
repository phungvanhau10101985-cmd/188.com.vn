'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminBankAPI } from '@/lib/admin-api';
import { DEPOSIT_PERCENT } from '@/lib/business-info';

export default function DepositPercentPanel() {
  const [percent, setPercent] = useState(String(DEPOSIT_PERCENT));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<{ variant: 'ok' | 'error'; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const out = await adminBankAPI.getDepositPercent();
      setPercent(String(out.partial_percent));
    } catch (e) {
      setError((e as Error)?.message || 'Không tải được mức cọc');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    const n = Number(percent);
    if (!Number.isInteger(n) || n < 1 || n > 99) {
      setBanner({ variant: 'error', text: 'Nhập số nguyên từ 1 đến 99.' });
      return;
    }
    setSaving(true);
    setBanner(null);
    try {
      const out = await adminBankAPI.saveDepositPercent(n);
      setPercent(String(out.partial_percent));
      setBanner({
        variant: 'ok',
        text: `Đã lưu mức cọc ${out.partial_percent}%. Đơn mới và lần đổi mức cọc sau sẽ dùng số này.`,
      });
    } catch (err) {
      setBanner({ variant: 'error', text: (err as Error)?.message || 'Không lưu được mức cọc' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="mb-8 rounded-xl border border-gray-200 bg-white p-5 shadow-sm" aria-labelledby="deposit-percent-heading">
      <h2 id="deposit-percent-heading" className="text-base font-semibold text-gray-900">
        Mức cọc
      </h2>
      <p className="mt-1 max-w-3xl text-sm text-gray-600">
        Phần trăm khách chuyển trước trên giá trị hàng (không gồm phí giao hàng). Khách vẫn có thể chọn cọc 100% khi thanh toán.
        Đơn đang chờ cọc giữ mức đã chốt cho đến khi khách đổi lại.
      </p>

      {error ? (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}{' '}
          <button type="button" onClick={() => void load()} className="font-medium underline">
            Thử lại
          </button>
        </div>
      ) : null}

      {banner ? (
        <div
          className={`mt-4 rounded-lg border px-4 py-3 text-sm ${
            banner.variant === 'ok'
              ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
              : 'border-red-200 bg-red-50 text-red-700'
          }`}
        >
          {banner.text}
        </div>
      ) : null}

      {loading ? (
        <p className="mt-4 text-sm text-gray-500">Đang tải mức cọc…</p>
      ) : (
        <form onSubmit={onSave} className="mt-4 flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-gray-800">Cọc trước (%)</span>
            <input
              type="number"
              inputMode="numeric"
              min={1}
              max={99}
              step={1}
              required
              value={percent}
              onChange={(ev) => setPercent(ev.target.value)}
              className="w-28 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-200"
              aria-describedby="deposit-percent-hint"
            />
          </label>
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {saving ? 'Đang lưu…' : 'Lưu mức cọc'}
          </button>
          <p id="deposit-percent-hint" className="w-full text-xs text-gray-500">
            Từ 1 đến 99. Mặc định 30 nếu chưa lưu.
          </p>
        </form>
      )}
    </section>
  );
}
