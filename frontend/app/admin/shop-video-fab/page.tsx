'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  adminShopVideoFabAPI,
  type ShopVideoFabSettings,
} from '@/lib/admin-api';

const hints = [
  'Đơn vị: pixel (px), tính từ mép dưới / mép phải cửa sổ trình duyệt.',
  'Mobile có thanh điều hướng dưới: dùng dòng «có thanh nav»; trang chi tiết SP / auth không có thanh đó → dùng «không thanh».',
  'Desktop: breakpoint từ 768px trở lên.',
];

export default function AdminShopVideoFabPage() {
  const [form, setForm] = useState<ShopVideoFabSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 4000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await adminShopVideoFabAPI.get();
      setForm(data);
    } catch (e) {
      showToast('err', (e as Error)?.message || 'Lỗi tải cấu hình');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const setNum =
    (key: keyof ShopVideoFabSettings) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const v = e.target.value === '' ? 0 : Number(e.target.value);
      setForm((prev) => (prev ? { ...prev, [key]: Number.isFinite(v) ? v : 0 } : prev));
    };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form) return;
    setSaving(true);
    try {
      const saved = await adminShopVideoFabAPI.update(form);
      setForm(saved);
      showToast('ok', 'Đã lưu vị trí nút video (site sẽ nhận sau vài chục giây nhờ cache).');
    } catch (err) {
      showToast('err', (err as Error)?.message || 'Lỗi lưu');
    } finally {
      setSaving(false);
    }
  };

  return (
      <div className="p-6 max-w-xl">
        <h1 className="text-xl font-bold text-gray-900 mb-2">Vị trí nút lướt xem video</h1>
        <p className="text-sm text-gray-600 mb-4">
          Nút tròn cam có icon video góc phải màn hình (mobile & desktop). Điều chỉnh khoảng cách mép dưới / mép phải.
        </p>
        <ul className="text-xs text-gray-500 space-y-1 mb-6 list-disc list-inside">
          {hints.map((h) => (
            <li key={h}>{h}</li>
          ))}
        </ul>

        {loading || !form ? (
          <p className="text-gray-500">Đang tải…</p>
        ) : (
          <form onSubmit={handleSubmit} className="bg-white rounded-lg border border-gray-200 shadow-sm p-5 space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <label className="block">
                <span className="text-sm font-medium text-gray-700">Mobile — phải (px)</span>
                <input
                  type="number"
                  min={0}
                  max={400}
                  value={form.right_mobile_px}
                  onChange={setNum('right_mobile_px')}
                  className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
                />
              </label>
              <label className="block">
                <span className="text-sm font-medium text-gray-700">Mobile — dưới, không thanh nav (px)</span>
                <input
                  type="number"
                  min={0}
                  max={400}
                  value={form.bottom_mobile_px_no_nav}
                  onChange={setNum('bottom_mobile_px_no_nav')}
                  className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
                />
              </label>
              <label className="block sm:col-span-2">
                <span className="text-sm font-medium text-gray-700">Mobile — dưới, có thanh nav (px)</span>
                <input
                  type="number"
                  min={0}
                  max={400}
                  value={form.bottom_mobile_px_with_nav}
                  onChange={setNum('bottom_mobile_px_with_nav')}
                  className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
                />
              </label>
              <label className="block">
                <span className="text-sm font-medium text-gray-700">Desktop — phải (px)</span>
                <input
                  type="number"
                  min={0}
                  max={400}
                  value={form.right_desktop_px}
                  onChange={setNum('right_desktop_px')}
                  className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
                />
              </label>
              <label className="block">
                <span className="text-sm font-medium text-gray-700">Desktop — dưới (px)</span>
                <input
                  type="number"
                  min={0}
                  max={400}
                  value={form.bottom_desktop_px}
                  onChange={setNum('bottom_desktop_px')}
                  className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
                />
              </label>
            </div>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 rounded-lg bg-[#ea580c] text-white text-sm font-semibold hover:bg-orange-700 disabled:opacity-50"
            >
              {saving ? 'Đang lưu…' : 'Lưu cấu hình'}
            </button>
          </form>
        )}

        {toast && (
          <div
            className={`fixed bottom-6 right-6 px-4 py-2 rounded-lg shadow text-sm z-[100] ${
              toast.type === 'ok' ? 'bg-green-700 text-white' : 'bg-red-600 text-white'
            }`}
          >
            {toast.msg}
          </div>
        )}
      </div>
  );
}
