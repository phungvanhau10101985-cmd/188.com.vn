'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminBankAPI } from '@/lib/admin-api';
import {
  DEPOSIT_MIN_VND,
  DEPOSIT_PERCENT,
  HIGH_UNIT_MIN_PERCENT,
  HIGH_UNIT_PRICE_VND,
} from '@/lib/business-info';
import { formatDepositMinVnd } from '@/lib/order-deposit';

const inputClass =
  'w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-200';

export default function DepositPercentPanel() {
  const [percent, setPercent] = useState(String(DEPOSIT_PERCENT));
  const [highPercent, setHighPercent] = useState(String(HIGH_UNIT_MIN_PERCENT));
  const [minAmount, setMinAmount] = useState(String(DEPOSIT_MIN_VND));
  const [highOrderAmount, setHighOrderAmount] = useState(String(HIGH_UNIT_PRICE_VND));
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
      setHighPercent(String(out.high_order_percent ?? HIGH_UNIT_MIN_PERCENT));
      setMinAmount(String(out.min_amount ?? DEPOSIT_MIN_VND));
      setHighOrderAmount(String(out.high_order_amount ?? HIGH_UNIT_PRICE_VND));
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
    const low = Number(percent);
    const highPct = Number(highPercent);
    const floor = Number(minAmount);
    const threshold = Number(highOrderAmount);
    if (!Number.isInteger(low) || low < 1 || low > 99) {
      setBanner({ variant: 'error', text: 'Cọc đơn dưới mốc phải là số nguyên từ 1 đến 99.' });
      return;
    }
    if (!Number.isInteger(highPct) || highPct < 1 || highPct > 99) {
      setBanner({ variant: 'error', text: 'Cọc đơn từ mốc trở lên phải là số nguyên từ 1 đến 99.' });
      return;
    }
    if (!Number.isInteger(floor) || floor < DEPOSIT_MIN_VND) {
      setBanner({
        variant: 'error',
        text: `Cọc tối thiểu không được thấp hơn ${formatDepositMinVnd(DEPOSIT_MIN_VND)}.`,
      });
      return;
    }
    if (!Number.isInteger(threshold) || threshold < DEPOSIT_MIN_VND) {
      setBanner({
        variant: 'error',
        text: `Mốc giá trị hàng không được thấp hơn ${formatDepositMinVnd(DEPOSIT_MIN_VND)}.`,
      });
      return;
    }
    setSaving(true);
    setBanner(null);
    try {
      const out = await adminBankAPI.saveDepositPercent(low, floor, threshold, highPct);
      setPercent(String(out.partial_percent));
      setHighPercent(String(out.high_order_percent));
      setMinAmount(String(out.min_amount));
      setHighOrderAmount(String(out.high_order_amount));
      setBanner({
        variant: 'ok',
        text: `Đã lưu: đơn dưới ${formatDepositMinVnd(out.high_order_amount)} cọc ${out.partial_percent}%, từ mốc đó cọc ${out.high_order_percent}%, tối thiểu ${formatDepositMinVnd(out.min_amount)}. Đơn mới và lần đổi mức cọc sau sẽ dùng số này.`,
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
        Điền mốc giá trị hàng, rồi điền % cọc cho đơn dưới mốc và % cọc cho đơn từ mốc trở lên. Ví dụ mốc
        3.000.000đ, dưới mốc cọc 10%, từ mốc cọc 30%. Tiền cọc tính trên giá trị hàng, không gồm phí giao hàng.
        Nếu số tiền theo % thấp hơn cọc tối thiểu thì lấy cọc tối thiểu, nhưng không vượt giá trị hàng. Khách vẫn
        chọn được cọc 100% khi thanh toán; mức 100% gồm cả phí giao hàng. Đơn đang chờ cọc giữ số đã chốt cho đến
        khi khách đổi lại.
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
        <form onSubmit={onSave} className="mt-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-gray-800">Mốc giá trị hàng (đ)</span>
              <input
                type="number"
                inputMode="numeric"
                min={DEPOSIT_MIN_VND}
                step={100000}
                required
                value={highOrderAmount}
                onChange={(ev) => setHighOrderAmount(ev.target.value)}
                className={inputClass}
                aria-describedby="deposit-percent-hint"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-gray-800">Cọc đơn dưới mốc (%)</span>
              <input
                type="number"
                inputMode="numeric"
                min={1}
                max={99}
                step={1}
                required
                value={percent}
                onChange={(ev) => setPercent(ev.target.value)}
                className={inputClass}
                aria-describedby="deposit-percent-hint"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-gray-800">Cọc đơn từ mốc (%)</span>
              <input
                type="number"
                inputMode="numeric"
                min={1}
                max={99}
                step={1}
                required
                value={highPercent}
                onChange={(ev) => setHighPercent(ev.target.value)}
                className={inputClass}
                aria-describedby="deposit-percent-hint"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-gray-800">Cọc tối thiểu (đ)</span>
              <input
                type="number"
                inputMode="numeric"
                min={DEPOSIT_MIN_VND}
                step={1000}
                required
                value={minAmount}
                onChange={(ev) => setMinAmount(ev.target.value)}
                className={inputClass}
                aria-describedby="deposit-percent-hint"
              />
            </label>
          </div>
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {saving ? 'Đang lưu…' : 'Lưu mức cọc'}
          </button>
          <p id="deposit-percent-hint" className="text-xs text-gray-500">
            Hai mức cọc từ 1 đến 99. Mốc giá trị hàng và cọc tối thiểu không thấp hơn {formatDepositMinVnd(DEPOSIT_MIN_VND)}.
            Đơn nhỏ hơn mốc dùng «Cọc đơn dưới mốc». Đơn bằng hoặc lớn hơn mốc dùng «Cọc đơn từ mốc».
          </p>
        </form>
      )}
    </section>
  );
}
