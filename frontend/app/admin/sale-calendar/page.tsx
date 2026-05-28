'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminSaleCalendarAPI, type AdminSaleCalendarSettings } from '@/lib/admin-api';

const MONTH_NAMES = [
  'Tháng 1',
  'Tháng 2',
  'Tháng 3',
  'Tháng 4',
  'Tháng 5',
  'Tháng 6',
  'Tháng 7',
  'Tháng 8',
  'Tháng 9',
  'Tháng 10',
  'Tháng 11',
  'Tháng 12',
];

export default function AdminSaleCalendarPage() {
  const [data, setData] = useState<AdminSaleCalendarSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await adminSaleCalendarAPI.getSettings();
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không tải được cấu hình sale');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

  const toggleGlobal = async () => {
    if (!data) return;
    setSaving(true);
    try {
      const res = await adminSaleCalendarAPI.updateSettings({ enabled: !data.enabled });
      setData(res);
      showToast('Đã cập nhật chương trình sale');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lỗi lưu');
    } finally {
      setSaving(false);
    }
  };

  const saveTeaserDays = async (days: number) => {
    setSaving(true);
    try {
      const res = await adminSaleCalendarAPI.updateSettings({ teaser_days: days });
      setData(res);
      showToast('Đã cập nhật số ngày teaser');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lỗi lưu');
    } finally {
      setSaving(false);
    }
  };

  const updateMonth = async (
    month: number,
    patch: { enabled?: boolean; discount_percent_override?: number | null },
  ) => {
    setSaving(true);
    try {
      await adminSaleCalendarAPI.updateMonthRule({ month, ...patch });
      await load();
      showToast(`Đã cập nhật tháng ${month}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lỗi lưu tháng');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="p-6 flex justify-center">
        <div className="animate-spin w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          {error}{' '}
          <button type="button" onClick={() => void load()} className="underline font-medium">
            Thử lại
          </button>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const current = data.current;

  return (
    <div className="p-6 max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Sale ngày trùng tháng</h1>
        <p className="text-sm text-gray-600 mt-1">
          Tháng lẻ giảm 6%, tháng chẵn 8% — đúng ngày {`{tháng}/{tháng}`}. Teaser trước 3 ngày (có thể chỉnh).
          Feed Google/Meta/TikTok: prefix title + sale_price ngày active.
        </p>
      </div>

      {toast ? (
        <div className="bg-green-50 border border-green-200 text-green-800 rounded-lg px-4 py-2 text-sm">
          {toast}
        </div>
      ) : null}

      <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-semibold text-gray-900">Bật chương trình</p>
            <p className="text-xs text-gray-500">Tắt toàn bộ teaser + giảm giá site + feed</p>
          </div>
          <button
            type="button"
            disabled={saving}
            onClick={() => void toggleGlobal()}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              data.enabled ? 'bg-green-600 text-white' : 'bg-gray-200 text-gray-700'
            }`}
          >
            {data.enabled ? 'Đang bật' : 'Đang tắt'}
          </button>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Ngày teaser trước sale</label>
          <select
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
            value={data.teaser_days}
            disabled={saving}
            onChange={(e) => void saveTeaserDays(Number(e.target.value))}
          >
            {[1, 2, 3, 4, 5, 7].map((d) => (
              <option key={d} value={d}>
                {d} ngày
              </option>
            ))}
          </select>
        </div>

        {current?.phase ? (
          <div className="rounded-lg bg-orange-50 border border-orange-200 px-4 py-3 text-sm">
            <p className="font-semibold text-orange-900">
              Hiện tại: {current.phase === 'teaser' ? 'Sắp sale' : 'Đang sale'} — {current.event_label}
            </p>
            <p className="text-orange-800">Giảm {current.discount_percent}%</p>
          </div>
        ) : (
          <p className="text-sm text-gray-500">Hiện không trong cửa sổ teaser/active.</p>
        )}
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100 font-semibold text-gray-900">Theo tháng</div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
              <tr>
                <th className="px-4 py-2">Tháng</th>
                <th className="px-4 py-2">Ngày sale</th>
                <th className="px-4 py-2">Mặc định</th>
                <th className="px-4 py-2">Override %</th>
                <th className="px-4 py-2">Bật</th>
              </tr>
            </thead>
            <tbody>
              {data.month_rules.map((rule) => (
                <tr key={rule.month} className="border-t border-gray-100">
                  <td className="px-4 py-2 font-medium">{MONTH_NAMES[rule.month - 1]}</td>
                  <td className="px-4 py-2">
                    {rule.month}/{rule.month}
                  </td>
                  <td className="px-4 py-2">{rule.default_discount_percent}%</td>
                  <td className="px-4 py-2">
                    <input
                      type="number"
                      min={0}
                      max={50}
                      step={0.5}
                      className="w-20 border border-gray-300 rounded px-2 py-1"
                      placeholder="Auto"
                      defaultValue={rule.discount_percent_override ?? ''}
                      onBlur={(e) => {
                        const raw = e.target.value.trim();
                        void updateMonth(
                          rule.month,
                          raw === ''
                            ? { discount_percent_override: null }
                            : { discount_percent_override: Number(raw) },
                        );
                      }}
                    />
                  </td>
                  <td className="px-4 py-2">
                    <button
                      type="button"
                      disabled={saving}
                      onClick={() => void updateMonth(rule.month, { enabled: !rule.enabled })}
                      className={`text-xs px-2 py-1 rounded ${
                        rule.enabled ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      {rule.enabled ? 'Bật' : 'Tắt'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h2 className="font-semibold text-gray-900 mb-3">Lịch sắp tới</h2>
        <ul className="space-y-2 text-sm">
          {data.upcoming.map((ev) => (
            <li key={ev.event_date} className="flex flex-wrap gap-x-3 gap-y-1 border-b border-gray-50 pb-2">
              <span className="font-medium">{ev.event_label}</span>
              <span className="text-gray-600">-{ev.discount_percent}%</span>
              <span className="text-gray-500 text-xs">Teaser từ {ev.teaser_start.slice(0, 10)}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
